import { japanDate } from './policy.mjs';

const MAX_AGE_MS = 5 * 60_000;
const HEALTH_STALE_AFTER_MS = 5 * 60_000;
const HEALTH_ACTIVE_WINDOW_MS = 10 * 60_000;
const ACCEPTED_FIELDS = new Set([
  'schema_version', 'date', 'device_id', 'app_version', 'sent_at',
  'program_received_at', 'race_count', 'odds_attempted', 'odds_succeeded',
  'odds_failed', 'odds_last_attempt_at', 'odds_last_success_at',
]);

function optionalTime(value, sentMs, field) {
  if (value === null || value === undefined) return null;
  if (typeof value !== 'string' || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,3})?Z$/.test(value))
    throw new Error(`INVALID_${field}`);
  const ms = Date.parse(value);
  if (!Number.isFinite(ms) || ms > sentMs + 1_000 || ms < sentMs - 24 * 60 * 60_000)
    throw new Error(`INVALID_${field}`);
  return ms;
}

function count(value, maximum, field) {
  if (!Number.isSafeInteger(value) || value < 0 || value > maximum)
    throw new Error(`INVALID_${field}`);
  return value;
}

/** Device-received acquisition metrics only. NEVER turn these into pre-close provenance. */
export function normalizeDeviceHeartbeat(body, nowMs = Date.now()) {
  if (!body || typeof body !== 'object' || Array.isArray(body) || body.schema_version !== 1)
    throw new Error('INVALID_SCHEMA');
  if (Object.keys(body).some(key => !ACCEPTED_FIELDS.has(key)))
    throw new Error('UNEXPECTED_FIELD');
  if (typeof body.device_id !== 'string' ||
      !/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(body.device_id))
    throw new Error('INVALID_DEVICE_ID');
  if (body.date !== japanDate(nowMs)) throw new Error('INVALID_DATE');
  if (typeof body.sent_at !== 'string' || !body.sent_at.endsWith('Z')) throw new Error('INVALID_SENT_AT');
  const sentMs = Date.parse(body.sent_at);
  if (!Number.isFinite(sentMs) || Math.abs(nowMs - sentMs) > MAX_AGE_MS)
    throw new Error('STALE_DEVICE_CLOCK');
  if (typeof body.app_version !== 'string' || !/^\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(body.app_version))
    throw new Error('INVALID_APP_VERSION');
  const attempted = count(body.odds_attempted, 1_000_000, 'ATTEMPTED');
  const succeeded = count(body.odds_succeeded, attempted, 'SUCCEEDED');
  const failed = count(body.odds_failed, attempted, 'FAILED');
  if (succeeded + failed > attempted) throw new Error('INVALID_ODDS_COUNTS');
  const programMs = optionalTime(body.program_received_at, sentMs, 'PROGRAM_TIME');
  const lastOddsMs = optionalTime(body.odds_last_attempt_at, sentMs, 'ODDS_ATTEMPT_TIME');
  const lastSuccessMs = optionalTime(body.odds_last_success_at, sentMs, 'ODDS_SUCCESS_TIME');
  if (succeeded > 0 && lastSuccessMs === null) throw new Error('MISSING_ODDS_SUCCESS_TIME');
  if (attempted > 0 && lastOddsMs === null) throw new Error('MISSING_ODDS_ATTEMPT_TIME');
  return {
    deviceId: body.device_id, date: body.date, sentMs, receivedMs: nowMs,
    appVersion: body.app_version, programMs,
    raceCount: count(body.race_count, 288, 'RACE_COUNT'),
    attempted, succeeded, failed, lastOddsMs, lastSuccessMs,
  };
}

/** Bounded compare that does not disclose an accepted token length via early exit. */
export function collectorKeyMatches(provided, expected) {
  if (typeof provided !== 'string' || typeof expected !== 'string' ||
      provided.length > 200 || expected.length < 32 || expected.length > 200) return false;
  const a = new TextEncoder().encode(provided);
  const b = new TextEncoder().encode(expected);
  let difference = a.length ^ b.length;
  for (let i = 0; i < Math.max(a.length, b.length); i++) difference |= (a[i] ?? 0) ^ (b[i] ?? 0);
  return difference === 0;
}

export async function ingestCollectorHeartbeat(request, env, nowMs = Date.now()) {
  if (!env.COLLECTOR_INGEST_TOKEN) return { status: 503, payload: { error: 'COLLECTOR_INGEST_DISABLED' } };
  const auth = request.headers.get('authorization') ?? '';
  if (!auth.startsWith('Bearer ') || !collectorKeyMatches(auth.slice(7), env.COLLECTOR_INGEST_TOKEN))
    return { status: 401, payload: { error: 'UNAUTHORIZED' } };
  if (!request.headers.get('content-type')?.toLowerCase().startsWith('application/json'))
    return { status: 415, payload: { error: 'JSON_REQUIRED' } };
  const raw = await request.text();
  if (raw.length > 2_048) return { status: 413, payload: { error: 'PAYLOAD_TOO_LARGE' } };
  let sample;
  try { sample = normalizeDeviceHeartbeat(JSON.parse(raw), nowMs); }
  catch (error) { return { status: 400, payload: { error: String(error.message).slice(0, 80) } }; }
  await env.DB.prepare(`INSERT INTO collector_device_heartbeat
    (device_id, race_date, device_sent_ms, received_ms, app_version,
     program_received_ms, race_count, odds_attempted, odds_succeeded,
     odds_failed, odds_last_attempt_ms, odds_last_success_ms)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(device_id) DO UPDATE SET
      race_date=excluded.race_date, device_sent_ms=excluded.device_sent_ms,
      received_ms=excluded.received_ms, app_version=excluded.app_version,
      program_received_ms=excluded.program_received_ms, race_count=excluded.race_count,
      odds_attempted=excluded.odds_attempted, odds_succeeded=excluded.odds_succeeded,
      odds_failed=excluded.odds_failed, odds_last_attempt_ms=excluded.odds_last_attempt_ms,
      odds_last_success_ms=excluded.odds_last_success_ms
    WHERE excluded.received_ms >= collector_device_heartbeat.received_ms`)
    .bind(sample.deviceId, sample.date, sample.sentMs, sample.receivedMs,
      sample.appVersion, sample.programMs, sample.raceCount, sample.attempted,
      sample.succeeded, sample.failed, sample.lastOddsMs, sample.lastSuccessMs).run();
  return { status: 202, payload: { schema_version: 1, accepted: true,
    classification: 'DEVICE_RECEIPT_ONLY', server_received_at: new Date(nowMs).toISOString(),
    eligible_for_forecast: false } };
}

export async function readCollectorStatus(env, date, nowMs = Date.now()) {
  const { results } = await env.DB.prepare(`SELECT received_ms, race_count,
      odds_attempted, odds_succeeded, odds_failed, odds_last_success_ms
      FROM collector_device_heartbeat WHERE race_date=?
      ORDER BY received_ms DESC LIMIT 20`).bind(date).all();
  const rows = results ?? [];
  const latest = rows[0];
  return {
    schema_version: 1, date, mode: 'DEVICE_RECEIPT_ONLY', eligible_for_forecast: false,
    active_devices_10m: rows.filter(row => nowMs - row.received_ms <= 600_000 && row.received_ms <= nowMs).length,
    last_received_at: latest ? new Date(latest.received_ms).toISOString() : null,
    latest_device_race_count: latest?.race_count ?? null,
    latest_device_odds_attempted: latest?.odds_attempted ?? null,
    latest_device_odds_succeeded: latest?.odds_succeeded ?? null,
    latest_device_odds_failed: latest?.odds_failed ?? null,
    latest_device_odds_success_at: latest?.odds_last_success_ms ? new Date(latest.odds_last_success_ms).toISOString() : null,
  };
}

/** Crosses JST midnight without creating a false healthy/failed day boundary. */
export function summarizeCollectorHealth(rows, nowMs = Date.now()) {
  const valid = rows.filter(row => Number.isSafeInteger(row.received_ms) &&
    row.received_ms >= 0 && row.received_ms <= nowMs);
  const latest = valid[0] ?? null;
  const ageMs = latest ? nowMs - latest.received_ms : null;
  const monitoringState = ageMs === null ? 'NEVER_CONNECTED' :
    ageMs <= HEALTH_STALE_AFTER_MS ? 'ACTIVE' : 'STALE';
  return {
    schema_version: 1,
    mode: 'DEVICE_RECEIPT_ONLY',
    eligible_for_forecast: false,
    evaluated_at: new Date(nowMs).toISOString(),
    monitoring_state: monitoringState,
    stale_after_seconds: HEALTH_STALE_AFTER_MS / 1_000,
    active_devices_10m: valid.filter(row => nowMs - row.received_ms <= HEALTH_ACTIVE_WINDOW_MS).length,
    last_received_at: latest ? new Date(latest.received_ms).toISOString() : null,
    last_received_age_seconds: ageMs === null ? null : Math.floor(ageMs / 1_000),
    last_race_date: latest?.race_date ?? null,
    latest_device_race_count: latest?.race_count ?? null,
    latest_device_odds_attempted: latest?.odds_attempted ?? null,
    latest_device_odds_succeeded: latest?.odds_succeeded ?? null,
    latest_device_odds_failed: latest?.odds_failed ?? null,
  };
}

/** Read-only public aggregate; never includes device identifiers or credentials. */
export async function readCollectorHealth(env, nowMs = Date.now()) {
  const { results } = await env.DB.prepare(`SELECT received_ms, race_date, race_count,
      odds_attempted, odds_succeeded, odds_failed
      FROM collector_device_heartbeat ORDER BY received_ms DESC LIMIT 20`).all();
  return summarizeCollectorHealth(results ?? [], nowMs);
}
