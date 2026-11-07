// Read-only daily quality interpretation. A successful HTTP call or a
// successful Action is NOT evidence that live previews, odds or BUY decisions
// exist. Missing preclose data remains UNAVAILABLE, never SKIP.
const fail = code => { throw new Error(`CLOUD_OPERATIONAL_AUDIT_${code}`); };
const int = (value, bound = 288) => Number.isInteger(value) && value >= 0 && value <= bound;
const ratio = (n, d) => d > 0 ? n / d : null;

export function summarizeOperationalDay(audit) {
  if (audit?.schema_version !== 1 || !/^\d{4}-\d{2}-\d{2}$/.test(audit.date ?? '') ||
      !Number.isFinite(Date.parse(audit.observed_at)) ||
      !int(audit.scheduled_races) || !int(audit.deadlines_passed) ||
      audit.deadlines_passed > audit.scheduled_races ||
      !int(audit.import?.count) || !int(audit.capture?.complete_observations) ||
      !int(audit.capture?.forecasts_ready) || !int(audit.capture?.buy) ||
      !int(audit.capture?.skip) || !int(audit.capture?.t8_attempts) ||
      !int(audit.capture?.t5_attempts) || !int(audit.results?.due) ||
      !int(audit.results?.recorded) || !int(audit.results?.unresolved_due) ||
      audit.results.due > audit.scheduled_races ||
      audit.results.recorded > audit.scheduled_races ||
      audit.results.unresolved_due > audit.results.due ||
      audit.capture.forecasts_ready > audit.capture.complete_observations ||
      audit.capture.complete_observations > audit.scheduled_races ||
      audit.capture.buy + audit.capture.skip !== audit.capture.forecasts_ready ||
      !['ACTIVE', 'STALE', 'NOT_OBSERVED'].includes(audit.cron?.status) ||
      (audit.import.count > 0 && audit.import.count !== audit.scheduled_races)) {
    fail('INVALID_CONTRACT');
  }
  const counts = audit.results;
  const knownResults = ['settled', 'unformed', 'postponed', 'cancelled', 'legacy_settled'];
  if (knownResults.some(key => !int(counts[key])) ||
      knownResults.reduce((sum, key) => sum + counts[key], 0) > counts.recorded) {
    fail('RESULT_INCONSISTENT');
  }
  if (!audit.capture_failure_codes || typeof audit.capture_failure_codes !== 'object' ||
      !audit.result_failure_codes || typeof audit.result_failure_codes !== 'object') {
    fail('FAILURE_CODES_MISSING');
  }
  const candidate = audit.program_roster_candidate;
  if (candidate && (!int(candidate.shape_complete_unverified) || !int(candidate.unavailable) ||
      !int(candidate.not_checked) || candidate.shape_complete_unverified + candidate.unavailable +
      candidate.not_checked !== audit.scheduled_races ||
      candidate.source_timestamp_verified !== 0 || candidate.eligible_for_forecast !== 0 ||
      !candidate.failure_codes || typeof candidate.failure_codes !== 'object')) {
    fail('PROGRAM_CANDIDATE_INCONSISTENT');
  }

  const scheduleStatus = audit.scheduled_races === 0 ?
    (audit.import.failure_code ? 'SCHEDULE_IMPORT_FAILED' : 'NO_SCHEDULE_OBSERVED') :
    audit.import.count === audit.scheduled_races ? 'IMPORTED' : 'IMPORT_NOT_RECONCILED';
  const resultStatus = counts.due === 0 ? 'NOT_YET_DUE' :
    counts.unresolved_due > 0 ? 'RESULTS_INCOMPLETE' : 'ALL_DUE_RESULTS_RECORDED';
  const precloseStatus = audit.scheduled_races === 0 ? 'NO_SCHEDULE_OBSERVED' :
    audit.capture.complete_observations === audit.scheduled_races ? 'OBSERVATIONS_VERIFIED' :
      audit.deadlines_passed === 0 ? 'NOT_YET_DUE' : 'PRECLOSE_UNAVAILABLE';
  // BUY/SKIP denotes genuine audited decisions only. Absent decisions must
  // never be counted as SKIP or counted in a hit-rate denominator.
  const recommendationStatus = audit.capture.forecasts_ready > 0 ? 'RECORDED' : 'UNAVAILABLE';

  return {
    date: audit.date, observed_at: audit.observed_at,
    scheduled_races: audit.scheduled_races, deadlines_passed: audit.deadlines_passed,
    import: { status: scheduleStatus, count: audit.import.count,
      failure_code: audit.import.failure_code ?? null },
    cron: { status: audit.cron.status, last_completed_at: audit.cron.last_completed_at ?? null,
      last_error_code: audit.cron.last_error_code ?? null },
    preclose: { status: precloseStatus, verified: audit.capture.complete_observations,
      t8_attempts: audit.capture.t8_attempts, t5_attempts: audit.capture.t5_attempts,
      coverage_of_scheduled: ratio(audit.capture.complete_observations, audit.scheduled_races),
      failure_codes: audit.capture_failure_codes },
    recommendations: { status: recommendationStatus, buy: audit.capture.buy,
      skip: audit.capture.skip, unavailable_excluded: true },
    program_roster_candidate: candidate ? {
      status: 'SHAPE_ONLY_UNVERIFIED', complete: candidate.shape_complete_unverified,
      unavailable: candidate.unavailable, not_checked: candidate.not_checked,
      eligible_for_forecast: 0, failure_codes: candidate.failure_codes,
    } : { status: 'NOT_OBSERVED', complete: 0, unavailable: 0,
      not_checked: audit.scheduled_races, eligible_for_forecast: 0, failure_codes: {} },
    results: { status: resultStatus, due: counts.due, recorded: counts.recorded,
      unresolved_due: counts.unresolved_due, settled: counts.settled,
      unformed: counts.unformed, postponed: counts.postponed,
      cancelled: counts.cancelled, legacy_settled: counts.legacy_settled,
      due_coverage: ratio(counts.due - counts.unresolved_due, counts.due),
      failure_codes: audit.result_failure_codes },
  };
}

// An untrusted rolling research BAH1 can be used for a COUNTS-ONLY audit,
// never to certify nationwide coverage, activate a checkpoint, or forecast.
// Each historical race contributes exactly six racer appearances. A matching
// count is necessary but NEVER sufficient for per-race completeness.
export function compareHistoryCandidateCounts(day, state) {
  if (!state || !Number.isInteger(state.lastDay) || !Number.isInteger(state.updateRaces) ||
      !state.recent || typeof state.recent !== 'object') fail('CANDIDATE_INVALID');
  const ordinal = Math.trunc(Date.parse(`${day.date}T00:00:00Z`) / 86_400_000) + 719_163;
  const terminalSettled = day.results.settled + day.results.legacy_settled;
  const base = { source: 'RESEARCH_CANDIDATE_NOT_CERTIFIED',
    history_last_day_ordinal: state.lastDay, date_ordinal: ordinal, terminal_settled: terminalSettled };
  if (state.lastDay < ordinal) return { ...base, candidate_races: null,
    terminal_minus_candidate: null, status: 'CANDIDATE_NOT_UPDATED' };
  let appearances = 0;
  for (const player of Object.values(state.recent)) {
    if (!Array.isArray(player.days)) fail('CANDIDATE_INVALID');
    appearances += player.days.filter(value => value === ordinal).length;
  }
  if (appearances % 6 !== 0) fail('CANDIDATE_APPEARANCE_INCONSISTENT');
  const candidate = appearances / 6;
  if (candidate > 288) fail('CANDIDATE_OVERSIZED');
  const difference = terminalSettled - candidate;
  return { ...base, candidate_races: candidate, terminal_minus_candidate: difference,
    status: difference === 0 ? 'COUNT_MATCH_BUT_UNCERTIFIED' : 'COUNT_DISCREPANCY_UNCERTIFIED' };
}

export function buildOperationalReport(yesterday, today, candidateHistory = null) {
  const older = summarizeOperationalDay(yesterday);
  const newer = summarizeOperationalDay(today);
  const milliseconds = Date.parse(`${newer.date}T00:00:00Z`) - Date.parse(`${older.date}T00:00:00Z`);
  if (milliseconds !== 86_400_000 || Date.parse(older.observed_at) > Date.parse(newer.observed_at) + 30_000) {
    fail('DAY_PAIR_MISMATCH');
  }
  if (candidateHistory) for (const day of [older, newer]) {
    day.history_candidate = compareHistoryCandidateCounts(day, candidateHistory);
  }
  return { schema_version: 1, audit_type: 'READ_ONLY_POSTED_CLOUD_EVIDENCE',
    created_at: new Date().toISOString(), days: [older, newer],
    note: 'Does not certify nationwide history completeness or live provider licensing. Successful Action is not a BUY/ROI sample.' };
}

export function operationalMarkdown(report) {
  const lines = ['## BOAT AI D1 cloud acquisition audit', '',
    '| JST day | Schedule | Cron | Program shape only (UNVERIFIED) | Preclose verified/scheduled | AI BUY/SKIP | Result due coverage |',
    '| --- | --- | --- | --- | --- | --- | --- |'];
  for (const day of report.days) {
    const coverage = day.results.due_coverage == null ? 'N/A' : `${(day.results.due_coverage * 100).toFixed(1)}%`;
    const p = day.program_roster_candidate;
    lines.push(`| ${day.date} | ${day.scheduled_races} (${day.import.status}) | ${day.cron.status} | ${p.complete}/${day.scheduled_races} (${p.status}) | ${day.preclose.verified}/${day.scheduled_races} (${day.preclose.status}) | ${day.recommendations.buy}/${day.recommendations.skip} (${day.recommendations.status}) | ${coverage} (${day.results.status}) |`);
  }
  lines.push('', 'Incomplete preclose/forecast data is **UNAVAILABLE**, not SKIP. Missing history/permission cannot be inferred from HTTP success.');
  if (report.days.some(day => day.history_candidate)) {
    lines.push('', '### Research history count comparison (NOT a completeness certificate)');
    for (const day of report.days) if (day.history_candidate) {
      const h = day.history_candidate;
      lines.push(`- ${day.date}: candidate ${h.candidate_races ?? 'not updated'}, terminal settled ${h.terminal_settled}; ${h.status}, difference ${h.terminal_minus_candidate ?? 'N/A'}.`);
    }
  }
  return `${lines.join('\n')}\n`;
}
