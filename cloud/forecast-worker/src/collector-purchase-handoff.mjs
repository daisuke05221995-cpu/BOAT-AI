import { collectorKeyMatches } from './device-collector.mjs';

const ACTIVE_MS = 5 * 60_000;
const EXPIRY_MS = 10 * 60_000;
const PURCHASE_EXPIRY_MS = 90_000;
const ID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const COMBINATION = /^([1-6])-([1-6])-([1-6])$/;

function authorize(request, env) {
  if (!env.COLLECTOR_INGEST_TOKEN) return { status: 503, payload: { error: 'HANDOFF_DISABLED' } };
  const header = request.headers.get('authorization') ?? '';
  if (!header.startsWith('Bearer ') || !collectorKeyMatches(header.slice(7), env.COLLECTOR_INGEST_TOKEN))
    return { status: 401, payload: { error: 'UNAUTHORIZED' } };
  return null;
}

function onlyKnownKeys(value, keys) {
  return Object.keys(value).every(key => keys.includes(key));
}

function validSession(session, nowMs) {
  const todayJst = new Date(nowMs + 9 * 60 * 60_000).toISOString().slice(0, 10);
  if (!session || typeof session !== 'object' || Array.isArray(session) ||
    !ID.test(session.id) || !Array.isArray(session.races) ||
    session.races.length < 1 || session.races.length > 12 ||
    !Array.isArray(session.selectedRaceIds) ||
    !onlyKnownKeys(session, ['id', 'createdAt', 'races', 'selectedRaceIds'])) return false;
  const ids = new Set();
  let total = 0;
  for (const race of session.races) {
    if (!race || typeof race !== 'object' || typeof race.raceId !== 'string' ||
      race.raceId.length > 80 || ids.has(race.raceId) ||
      race.date !== todayJst ||
      !Number.isInteger(race.stadiumNumber) || race.stadiumNumber < 1 || race.stadiumNumber > 24 ||
      !Number.isInteger(race.raceNumber) || race.raceNumber < 1 || race.raceNumber > 12 ||
      typeof race.venueName !== 'string' || race.venueName.length > 40 ||
      !Array.isArray(race.tickets) || race.tickets.length < 1 || race.tickets.length > 6 ||
      !onlyKnownKeys(race, ['raceId', 'date', 'stadiumNumber', 'raceNumber', 'venueName', 'recommended', 'tickets', 'strategyId'])) return false;
    ids.add(race.raceId);
    const combos = new Set();
    for (const ticket of race.tickets) {
      const match = typeof ticket?.combination === 'string' && ticket.combination.match(COMBINATION);
      if (!match || new Set(match.slice(1)).size !== 3 || combos.has(ticket.combination) ||
        !Number.isInteger(ticket.amount) || ticket.amount < 100 ||
        ticket.amount > 100_000 || ticket.amount % 100 !== 0 ||
        !onlyKnownKeys(ticket, ['combination', 'amount', 'odds', 'tier', 'aiProbability', 'expectedReturnRate'])) return false;
      combos.add(ticket.combination);
      total += ticket.amount;
    }
  }
  const selected = new Set(session.selectedRaceIds);
  return selected.size > 0 && selected.size === session.selectedRaceIds.length &&
    [...selected].every(id => ids.has(id)) && total <= 1_000_000;
}

async function parsePost(request) {
  if (!request.headers.get('content-type')?.startsWith('application/json')) throw Error('JSON_REQUIRED');
  const raw = await request.text();
  if (raw.length > 16_384) throw Error('PAYLOAD_TOO_LARGE');
  return JSON.parse(raw);
}

function inputError(error) {
  if (error.message === 'JSON_REQUIRED') return { status: 415, payload: { error: 'JSON_REQUIRED' } };
  if (error.message === 'PAYLOAD_TOO_LARGE') return { status: 413, payload: { error: 'PAYLOAD_TOO_LARGE' } };
  return { status: 400, payload: { error: 'INVALID_HANDOFF' } };
}

/** Stage a proposal on the collector device; no interaction with Teleboat occurs. */
export async function stagePurchaseHandoff(request, env, nowMs = Date.now()) {
  const denied = authorize(request, env);
  if (denied) return denied;
  let body;
  try { body = await parsePost(request); } catch (e) { return inputError(e); }
  const proposal = body?.schema_version === 1 &&
    Object.keys(body).sort().join(',') === 'schema_version,session';
  const authorizedPurchase = body?.schema_version === 2 &&
    Object.keys(body).sort().join(',') === 'approved_at_ms,approved_total_yen,authorized_purchase,schema_version,session' &&
    body.authorized_purchase === true && Number.isInteger(body.approved_at_ms) &&
    body.approved_at_ms <= nowMs && body.approved_at_ms >= nowMs - 60_000;
  if ((!proposal && !authorizedPurchase) || !validSession(body.session, nowMs))
    return { status: 400, payload: { error: 'INVALID_HANDOFF' } };
  const selectedRaces = body?.session?.races?.filter(r => body.session.selectedRaceIds?.includes(r.raceId)) ?? [];
  const selectedTotal = selectedRaces.reduce((n, race) =>
    n + race.tickets.reduce((sum, ticket) => sum + ticket.amount, 0), 0);
  if (authorizedPurchase && (selectedTotal > 5_000 || selectedTotal <= 0 ||
      body.approved_total_yen !== selectedTotal || selectedRaces.length !== body.session.selectedRaceIds.length))
    return { status: 400, payload: { error: 'INVALID_HANDOFF' } };
  const device = await env.DB.prepare(`SELECT device_id FROM collector_device_heartbeat
    WHERE received_ms BETWEEN ? AND ? ORDER BY received_ms DESC LIMIT 1`)
    .bind(nowMs - ACTIVE_MS, nowMs).first();
  if (!device) return { status: 409, payload: { error: 'NO_ACTIVE_COLLECTOR' } };
  await env.DB.prepare("UPDATE collector_purchase_handoff SET status='EXPIRED' WHERE status='PENDING' AND expires_ms<=?")
    .bind(nowMs).run();
  const pending = await env.DB.prepare(`SELECT handoff_id FROM collector_purchase_handoff
    WHERE device_id=? AND status='PENDING' LIMIT 1`).bind(device.device_id).first();
  if (pending) return { status: 409, payload: { error: 'HANDOFF_ALREADY_PENDING' } };
  const handoffId = crypto.randomUUID();
  const payload = authorizedPurchase ? {
    schema_version: 2,
    session: body.session,
    approved_at_ms: body.approved_at_ms,
    approved_total_yen: selectedTotal
  } : body.session;
  const expiry = nowMs + (authorizedPurchase ? PURCHASE_EXPIRY_MS : EXPIRY_MS);
  try {
    await env.DB.prepare(`INSERT INTO collector_purchase_handoff
      (handoff_id, device_id, session_json, status, requested_ms, expires_ms)
      VALUES (?, ?, ?, 'PENDING', ?, ?)`).bind(
      handoffId, device.device_id, JSON.stringify(payload), nowMs, expiry).run();
  } catch (_) {
    return { status: 409, payload: { error: 'HANDOFF_ALREADY_PENDING' } };
  }
  return { status: 202, payload: { schema_version: authorizedPurchase ? 2 : 1,
    staged: true, handoff_id: handoffId, expires_at: new Date(expiry).toISOString() } };
}

export async function nextPurchaseHandoff(request, env, nowMs = Date.now()) {
  const denied = authorize(request, env);
  if (denied) return denied;
  const deviceId = new URL(request.url).searchParams.get('device_id') ?? '';
  if (!ID.test(deviceId)) return { status: 400, payload: { error: 'INVALID_DEVICE_ID' } };
  const device = await env.DB.prepare('SELECT device_id FROM collector_device_heartbeat WHERE device_id=?')
    .bind(deviceId).first();
  if (!device) return { status: 403, payload: { error: 'DEVICE_NOT_REGISTERED' } };
  const handoff = await env.DB.prepare(`SELECT handoff_id, session_json, expires_ms FROM collector_purchase_handoff
    WHERE device_id=? AND status='PENDING' AND expires_ms>? ORDER BY requested_ms ASC LIMIT 1`)
    .bind(deviceId, nowMs).first();
  const raw = handoff ? JSON.parse(handoff.session_json) : null;
  const authorized = raw?.schema_version === 2;
  return { status: 200, payload: { schema_version: authorized ? 2 : 1,
    handoff_id: handoff?.handoff_id ?? null,
    expires_at: handoff ? new Date(handoff.expires_ms).toISOString() : null,
    session: authorized ? raw.session : raw,
    purchase_authorized: authorized ? true : undefined,
    approved_at_ms: authorized ? raw.approved_at_ms : undefined,
    approved_total_yen: authorized ? raw.approved_total_yen : undefined } };
}

export async function acknowledgePurchaseHandoff(request, env, nowMs = Date.now()) {
  const denied = authorize(request, env);
  if (denied) return denied;
  let body;
  try { body = await parsePost(request); } catch (e) { return inputError(e); }
  if (!body || Object.keys(body).sort().join(',') !== 'device_id,handoff_id,schema_version' ||
    body.schema_version !== 1 || !ID.test(body.device_id) || !ID.test(body.handoff_id))
    return { status: 400, payload: { error: 'INVALID_HANDOFF' } };
  await env.DB.prepare(`UPDATE collector_purchase_handoff SET status='DELIVERED', delivered_ms=?
    WHERE handoff_id=? AND device_id=? AND status='PENDING' AND expires_ms>?`)
    .bind(nowMs, body.handoff_id, body.device_id, nowMs).run();
  const record = await env.DB.prepare(`SELECT status FROM collector_purchase_handoff WHERE handoff_id=? AND device_id=?`)
    .bind(body.handoff_id, body.device_id).first();
  if (record?.status !== 'DELIVERED') return { status: 409, payload: { error: 'HANDOFF_NOT_PENDING' } };
  return { status: 202, payload: { schema_version: 1, accepted: true } };
}
