import { collectorKeyMatches } from './device-collector.mjs';

const ACTIVE_MS = 5 * 60_000;
const EXPIRY_MS = 3 * 60_000;
const MIN_INTERVAL_MS = 60_000;
const ID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function authorize(request, env) {
  if (!env.COLLECTOR_INGEST_TOKEN) return { status: 503, payload: { error: 'REMOTE_DISABLED' } };
  const header = request.headers.get('authorization') ?? '';
  if (!header.startsWith('Bearer ') || !collectorKeyMatches(header.slice(7), env.COLLECTOR_INGEST_TOKEN))
    return { status: 401, payload: { error: 'UNAUTHORIZED' } };
  return null;
}

async function readJson(request) {
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json'))
    throw new Error('JSON_REQUIRED');
  const raw = await request.text();
  if (raw.length > 512) throw new Error('PAYLOAD_TOO_LARGE');
  const parsed = JSON.parse(raw);
  if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('INVALID_BODY');
  return parsed;
}

function exactFields(body, fields) {
  return Object.keys(body).length === fields.length &&
    fields.every(field => Object.hasOwn(body, field));
}

function inputError(error) {
  if (error.message === 'JSON_REQUIRED') return { status: 415, payload: { error: 'JSON_REQUIRED' } };
  if (error.message === 'PAYLOAD_TOO_LARGE') return { status: 413, payload: { error: 'PAYLOAD_TOO_LARGE' } };
  return { status: 400, payload: { error: 'INVALID_COMMAND' } };
}

async function expireOld(env, nowMs) {
  await env.DB.prepare("UPDATE collector_remote_refresh SET status='EXPIRED' WHERE status='PENDING' AND expires_ms<=?")
    .bind(nowMs).run();
}

/** Only one fixed action exists: refresh BOAT AI data in the foreground collector app. */
export async function requestRemoteRefresh(request, env, nowMs = Date.now()) {
  const denied = authorize(request, env);
  if (denied) return denied;
  let body;
  try { body = await readJson(request); } catch (error) { return inputError(error); }
  if (!exactFields(body, ['schema_version', 'action']) ||
    body.schema_version !== 1 || body.action !== 'REFRESH_NOW')
    return { status: 400, payload: { error: 'INVALID_COMMAND' } };

  const device = await env.DB.prepare(`SELECT device_id FROM collector_device_heartbeat
    WHERE received_ms BETWEEN ? AND ? ORDER BY received_ms DESC LIMIT 1`)
    .bind(nowMs - ACTIVE_MS, nowMs).first();
  if (!device) return { status: 409, payload: { error: 'NO_ACTIVE_COLLECTOR' } };
  await expireOld(env, nowMs);
  const pending = await env.DB.prepare(`SELECT command_id FROM collector_remote_refresh
    WHERE device_id=? AND status='PENDING' LIMIT 1`).bind(device.device_id).first();
  if (pending) return { status: 202, payload: { schema_version: 1, queued: true,
    coalesced: true, command_id: pending.command_id, action: 'REFRESH_NOW' } };
  const latest = await env.DB.prepare(`SELECT requested_ms FROM collector_remote_refresh
    WHERE device_id=? ORDER BY requested_ms DESC LIMIT 1`).bind(device.device_id).first();
  if (latest && nowMs - latest.requested_ms < MIN_INTERVAL_MS)
    return { status: 429, payload: { error: 'REFRESH_RATE_LIMIT' } };
  const id = crypto.randomUUID();
  try {
    await env.DB.prepare(`INSERT INTO collector_remote_refresh
      (command_id, device_id, action, status, requested_ms, expires_ms)
      VALUES (?, ?, 'REFRESH_NOW', 'PENDING', ?, ?)`).bind(id, device.device_id, nowMs, nowMs + EXPIRY_MS).run();
  } catch (_) {
    // The partial unique index blocks parallel requests from queuing multiple commands.
    return { status: 409, payload: { error: 'COMMAND_ALREADY_PENDING' } };
  }
  return { status: 202, payload: { schema_version: 1, queued: true, coalesced: false,
    command_id: id, action: 'REFRESH_NOW' } };
}

/** Only an authenticated registered collector can retrieve its own pending command. */
export async function pollRemoteRefresh(request, env, nowMs = Date.now()) {
  const denied = authorize(request, env);
  if (denied) return denied;
  const deviceId = new URL(request.url).searchParams.get('device_id');
  if (!ID_PATTERN.test(deviceId ?? '')) return { status: 400, payload: { error: 'INVALID_DEVICE_ID' } };
  const device = await env.DB.prepare('SELECT device_id FROM collector_device_heartbeat WHERE device_id=?')
    .bind(deviceId).first();
  if (!device) return { status: 403, payload: { error: 'DEVICE_NOT_REGISTERED' } };
  const command = await env.DB.prepare(`SELECT command_id, action, expires_ms FROM collector_remote_refresh
    WHERE device_id=? AND status='PENDING' AND expires_ms>? ORDER BY requested_ms ASC LIMIT 1`)
    .bind(deviceId, nowMs).first();
  return { status: 200, payload: { schema_version: 1, action: command?.action ?? null,
    command_id: command?.command_id ?? null,
    expires_at: command ? new Date(command.expires_ms).toISOString() : null } };
}

/** ACCEPTED means delivered to Android, not proof the network refresh succeeded. */
export async function acknowledgeRemoteRefresh(request, env, nowMs = Date.now()) {
  const denied = authorize(request, env);
  if (denied) return denied;
  let body;
  try { body = await readJson(request); } catch (error) { return inputError(error); }
  if (!exactFields(body, ['schema_version', 'device_id', 'command_id', 'action']) ||
    body.schema_version !== 1 || !ID_PATTERN.test(body.device_id) ||
    !ID_PATTERN.test(body.command_id) || body.action !== 'REFRESH_NOW')
    return { status: 400, payload: { error: 'INVALID_COMMAND' } };
  await env.DB.prepare(`UPDATE collector_remote_refresh SET status='ACCEPTED', accepted_ms=?
    WHERE command_id=? AND device_id=? AND action='REFRESH_NOW' AND status='PENDING' AND expires_ms>?`)
    .bind(nowMs, body.command_id, body.device_id, nowMs).run();
  const record = await env.DB.prepare(`SELECT status FROM collector_remote_refresh
    WHERE command_id=? AND device_id=? AND action='REFRESH_NOW'`)
    .bind(body.command_id, body.device_id).first();
  if (record?.status !== 'ACCEPTED') return { status: 409, payload: { error: 'COMMAND_NOT_PENDING' } };
  return { status: 202, payload: { schema_version: 1, accepted: true, action: 'REFRESH_NOW' } };
}
