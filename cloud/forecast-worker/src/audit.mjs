import { verifiedStoredCapture } from './preclose.mjs';

const iso = value => Number.isFinite(value) ? new Date(value).toISOString() : null;

export function summarizeDailyAudit(date, nowMs, races = [], attempts = [], imported = null, heartbeat = null) {
  const failures = {};
  const captures = {
    t8_attempts: 0, t5_attempts: 0, running_attempts: 0,
    preview_observed: 0, odds_observed: 0, complete_observations: 0,
    forecasts_ready: 0, buy: 0, skip: 0,
    missed_after_deadline: 0, due_without_attempt: 0,
  };
  const results = {
    due: 0, recorded: 0, settled: 0, unformed: 0,
    postponed: 0, cancelled: 0, legacy_settled: 0, unresolved_due: 0,
  };
  const resultFailures = {};
  const programCandidate = {
    shape_complete_unverified: 0, unavailable: 0, not_checked: 0,
    source_timestamp_verified: 0, eligible_for_forecast: 0,
    failure_codes: {},
  };
  let deadlinesPassed = 0;
  let firstDeadline = null;
  let lastDeadline = null;

  for (const row of races) {
    if (row.program_candidate_status === 'SHAPE_ONLY_UNVERIFIED') {
      programCandidate.shape_complete_unverified++;
    } else if (row.program_candidate_status === 'UNAVAILABLE') {
      programCandidate.unavailable++;
      const reason = String(row.program_candidate_failure_code ?? 'UNKNOWN').slice(0, 100);
      programCandidate.failure_codes[reason] = (programCandidate.failure_codes[reason] ?? 0) + 1;
    } else {
      programCandidate.not_checked++;
    }
    const deadline = Number(row.deadline_ms);
    if (!Number.isFinite(deadline)) continue;
    firstDeadline = firstDeadline == null ? deadline : Math.min(firstDeadline, deadline);
    lastDeadline = lastDeadline == null ? deadline : Math.max(lastDeadline, deadline);
    if (row.preview_json) captures.preview_observed++;
    if (row.odds_json) captures.odds_observed++;
    const complete = verifiedStoredCapture(row);
    if (complete) captures.complete_observations++;
    const ready = complete && !!row.forecast_json && !!row.model_version &&
      (row.decision === 'BUY' || row.decision === 'SKIP');
    if (ready) {
      captures.forecasts_ready++;
      if (row.decision === 'BUY') captures.buy++;
      if (row.decision === 'SKIP') captures.skip++;
    }
    if (nowMs >= deadline) {
      deadlinesPassed++;
      if (!complete) captures.missed_after_deadline++;
    } else if (nowMs >= deadline - 8 * 60_000 && row.capture_stage === 0) {
      captures.due_without_attempt++;
    }
    const resultDue = nowMs >= deadline + 20 * 60_000;
    if (resultDue) results.due++;
    if (row.result_json && row.result_recorded_ms) {
      results.recorded++;
      let terminal;
      try { terminal = JSON.parse(row.result_json); } catch { terminal = null; }
      const key = ({ SETTLED: 'settled', UNFORMED: 'unformed',
        POSTPONED: 'postponed', CANCELLED: 'cancelled' })[terminal?.status];
      if (key) results[key]++;
      else if (terminal?.trifecta_combination) results.legacy_settled++;
    } else if (resultDue) {
      results.unresolved_due++;
      if (row.result_failure_code) {
        const code = String(row.result_failure_code).slice(0, 100);
        resultFailures[code] = (resultFailures[code] ?? 0) + 1;
      }
    }
  }

  for (const attempt of attempts) {
    if (attempt.stage === 1) captures.t8_attempts++;
    if (attempt.stage === 2) captures.t5_attempts++;
    if (attempt.finished_ms == null) captures.running_attempts++;
    if (attempt.failure_code) {
      const code = String(attempt.failure_code).slice(0, 100);
      failures[code] = (failures[code] ?? 0) + 1;
    }
  }

  const lastCompleted = heartbeat?.last_completed_ms ?? null;
  const cron = {
    status: !heartbeat ? 'NOT_OBSERVED' :
      !Number.isFinite(lastCompleted) || nowMs - lastCompleted > 5 * 60_000 ? 'STALE' : 'ACTIVE',
    last_started_at: iso(heartbeat?.last_started_ms),
    last_completed_at: iso(lastCompleted),
    started_count: heartbeat?.started_count ?? 0,
    completed_count: heartbeat?.completed_count ?? 0,
    last_error_code: heartbeat?.last_error_code ?? null,
  };
  return {
    schema_version: 1, date, observed_at: iso(nowMs),
    scheduled_races: races.length, deadlines_passed: deadlinesPassed,
    first_deadline_at: iso(firstDeadline), last_deadline_at: iso(lastDeadline),
    import: {
      last_attempt_at: iso(imported?.last_attempt_ms),
      last_success_at: iso(imported?.last_success_ms),
      count: imported?.race_count ?? 0,
      failure_code: imported?.failure_code ?? null,
    },
    cron, capture: captures, results, program_roster_candidate: programCandidate,
    capture_failure_codes: failures,
    result_failure_codes: resultFailures,
  };
}
