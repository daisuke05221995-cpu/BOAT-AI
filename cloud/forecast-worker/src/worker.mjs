import {
  EIGHT_MIN, FIVE_MIN, SCHEDULE_REFRESH_MS,
  japanDate, isValidDate, extractSchedule, nextCaptureStage,
} from './policy.mjs';
import { summarizeDailyAudit } from './audit.mjs';
import { verifiedOddsPayload, verifiedPreviewPayload, verifiedStoredCapture } from './preclose.mjs';
import { normalizePublishedResult, resultRetryDue } from './result.mjs';
import { inspectProgramRosterCandidate } from './program-roster-candidate.mjs';
import { inspectSixFinishCandidate } from './six-finish-candidate.mjs';
import { evaluateModelAShadow, parseShadowApprovals } from './model-a-shadow.mjs';
import { SOURCE_MAX_AGE_MS } from './preclose.mjs';
import { FROZEN_MODEL_A_BUNDLE_SHA256 } from './model-a-model-store.mjs';
import { runAutomaticHistoryCatchup } from './model-a-history-auto.mjs';

const allowedHeaders = { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' };
const MAX_IMPORT_RACES = 288;

function jsonResponse(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: allowedHeaders });
}

function unavailableReason(row, nowMs) {
  if (row.forecast_json && row.model_version && (row.decision === 'BUY' || row.decision === 'SKIP')) {
    return verifiedStoredCapture(row) ? null : 'CAPTURE_NOT_VERIFIED';
  }
  if (nowMs < row.deadline_ms && row.capture_stage === 0) return 'NOT_DUE';
  if (row.failure_code) return row.failure_code;
  return row.captured_ms ? 'MODEL_NOT_DEPLOYED' : 'DATA_NOT_CAPTURED';
}

export function serializeForecast(row, nowMs) {
  const reason = unavailableReason(row, nowMs);
  const ready = !reason && verifiedStoredCapture(row);
  return {
    race_id: row.race_id,
    deadline_at: new Date(row.deadline_ms).toISOString(),
    forecast_completed_at: ready ? new Date(row.captured_ms).toISOString() : null,
    model_version: ready ? row.model_version : null,
    preview_source: row.preview_source ?? null,
    preview_observed_at: Number.isFinite(row.preview_observed_ms) ? new Date(row.preview_observed_ms).toISOString() : null,
    weather_source: row.weather_source ?? null,
    weather_observed_at: Number.isFinite(row.weather_observed_ms) ? new Date(row.weather_observed_ms).toISOString() : null,
    odds_source: row.odds_source ?? null,
    odds_observed_at: Number.isFinite(row.odds_observed_ms) ? new Date(row.odds_observed_ms).toISOString() : null,
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
  // Retry a missing schedule at most hourly; recover after a late deployment or
  // a morning outage. The capture path still forbids post-close predictions.
  const jstHour = Number(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Tokyo', hour: '2-digit', hourCycle: 'h23' }).format(nowMs));
  return date === japanDate(nowMs) && jstHour >= 6 && jstHour <= 23 &&
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
    const program = await loadProgram(env, date);
    const fetchedAt = Date.now();
    const races = extractSchedule(program, date);
    if (!races.length || races.length > MAX_IMPORT_RACES) throw new Error('INVALID_SCHEDULE_COUNT');
    // Preserve any already captured data and race deadlines; never overwrite a
    // race's original schedule after a capture attempt has started.
    const insert = env.DB.prepare(`INSERT INTO race_schedule
        (race_id, race_date, stadium_number, race_number, deadline_ms, updated_ms)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(race_id) DO UPDATE SET deadline_ms=excluded.deadline_ms, updated_ms=excluded.updated_ms
        WHERE race_schedule.capture_stage = 0 AND race_schedule.capture_started_ms IS NULL`);
    // D1 Free has a per-invocation query limit. Batch one-time timetable writes
    // instead of issuing one D1 subrequest per race (up to 288 races/day).
    for (let index = 0; index < races.length; index += 48) {
      await env.DB.batch(races.slice(index, index + 48).map(race =>
        insert.bind(race.race_id, race.race_date, race.stadium_number,
          race.race_number, race.deadline_ms, nowMs)));
    }
    // Store a diagnostic candidate separately from the prediction table. The
    // program feed's actual observation/publishing time is unknown; even a
    // complete six-boat roster here is NOT a verified forecast input.
    const saveCandidate = env.DB.prepare(`INSERT INTO program_roster_candidate
        (race_id, checked_ms, status, failure_code, candidate_json)
        VALUES (?, ?, ?, ?, ?) ON CONFLICT(race_id) DO NOTHING`);
    for (let index = 0; index < races.length; index += 48) {
      await env.DB.batch(races.slice(index, index + 48).map(race => {
        const observation = inspectProgramRosterCandidate(selectRace(program, race), race, fetchedAt);
        return saveCandidate.bind(race.race_id, fetchedAt, observation.status,
          observation.failureCode, observation.candidate ? JSON.stringify(observation.candidate) : null);
      }));
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
  return verifiedOddsPayload(response, row, Date.now());
}

async function authorizedPreview(env, row) {
  if (!env.PREVIEW_API_URL) throw new Error('PREVIEW_PROVIDER_NOT_CONFIGURED');
  const url = new URL(env.PREVIEW_API_URL);
  if (url.protocol !== 'https:') throw new Error('PREVIEW_PROVIDER_MUST_BE_HTTPS');
  url.searchParams.set('date', row.race_date);
  url.searchParams.set('stadium', String(row.stadium_number));
  url.searchParams.set('race', String(row.race_number));
  const headers = env.PREVIEW_API_TOKEN ? { authorization: `Bearer ${env.PREVIEW_API_TOKEN}` } : {};
  const response = await fetchJson(url.toString(), { headers });
  return verifiedPreviewPayload(response, row, Date.now());
}

async function authorizedRoster(env, row) {
  if (!env.ROSTER_API_URL) throw new Error('ROSTER_PROVIDER_NOT_CONFIGURED');
  const url = new URL(env.ROSTER_API_URL);
  if (url.protocol !== 'https:') throw new Error('ROSTER_PROVIDER_MUST_BE_HTTPS');
  url.searchParams.set('date', row.race_date);
  url.searchParams.set('stadium', String(row.stadium_number));
  url.searchParams.set('race', String(row.race_number));
  const headers = env.ROSTER_API_TOKEN ? { authorization: `Bearer ${env.ROSTER_API_TOKEN}` } : {};
  return fetchJson(url.toString(), { headers });
}

async function mapBounded(items, limit, work) {
  const results = new Array(items.length);
  let cursor = 0;
  await Promise.all(Array.from({ length: Math.min(items.length, limit) }, async () => {
    while (cursor < items.length) {
      const index = cursor++;
      results[index] = await work(items[index]);
    }
  }));
  return results;
}

async function captureDueRaces(env, date, nowMs) {
  const { results: rows } = await env.DB.prepare(`SELECT * FROM race_schedule
    WHERE race_date=? AND capture_stage < 2 AND deadline_ms > ? AND deadline_ms <= ?
    ORDER BY deadline_ms LIMIT 30`)
    .bind(date, nowMs, nowMs + EIGHT_MIN).all();
  const due = (rows ?? []).map(row => ({ row, stage: nextCaptureStage(row, nowMs) })).filter(item => item.stage);
  if (!due.length) return;
  // The public daily timetable feed can lag by 10–20 minutes. It is never
  // authoritative for a T-8 exhibition snapshot or a BUY/SKIP decision.
  const claim = env.DB.prepare(`UPDATE race_schedule SET capture_stage=?, capture_started_ms=?, updated_ms=?
    WHERE race_id=? AND capture_stage=? AND deadline_ms > ?`);
  const claimResults = await env.DB.batch(due.map(({ row, stage }) =>
    claim.bind(stage, nowMs, nowMs, row.race_id, row.capture_stage, nowMs)));
  const claimed = due.filter((_, index) => claimResults[index]?.meta?.changes);
  if (!claimed.length) return;
  const attempt = env.DB.prepare(`INSERT INTO capture_attempt (race_id, stage, started_ms)
    VALUES (?, ?, ?) ON CONFLICT(race_id, stage) DO NOTHING`);
  await env.DB.batch(claimed.map(({ row, stage }) => attempt.bind(row.race_id, stage, nowMs)));
  const save = env.DB.prepare(`UPDATE race_schedule SET
    capture_stage=?, captured_ms=?, preview_json=?, preview_source=?, preview_observed_ms=?,
    weather_source=?, weather_observed_ms=?,
    odds_json=?, odds_source=?, odds_observed_ms=?, failure_code=?, updated_ms=?
    WHERE race_id=? AND capture_started_ms=?`);
  const audit = env.DB.prepare(`UPDATE capture_attempt SET finished_ms=?, completed=?, failure_code=?
    WHERE race_id=? AND stage=? AND started_ms=?`);
  const shadowSave = env.DB.prepare(`INSERT INTO model_a_shadow_attempt
    (race_id, capture_stage, checked_ms, status, reason, history_sha256,
      model_bundle_sha256, source_provenance_json, probabilities_json)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(race_id, capture_stage) DO NOTHING`);
  let approvals = null;
  let approvalFailure = null;
  try { approvals = parseShadowApprovals(env.MODEL_A_APPROVED_SOURCES_JSON); }
  catch { approvalFailure = 'MODEL_A_APPROVALS_INVALID'; }
  const assetCache = new Map();
  // Several races often share the same deadline. Bounded parallel fetches
  // prevent one slow venue from making every subsequent T-8 attempt stale.
  // Concurrency is capped to avoid a 30-race burst against the provider.
  const observations = await mapBounded(claimed, 4, async ({ row, stage }) => {
    let preview = null;
    let odds = null;
    let roster = null;
    const failures = [];
    // Preserve the existing cap of four total simultaneous external fetches.
    // Each source is attempted independently; one failure cannot suppress
    // another source, and the optional roster is never a timetable cache.
    try { preview = await authorizedPreview(env, row); }
    catch (error) { failures.push(String(error.message)); }
    try { odds = await authorizedOdds(env, row); }
    catch (error) { failures.push(String(error.message)); }
    if (approvals && env.ROSTER_API_URL) {
      try { roster = await authorizedRoster(env, row); } catch { /* shadow remains unavailable */ }
    }
    // A slow network response cannot backfill a supposedly pre-close forecast.
    const finishedAt = Date.now();
    if (finishedAt >= row.deadline_ms) failures.push('CAPTURE_FINISHED_AFTER_DEADLINE');
    const failure = failures.length ? failures.join('|').slice(0, 100) : null;
    const captured = !failure && preview != null && odds != null;
    let shadow = { status: 'UNAVAILABLE', reason: approvalFailure ?? 'MODEL_A_LIVE_SOURCES_INCOMPLETE' };
    if (captured && roster && !approvalFailure) {
      shadow = await evaluateModelAShadow({ db: env.DB, row, nowMs: finishedAt,
        rosterSnapshot: roster,
        previewSnapshot: { date: row.race_date, stadium_number: row.stadium_number,
          race_number: row.race_number, source: preview.source,
          observed_at: new Date(preview.observedMs).toISOString(), preview: preview.preview },
        oddsSnapshot: { date: row.race_date, stadium_number: row.stadium_number,
          race_number: row.race_number, source: odds.source,
          observed_at: new Date(odds.observedMs).toISOString(), odds: odds.odds },
        approvals, bundleSha256: FROZEN_MODEL_A_BUNDLE_SHA256, cache: assetCache });
    }
    // Computing the model may take time. Never persist a probability that was
    // first completed after close or using observations that have gone stale.
    const shadowCheckedMs = Date.now();
    if (shadow.status === 'FORECAST_ONLY' && (shadowCheckedMs >= row.deadline_ms ||
        ['rosterObservedMs', 'previewObservedMs', 'weatherObservedMs', 'oddsObservedMs']
          .some(key => shadowCheckedMs - shadow.provenance[key] > SOURCE_MAX_AGE_MS))) {
      shadow = { status: 'UNAVAILABLE', reason: 'MODEL_A_SHADOW_FINISHED_TOO_LATE' };
    }
    return { row, stage, preview, odds, failure, finishedAt, captured, shadow, shadowCheckedMs };
  });
  const updates = [];
  for (const { row, stage, preview, odds, failure, finishedAt, captured, shadow, shadowCheckedMs } of observations) {
    updates.push(save.bind(captured ? 2 : stage, captured ? finishedAt : null,
        preview ? JSON.stringify(preview.preview) : null,
        preview?.source ?? null, preview?.observedMs ?? null,
        preview?.weatherSource ?? null, preview?.weatherObservedMs ?? null,
        odds ? JSON.stringify(odds.odds) : null,
        odds?.source ?? null, odds?.observedMs ?? null,
        failure, finishedAt, row.race_id, nowMs));
    updates.push(audit.bind(finishedAt, captured ? 1 : 0, failure, row.race_id, stage, nowMs));
    updates.push(shadowSave.bind(row.race_id, stage, shadowCheckedMs, shadow.status,
      shadow.reason ?? null, shadow.historySha256 ?? null, shadow.modelBundleSha256 ?? null,
      shadow.provenance ? JSON.stringify(shadow.provenance) : null,
      shadow.forecast ? JSON.stringify(shadow.forecast) : null));
    // Shadow probabilities never produce Android-visible BUY/SKIP decisions.
  }
  await env.DB.batch(updates);
}

async function settleDueRaces(env, date, nowMs) {
  const yesterday = japanDate(nowMs - 24 * 60 * 60_000);
  const retryCutoff = nowMs - 15 * 60_000;
  // D1 can contain legacy result_stage=2 rows without results. Check the
  // actual persisted result, not the old two-attempt flag. Reconcile yesterday
  // as well, since delayed final dividends and postponed meetings are common.
  const { results: rows } = await env.DB.prepare(`SELECT * FROM race_schedule
    WHERE race_date IN (?, ?) AND result_json IS NULL AND deadline_ms <= ?
      AND (result_last_attempt_ms IS NULL OR result_last_attempt_ms <= ?)
    ORDER BY deadline_ms LIMIT 30`)
    .bind(yesterday, date, nowMs - 20 * 60_000, retryCutoff).all();
  const due = (rows ?? []).filter(row => resultRetryDue(row, nowMs));
  if (!due.length) return;
  const claim = env.DB.prepare(`UPDATE race_schedule SET
    result_stage=1, result_last_attempt_ms=?, updated_ms=?
    WHERE race_id=? AND result_json IS NULL
      AND (result_last_attempt_ms IS NULL OR result_last_attempt_ms <= ?)`);
  const claimed = await env.DB.batch(due.map(row =>
    claim.bind(nowMs, nowMs, row.race_id, retryCutoff)));
  const claimedRows = due.filter((_, index) => claimed[index]?.meta?.changes);
  if (!claimedRows.length) return;
  const programs = new Map(await Promise.all([...new Set(claimedRows.map(row => row.race_date))]
    .map(async raceDate => {
      try { return [raceDate, await loadProgram(env, raceDate)]; }
      catch { return [raceDate, null]; }
    })));
  const save = env.DB.prepare(`UPDATE race_schedule
    SET result_json=?, result_recorded_ms=?, result_stage=2,
      result_failure_code=NULL, updated_ms=? WHERE race_id=? AND result_last_attempt_ms=?
      AND result_json IS NULL`);
  const fail = env.DB.prepare(`UPDATE race_schedule SET result_failure_code=?, updated_ms=?
    WHERE race_id=? AND result_last_attempt_ms=? AND result_json IS NULL`);
  const saveSixFinish = env.DB.prepare(`INSERT INTO six_finish_candidate
    (race_id, checked_ms, status, failure_code, candidate_json)
    VALUES (?, ?, ?, ?, ?) ON CONFLICT(race_id) DO NOTHING`);
  const updates = [];
  for (const row of claimedRows) {
    const program = programs.get(row.race_date);
    const race = selectRace(program, row);
    const result = normalizePublishedResult(race, row);
    if (result) {
      const checkedMs = Date.now();
      updates.push(save.bind(JSON.stringify(result), checkedMs, checkedMs, row.race_id, nowMs));
      const six = inspectSixFinishCandidate(race, row, result, checkedMs);
      updates.push(saveSixFinish.bind(row.race_id, checkedMs, six.status, six.failureCode,
        six.candidate ? JSON.stringify(six.candidate) : null));
    }
    else updates.push(fail.bind(program ? 'RESULT_NOT_FINAL' : 'RESULT_SOURCE_UNAVAILABLE',
      Date.now(), row.race_id, nowMs));
  }
  if (updates.length) await env.DB.batch(updates);
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
    // At most one historical day per cron, never before its JST day-end.
    // A missing authorized feed is a no-op; old results and live capture
    // continue even if a history day cannot be certified.
    await runAutomaticHistoryCatchup(env, nowMs);
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
    if (url.pathname === '/v1/history-status') {
      const [active, attempts] = await Promise.all([
        env.DB.prepare('SELECT through_day FROM model_a_history_active WHERE singleton=1').first(),
        env.DB.prepare(`SELECT race_date, last_finished_ms, status, reason, expected_races,
            committed_races FROM model_a_history_day_attempt ORDER BY race_date DESC LIMIT 7`).all(),
      ]);
      const day = active?.through_day ?? null;
      return jsonResponse({ mode: 'STRICT_DAILY_HISTORY', history_through_date: day ?
        new Date((day - 719_163) * 86_400_000).toISOString().slice(0, 10) : null,
        ready_for_today: day === Math.floor(Date.parse(`${japanDate(Date.now())}T00:00:00Z`) / 86_400_000) + 719_163 - 1,
        recent_attempts: attempts.results ?? [] });
    }
    if (url.pathname !== '/v1/forecasts' && url.pathname !== '/v1/audit' &&
        url.pathname !== '/v1/model-a-shadow') return jsonResponse({ error: 'NOT_FOUND' }, 404);
    const date = url.searchParams.get('date');
    if (!isValidDate(date)) return jsonResponse({ error: 'INVALID_DATE' }, 400);
    if (url.pathname === '/v1/model-a-shadow') {
      const { results: rows } = await env.DB.prepare(`SELECT a.status, a.reason, COUNT(*) AS count
        FROM model_a_shadow_attempt a JOIN race_schedule s ON a.race_id=s.race_id
        WHERE s.race_date=? GROUP BY a.status, a.reason ORDER BY count DESC LIMIT 100`)
        .bind(date).all();
      // Aggregate-only visibility: never expose model probabilities, entrants,
      // tokens, source payloads or per-race purchase-like predictions.
      return jsonResponse({ date, mode: 'FORECAST_ONLY', buy_skip_enabled: false,
        attempts: (rows ?? []).reduce((sum, row) => sum + row.count, 0),
        outcomes: rows ?? [] });
    }
    if (url.pathname === '/v1/audit') {
      const [schedule, attempts, imported, heartbeat] = await Promise.all([
        env.DB.prepare(`SELECT s.*, p.status AS program_candidate_status,
            p.failure_code AS program_candidate_failure_code,
            f.status AS six_finish_candidate_status,
            f.failure_code AS six_finish_candidate_failure_code
          FROM race_schedule s LEFT JOIN program_roster_candidate p ON s.race_id=p.race_id
          LEFT JOIN six_finish_candidate f ON s.race_id=f.race_id
          WHERE s.race_date=? ORDER BY s.deadline_ms LIMIT 288`).bind(date).all(),
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
