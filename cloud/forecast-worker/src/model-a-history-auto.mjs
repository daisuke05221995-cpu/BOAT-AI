// Strict automatic, day-by-day Model A history promotion from an explicitly
// authorized full-national-history feed. No public write endpoint, no source
// configured by default, no use of research-only history or sealed holdouts.
import { japanDate, isValidDate } from './policy.mjs';
import { sourceTime } from './preclose.mjs';
import { reconcileModelAHistoryDay } from './model-a-daily-reconcile.mjs';
import { FROZEN_ANDROID_HISTORY_BASE, loadVerifiedHistoryCheckpoint,
  sealReconciledHistoryDay, stageHistoryCheckpoint,
  activateVerifiedHistoryCheckpoint } from './model-a-history-store.mjs';

const DAY_MS = 86_400_000;
const RETRY_MS = 60 * 60_000;
const MIN_HISTORY_DAY = FROZEN_ANDROID_HISTORY_BASE.throughDay + 1;
const HEX = /^[0-9a-f]{64}$/;
const KINDS = ['coverage', 'schedule', 'roster', 'preview', 'weather', 'result'];
const fail = code => { throw new Error(`MODEL_A_HISTORY_AUTO_${code}`); };
const ordinalDate = day => new Date((day - 719_163) * DAY_MS).toISOString().slice(0, 10);
const matchesSource = (allow, kind, source) => allow?.[kind]?.includes(source) === true;

export function parseHistorySourceApprovals(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  let allow;
  try { allow = JSON.parse(value); } catch { fail('APPROVALS_INVALID'); }
  if (!allow || Array.isArray(allow) || typeof allow !== 'object' ||
      KINDS.some(kind => !Array.isArray(allow[kind]) || !allow[kind].length ||
        !allow[kind].every(source => typeof source === 'string' && source.length > 0 && source.length <= 100))) {
    fail('APPROVALS_INVALID');
  }
  return allow;
}

function utcTime(value) {
  if (typeof value !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(value)) fail('SOURCE_TIME_MISSING');
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) fail('SOURCE_TIME_INVALID');
  return ms;
}

// Historical BAH1 updates use true pre-close input, not post-result snapshots.
// The provider must have persisted original observation AND capture clocks.
export function verifyHistoricalDailyFeed(feed, date, nowMs, approvals) {
  if (!isValidDate(date) || !approvals || !feed || typeof feed !== 'object') fail('FEED_UNAVAILABLE');
  const manifest = feed.manifest;
  const races = feed.races;
  if (manifest?.date !== date || !Array.isArray(races) ||
      races.length < 1 || races.length > 288 ||
      !matchesSource(approvals, 'coverage', manifest.coverageSource) ||
      !matchesSource(approvals, 'schedule', manifest.scheduleSource) ||
      !matchesSource(approvals, 'result', manifest.resultSource) ||
      manifest.coverageStatus !== 'NATIONAL_ALL_VENUES_COMPLETE' ||
      manifest.expectedRaceCount !== races.length) fail('NATIONAL_MANIFEST_UNVERIFIED');
  // Source publishing a count cannot attest the day before the day ends JST.
  const coverageMs = utcTime(manifest.coverageConfirmedAt);
  const closingMs = Date.parse(`${date}T00:00:00+09:00`) + DAY_MS;
  if (coverageMs < closingMs || coverageMs > nowMs ||
      utcTime(manifest.confirmedAt) < closingMs || utcTime(manifest.confirmedAt) > nowMs) {
    fail('NATIONAL_MANIFEST_NOT_FINAL');
  }
  const seenIds = new Set();
  for (const race of races) {
    if (race?.date !== date || typeof race.raceId !== 'string' || seenIds.has(race.raceId)) fail('RACE_ID_DUPLICATE_OR_MISSING');
    seenIds.add(race.raceId);
    const e = race.sourceEvidence;
    if (!e || !matchesSource(approvals, 'result', e.resultSource) ||
        typeof e.resultRecordId !== 'string' || !/^[\w.:/-]{6,180}$/.test(e.resultRecordId) ||
        e.resultRaceId !== race.raceId || !Number.isFinite(race.deadlineMs)) fail('RESULT_EVIDENCE_UNVERIFIED');
    const resultObserved = utcTime(e.resultObservedAt);
    if (resultObserved <= race.deadlineMs || resultObserved > nowMs || resultObserved > coverageMs) {
      fail('RESULT_OBSERVED_TIME_INVALID');
    }
    if (race.result?.status !== 'SETTLED') continue;
    const byLane = [...(Array.isArray(race.racers) ? race.racers : [])]
      .sort((a, b) => (a?.lane ?? 0) - (b?.lane ?? 0));
    if (!matchesSource(approvals, 'roster', e.rosterSource) ||
        !matchesSource(approvals, 'preview', e.previewSource) ||
        !matchesSource(approvals, 'weather', e.weatherSource) ||
        !Array.isArray(e.registrationNumbersByLane) || e.registrationNumbersByLane.length !== 6 ||
        byLane.length !== 6 ||
        byLane.some((r, index) => r?.lane !== index + 1 ||
          !Number.isInteger(r.registrationNumber) ||
          r.registrationNumber !== e.registrationNumbersByLane[index])) fail('PRECLOSE_IDENTITY_UNVERIFIED');
    const capturedMs = utcTime(e.capturedAt);
    if (capturedMs >= race.deadlineMs || capturedMs > nowMs) fail('PRECLOSE_CAPTURE_AFTER_DEADLINE');
    sourceTime(e.rosterObservedAt, capturedMs, race.deadlineMs, 'HISTORY_ROSTER');
    sourceTime(e.previewObservedAt, capturedMs, race.deadlineMs, 'HISTORY_PREVIEW');
    sourceTime(e.weatherObservedAt, capturedMs, race.deadlineMs, 'HISTORY_WEATHER');
  }
  return { manifest, races };
}

async function fetchDailyFeed(env, date) {
  const url = new URL(env.HISTORY_DAILY_FEED_URL);
  if (url.protocol !== 'https:' || !url.hostname) fail('FEED_MUST_BE_HTTPS');
  url.searchParams.set('date', date);
  const headers = env.HISTORY_DAILY_FEED_TOKEN ?
    { authorization: `Bearer ${env.HISTORY_DAILY_FEED_TOKEN}` } : {};
  const response = await fetch(url.toString(), { headers, signal: AbortSignal.timeout(12_000) });
  if (!response.ok) fail(`FEED_HTTP_${response.status}`);
  return response.json();
}

async function crossCheckKnownSchedule(db, date, expectedIds) {
  const { results: rows } = await db.prepare('SELECT race_id FROM race_schedule WHERE race_date=? LIMIT 289')
    .bind(date).all();
  if (!rows?.length) return;
  const expected = new Set(expectedIds);
  if (rows.length !== expected.size || rows.some(row => !expected.has(row.race_id))) {
    fail('LOCAL_SCHEDULE_DISAGREES_WITH_MANIFEST');
  }
}

export async function promoteHistoricalDay(db, date, nowMs, feed, approvals,
  previousSha256, loadCheckpoint = loadVerifiedHistoryCheckpoint,
  stageCheckpoint = stageHistoryCheckpoint, activateCheckpoint = activateVerifiedHistoryCheckpoint) {
  const { manifest, races } = verifyHistoricalDailyFeed(feed, date, nowMs, approvals);
  await crossCheckKnownSchedule(db, date, manifest.scheduledRaceIds);
  const previous = await loadCheckpoint(db, previousSha256);
  const { state, audit } = reconcileModelAHistoryDay(previous.state, manifest, races, nowMs);
  const checkpoint = await sealReconciledHistoryDay({ state, audit }, previousSha256);
  try { await stageCheckpoint(db, checkpoint); }
  catch (error) {
    // A successful stage followed by a crashed invocation can be retried:
    // never overwrite, only accept an identical fully verified generation.
    let existing;
    try { existing = await loadCheckpoint(db, checkpoint.sha256); } catch { throw error; }
    if (existing.sha256 !== checkpoint.sha256 || existing.previousSha256 !== previousSha256 ||
        existing.throughDay !== checkpoint.throughDay) throw error;
  }
  const verified = await loadCheckpoint(db, checkpoint.sha256);
  if (verified.sha256 !== checkpoint.sha256 || verified.throughDay !== checkpoint.throughDay ||
      verified.previousSha256 !== previousSha256) fail('STAGED_ASSET_MISMATCH');
  // Bootstrap the exact frozen Android base only AFTER a full first-day
  // candidate has been checked. Never activate recent research BAH1 here.
  const active = await db.prepare('SELECT * FROM model_a_history_active WHERE singleton=1').first();
  if (!active && previousSha256 === FROZEN_ANDROID_HISTORY_BASE.sha256) {
    await activateCheckpoint(db, previousSha256, nowMs);
  }
  await activateCheckpoint(db, checkpoint.sha256, nowMs);
  return { sha256: checkpoint.sha256, expectedRaces: audit.expectedRaces,
    committedRaces: audit.committedRaces };
}

export async function runAutomaticHistoryCatchup(env, nowMs = Date.now(),
  download = fetchDailyFeed, promote = promoteHistoricalDay) {
  if (!env.HISTORY_DAILY_FEED_URL || !env.HISTORY_APPROVED_SOURCES_JSON) return { status: 'DISABLED' };
  let approvals;
  try { approvals = parseHistorySourceApprovals(env.HISTORY_APPROVED_SOURCES_JSON); }
  catch { return { status: 'DISABLED', reason: 'HISTORY_APPROVALS_INVALID' }; }
  const active = await env.DB.prepare('SELECT * FROM model_a_history_active WHERE singleton=1').first();
  const lastDay = active?.through_day ?? FROZEN_ANDROID_HISTORY_BASE.throughDay;
  const sha256 = active?.sha256 ?? FROZEN_ANDROID_HISTORY_BASE.sha256;
  if (!HEX.test(sha256) || !Number.isInteger(lastDay) || lastDay < MIN_HISTORY_DAY - 1) {
    return { status: 'DISABLED', reason: 'HISTORY_POINTER_INVALID' };
  }
  const targetDay = lastDay + 1;
  const date = ordinalDate(targetDay);
  if (date >= japanDate(nowMs)) return { status: 'UP_TO_DATE' };
  // The Workers minute-cron should not make repeated licensed feed calls
  // while the source is down. CAS-style claim also protects overlapping runs.
  const claimed = await env.DB.prepare(`INSERT INTO model_a_history_day_attempt
    (race_date, last_started_ms, status) VALUES (?, ?, 'RUNNING')
    ON CONFLICT(race_date) DO UPDATE SET last_started_ms=excluded.last_started_ms,
      last_finished_ms=NULL, status='RUNNING', reason=NULL
    WHERE model_a_history_day_attempt.status!='PROMOTED'
      AND model_a_history_day_attempt.last_started_ms <= ?`)
    .bind(date, nowMs, nowMs - RETRY_MS).run();
  if (claimed.meta?.changes !== 1) return { status: 'RATE_LIMITED', date };
  try {
    const feed = await download(env, date);
    const result = await promote(env.DB, date, Date.now(), feed, approvals, sha256);
    await env.DB.prepare(`UPDATE model_a_history_day_attempt SET
      status='PROMOTED', last_finished_ms=?, reason=NULL, promoted_sha256=?,
      expected_races=?, committed_races=? WHERE race_date=? AND last_started_ms=?`)
      .bind(Date.now(), result.sha256, result.expectedRaces, result.committedRaces, date, nowMs).run();
    return { status: 'PROMOTED', date, ...result };
  } catch (error) {
    const reason = String(error?.message ?? 'UNKNOWN').slice(0, 120);
    await env.DB.prepare(`UPDATE model_a_history_day_attempt SET
      status='UNAVAILABLE', last_finished_ms=?, reason=?
      WHERE race_date=? AND last_started_ms=?`)
      .bind(Date.now(), reason, date, nowMs).run();
    return { status: 'UNAVAILABLE', date, reason };
  }
}
