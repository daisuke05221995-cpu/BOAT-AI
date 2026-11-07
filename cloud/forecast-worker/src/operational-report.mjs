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
    results: { status: resultStatus, due: counts.due, recorded: counts.recorded,
      unresolved_due: counts.unresolved_due, settled: counts.settled,
      unformed: counts.unformed, postponed: counts.postponed,
      cancelled: counts.cancelled, legacy_settled: counts.legacy_settled,
      due_coverage: ratio(counts.due - counts.unresolved_due, counts.due),
      failure_codes: audit.result_failure_codes },
  };
}

export function buildOperationalReport(yesterday, today) {
  const older = summarizeOperationalDay(yesterday);
  const newer = summarizeOperationalDay(today);
  const milliseconds = Date.parse(`${newer.date}T00:00:00Z`) - Date.parse(`${older.date}T00:00:00Z`);
  if (milliseconds !== 86_400_000 || Date.parse(older.observed_at) > Date.parse(newer.observed_at) + 30_000) {
    fail('DAY_PAIR_MISMATCH');
  }
  return { schema_version: 1, audit_type: 'READ_ONLY_POSTED_CLOUD_EVIDENCE',
    created_at: new Date().toISOString(), days: [older, newer],
    note: 'Does not certify nationwide history completeness or live provider licensing. Successful Action is not a BUY/ROI sample.' };
}

export function operationalMarkdown(report) {
  const lines = ['## BOAT AI D1 cloud acquisition audit', '',
    '| JST day | Schedule | Cron | Preclose verified/scheduled | AI BUY/SKIP | Result due coverage |',
    '| --- | --- | --- | --- | --- | --- |'];
  for (const day of report.days) {
    const coverage = day.results.due_coverage == null ? 'N/A' : `${(day.results.due_coverage * 100).toFixed(1)}%`;
    lines.push(`| ${day.date} | ${day.scheduled_races} (${day.import.status}) | ${day.cron.status} | ${day.preclose.verified}/${day.scheduled_races} (${day.preclose.status}) | ${day.recommendations.buy}/${day.recommendations.skip} (${day.recommendations.status}) | ${coverage} (${day.results.status}) |`);
  }
  lines.push('', 'Incomplete preclose/forecast data is **UNAVAILABLE**, not SKIP. Missing history/permission cannot be inferred from HTTP success.');
  return `${lines.join('\n')}\n`;
}
