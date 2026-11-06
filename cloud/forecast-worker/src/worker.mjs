import {
  EIGHT_MIN, FIVE_MIN, SCHEDULE_REFRESH_MS,
  japanDate, isValidDate, extractSchedule, nextCaptureStage,
  nextResultStage, validOdds,
} from './policy.mjs';
import { summarizeDailyAudit } from './audit.mjs';

const allowedHeaders = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' };
const MAX_IMPORT_RACES = 288;

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: allowedHeaders });
}

function unavailableReason(row, nowMs) {
  if (row.forecast_json && row.model_version && (row.decision === 'BUY' || row.decision === 'SKIP')) return null;
  if (nowMs < row.deadline_ms && row.capture_stage === 0) return 'NOT_DUE';
  if (row.failure_code) return row.failure_code;
  return row.captured_ms ? 'MODEL_NOT_DEPLOYED' : 'DATA_NOT_CAPTURED';
}

export function serializeForecast(row, nowMs) {
  const reason = unavailableReason(row, nowMs);
  const ready = !reason && row.captured_ms < row.deadline_ms;
  return {
    race_id: row.race_id,
    deadline_at: new Date(row.deadline_ms).toISOString(),
    forecast_completed_at: ready ? new Date(row.captured_ms).toISOString() : null,
    model_version: ready ? row.model_version : null,
    odds_source: row.odds_source ?? null,
    odds_fetched_at: row.captured_ms && row.odds_json ? new Date(row.captured_ms).toISOString() : null,
    status: ready ? 'READY' : nowMs >= row.deadline_ms || row.capture_stage === 2 ? 'UNAVAILABLE' : 'PENDING',
    decision: ready ? row.decision : null,
    combinations: ready ? JSON.parse(row.forecast_json).combinations : [],
    stakes: ready ? JSON.parse(row.forecast_json).stakes : [],
    quality_flags: reason ? [reason] : [],
    result: row.result_json ? JSON.parse(row.result_json) : null,
    result_recorded_at: row.result_recorded_ms ? new Date(row.result_recorded_ms).toISOString() : null,
  };
}

function parseDateProgramUrl(env, date) {
  const compact = date.replaceAll('-', '');
  const base = env.PROGRAM_FEED_BASE_URL ?? 'https://boatraceopenapi.github.io/api/v1';
  const url = new URL(`${base.replace(/\/$/, '')}/${date.slice(0, 4)}/${compact}.json`);
  if (url.protocol !== 'https:') throw new Error('PROGRAM_FEED_MUST_BE_HTTPS');
  return url.toString();
}

async function fetchJson(url, opts = {}) {
  const response = await fetch(url, { ...opts, signal: AbortSignal.timeout(8_000) });
  if (!response.ok) throw new Error(`HTTP_${response.status}`);
  return response.json();
}

async function loadProgram(env, date) {
  const feed = await fetchJson(parseDateProgramUrl(env, date));
  if (feed?.programs?.stadiums == null) throw new Error('INVALID_PROGRAM_SCHEMA');
  return feed;
}

export function dailyImportDue(date, nowMs, previous) {
  // Only imports the published race timetable, not exhibition or odds.
  // Retry a missing schedule at most hourly; no external request per cron tick.
  const jstHour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Tokyo', hour: '2-digit', hourCycle: 'h23' }).format(nowMs));
  return date === japanDate(nowMs) && jstHour >= 6 && jstHour <= 12 &&
    (!previous || (previous.race_count === 0 && nowMs - previous.last_attempt_ms >= SCHEDULE_REFRESH_MS));
}

async function importDailySchedule(env, date, nowMs) {
  const previous = await env.DB.prepare('SELECT * FROM daily_import WHERE race_date = ?').bind(date).first();
  if (!dailyImportDue(date, nowMs, previous)) return;
  // Claim first; concurrent cron executions won't import the same date twice.
  const claim = await env.DB.prepare(`INSERT INTO daily_import (race_date, last_attempt_ms, race_count)
    VALUES (?, ?, 0) ON CONFLICT(race_date) DO UPDATE SET last_attempt_ms=excluded.last_attempt_ms
    WHERE daily_import.race_count=0 AND daily_import.last_attempt_ms <= ?`)
    .bind(date, nowMs, nowMs - SCHEDULE_REFRESH_MS).run();
  if (!claim.meta?.changes) return;
  try {
    const races = extractSchedule(await loadProgram(env, date), date);
    if (!races.length || races.length > MAX_IMPORT_RACES) throw new Error('INVALID_SCHEDULE_COUNT');
    // Preserve any already captured data and race deadlines; never overwrite a
    // race's original schedule after a capture attempt has started.
    for (const race of races) {
      await env.DB.prepare(`INSERT INTO race_schedule
        (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(race_id) DO UPDATE SET deadline_ms=excluded.deadline_ms, updated_ms=excluded.updated_ms
        WHERE race_schedule.capture_stage = 0 AND race_schedule.capture_started_ms IS NULL`)
        .bind(race.race_id, race.race_date, race.stadium_number, race.race_number, race.deadline_ms, nowMs).run();
    }
    await env.DB.prepare('UPDATE daily_import SET race_count=?, last_success_ms=?, failure_code=NULL WHERE race_date=?')
      .bind(races.length, nowMs, date).run();
  } catch (error) {
    await env.DB.prepare('UPDATE daily_import SET failure_code=? WHERE race_date=?')
      .bind(String(error.message).slice(0, 100), date).run();
  }
}

function selectRace(program, row) {
  const stadiums = program?.programs?.stadiums ?? {};
  return (stadiums[String(row.stadium_number)] ?? stadiums[String(row.stadium_number).padStart(2, '0')])
    ?.races?.[String(row.race_number)] ?? null;
}

async function authorizedOdds(env, row) {
  if (!env.ODDS_API_URL) throw new Error('ODDS_PROVIDER_NOT_CONFIGURED');
  const url = new URL(env.ODDS_API_URL);
  if (url.protocol !== 'https:') throw new Error('ODDS_PROVIDER_MUST_BE_HTTPS');
  url.searchParams.set('date', row.race_date);
  url.searchParams.set('stadium', String(row.stadium_number));
  url.searchParams.set('race', String(row.race_number));
  const headers = env.ODDS_API_TOKEN ? { authorization: `Bearer ${env.ODDS_API_TOKEN}` } : {};
  const response = await fetchJson(url.toString(), { headers });
  if (!validOdds(response)) throw new Error('ODDS_NOT_COMPLETE');
  return { odds: response.odds, source: response.source ?? 'configured-provider' };
}

async function captureDueRaces(env, date, nowMs) {
  const { results: rows } = await env.DB.prepare(`SELECT * FROM race_schedule
    WHERE race_date=? AND capture_stage < 2 AND deadline_ms > ? AND deadline_ms <= ?
    ORDER BY deadline_ms LIMIT 30`)
    .bind(date, nowMs, nowMs + EIGHT_MIN).all();
  const due = (rows ?? []).map(row => ({ row, stage: nextCaptureStage(row, nowMs) })).filter(item => item.stage);
  if (!due.length) return;
  // One upstream daily-feed request for every batch of due races; no polling.
  let program;
  let programError;
  try { program = await loadProgram(env, date); } catch (error) { programError = String(error.message).slice(0, 100); }
  for (const { row, stage } of due) {
    const claimed = await env.DB.prepare(`UPDATE race_schedule SET capture_stage=?, capture_started_ms=?, updated_ms=?
      WHERE race_id=? AND capture_stage=? AND deadline_ms > ?`)
      .bind(stage, nowMs, nowMs, row.race_id, row.capture_stage, nowMs).run();
    if (!claimed.meta?.changes) continue;
    await env.DB.prepare(`INSERT INTO capture_attempt (race_id, stage, started_ms)
      VALUES (?, ?, ?) ON CONFLICT(race_id, stage) DO NOTHING`)
      .bind(row.race_id, stage, nowMs).run();
    const observation = selectRace(program, row);
    let odds = null;
    let failure = programError ?? (!observation?.preview ? 'EXHIBITION_NOT_AVAILABLE' : null);
    if (!failure) {
      try { odds = await authorizedOdds(env, row); }
      catch (error) { failure = String(error.message).slice(0, 100); }
    }
    // A slow network response cannot backfill a supposedly pre-close forecast.
    const finishedAt = Date.now();
    if (finishedAt >= row.deadline_ms) failure = 'CAPTURE_FINISHED_AFTER_DEADLINE';
    const captured = !failure && odds;
    await env.DB.prepare(`UPDATE race_schedule SET
      capture_stage=?, captured_ms=?, preview_json=?, odds_json=?, odds_source=?, failure_code=?, updated_ms=?
      WHERE race_id=? AND capture_started_ms=?`)
      .bind(captured ? 2 : stage, captured ? finishedAt : null,
        observation?.preview ? JSON.stringify(observation.preview) : null,
        captured ? JSON.stringify(odds.odds) : null,
        captured ? odds.source : null, failure, finishedAt, row.race_id, nowMs).run();
    await env.DB.prepare(`UPDATE capture_attempt SET finished_ms=?, completed=?, failure_code=?
      WHERE race_id=? AND stage=? AND started_ms=?`)
      .bind(finishedAt, captured ? 1 : 0, failure, row.race_id, stage, nowMs).run();
    // Deliberately no BUY/SKIP until the Android Model A parity runner exists.
  }
}

function parseResult(observation) {
  const payout = observation?.result?.payouts?.trifecta?.[0];
  if (!payout || !/^\d-\d-\d$/.test(String(payout.combination)) || !Number.isFinite(Number(payout.amount))) return null;
  return { trifecta_combination: payout.combination, trifecta_payout: Number(payout.amount) };
}

async function settleDueRaces(env, date, nowMs) {
  const { results: rows } = await env.DB.prepare(`SELECT * FROM race_schedule
    WHERE race_date=? AND result_stage < 2 AND deadline_ms <= ? ORDER BY deadline_ms LIMIT 30`)
    .bind(date, nowMs - 20 * 60_000).all();
  const due = (rows ?? []).map(row => ({ row, stage: nextResultStage(row, nowMs) })).filter(item => item.stage);
  if (!due.length) return;
  let program;
  try { program = await loadProgram(env, date); } catch { /* source may lag; second chance below */ }
  for (const { row, stage } of due) {
    const claimed = await env.DB.prepare(`UPDATE race_schedule SET result_stage=?, updated_ms=?
      WHERE race_id=? AND result_stage=?`)
      .bind(stage, nowMs, row.race_id, row.result_stage).run();
    if (!claimed.meta?.changes) continue;
    const result = parseResult(selectRace(program, row));
    if (result) await env.DB.prepare(`UPDATE race_schedule
      SET result_json=?, result_recorded_ms=?, result_stage=2, updated_ms=? WHERE race_id=?`)
      .bind(JSON.stringify(result), Date.now(), Date.now(), row.race_id).run();
  }
}

export async function runScheduled(env, nowMs = Date.now()) {
  const date = japanDate(nowMs);
  await env.DB.prepare(`INSERT INTO cron_heartbeat (race_date, last_started_ms, started_count)
    VALUES (?, ?, 1)
    ON CONFLICT(race_date) DO UPDATE SET
      last_started_ms=MAX(cron_heartbeat.last_started_ms, excluded.last_started_ms),
      started_count=cron_heartbeat.started_count+1`)
    .bind(date, nowMs).run();
  try {
    await importDailySchedule(env, date, nowMs);
    await captureDueRaces(env, date, nowMs);
    await settleDueRaces(env, date, nowMs);
    await env.DB.prepare(`UPDATE cron_heartbeat SET
      last_completed_ms=MAX(COALESCE(last_completed_ms, 0), ?),
      completed_count=completed_count+1, last_error_code=NULL WHERE race_date=?`)
      .bind(Date.now(), date).run();
  } catch (error) {
    await env.DB.prepare('UPDATE cron_heartbeat SET last_error_code=? WHERE race_date=?')
      .bind('SCHEDULED_RUN_FAILED', date).run();
    throw error;
  }
}

export default {
  async scheduled(_event, env, ctx) { ctx.waitUntil(runScheduled(env)); },
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method !== 'GET') return jsonResponse({ error: 'METHOD_NOT_ALLOWED' }, 405);
    if (url.pathname === '/v1/health') return jsonResponse({ ok: true, service: 'boat-ai-cloud', schema_version: 1 });
    if (url.pathname !== '/v1/forecasts' && url.pathname !== '/v1/audit') return jsonResponse({ error: 'NOT_FOUND' }, 404);
    const date = url.searchParams.get('date');
    if (!isValidDate(date)) return jsonResponse({ error: 'INVALID_DATE' }, 400);
    if (url.pathname === '/v1/audit') {
      const [schedule, attempts, imported, heartbeat] = await Promise.all([
        env.DB.prepare('SELECT * FROM race_schedule WHERE race_date=? ORDER BY deadline_ms LIMIT 288').bind(date).all(),
        env.DB.prepare(`SELECT a.stage, a.started_ms, a.finished_ms, a.completed, a.failure_code
          FROM capture_attempt a INNER JOIN race_schedule s ON s.race_id=a.race_id
          WHERE s.race_date=? ORDER BY a.started_ms LIMIT 576`).bind(date).all(),
        env.DB.prepare('SELECT * FROM daily_import WHERE race_date=?').bind(date).first(),
        env.DB.prepare('SELECT * FROM cron_heartbeat WHERE race_date=?').bind(date).first(),
      ]);
      return jsonResponse(summarizeDailyAudit(date, Date.now(), schedule.results ?? [],
        attempts.results ?? [], imported, heartbeat));
    }
    const { results: rows } = await env.DB.prepare('SELECT * FROM race_schedule WHERE race_date=? ORDER BY deadline_ms, race_id LIMIT 288')
      .bind(date).all();
    return jsonResponse({ schema_version: 1, date, generated_at: new Date().toISOString(),
      races: (rows ?? []).map(row => serializeForecast(row, Date.now())) });
  },
};
