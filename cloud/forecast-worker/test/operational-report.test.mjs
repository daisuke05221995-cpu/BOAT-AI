import test from 'node:test';
import assert from 'node:assert/strict';
import { summarizeDailyAudit } from '../src/audit.mjs';
import { summarizeOperationalDay, buildOperationalReport,
  operationalMarkdown } from '../src/operational-report.mjs';

const nowMs = Date.parse('2026-11-08T01:20:00Z');
const earlier = '2026-11-07';
const later = '2026-11-08';
const observation = (date, rows = [], importedCount = rows.length) =>
  summarizeDailyAudit(date, nowMs, rows, [], { race_count: importedCount }, {
    last_started_ms: nowMs - 60_000, last_completed_ms: nowMs - 55_000,
    started_count: 100, completed_count: 99,
  });
const race = (name, date, extras = {}) => ({
  race_id: name, race_date: date, deadline_ms: nowMs - 40 * 60_000,
  capture_stage: 2, preview_json: null, odds_json: null,
  forecast_json: null, model_version: null, decision: null,
  result_json: null, result_recorded_ms: null,
  ...extras,
});

test('read-only daily report keeps no preclose data UNAVAILABLE, never calls it SKIP', () => {
  const raw = observation(earlier, [
    race('one', earlier, { result_json: JSON.stringify({ status: 'SETTLED' }),
      result_recorded_ms: nowMs - 1_000 }),
    race('two', earlier, { result_failure_code: 'RESULT_NOT_FINAL' }),
  ]);
  const report = summarizeOperationalDay(raw);
  assert.equal(report.scheduled_races, 2);
  assert.equal(report.preclose.status, 'PRECLOSE_UNAVAILABLE');
  assert.equal(report.preclose.coverage_of_scheduled, 0);
  assert.equal(report.recommendations.status, 'UNAVAILABLE');
  assert.deepEqual([report.recommendations.buy, report.recommendations.skip], [0, 0]);
  assert.equal(report.recommendations.unavailable_excluded, true);
  assert.equal(report.results.status, 'RESULTS_INCOMPLETE');
  assert.equal(report.results.due_coverage, 0.5);
  assert.equal(report.results.failure_codes.RESULT_NOT_FINAL, 1);
});

test('complete terminal results include cancellation and unformed without making a BUY record', () => {
  const raw = observation(earlier, [
    race('one', earlier, { result_json: JSON.stringify({ status: 'POSTPONED' }), result_recorded_ms: nowMs }),
    race('two', earlier, { result_json: JSON.stringify({ status: 'UNFORMED' }), result_recorded_ms: nowMs }),
  ]);
  const day = summarizeOperationalDay(raw);
  assert.deepEqual([day.results.status, day.results.due_coverage,
    day.results.postponed, day.results.unformed], ['ALL_DUE_RESULTS_RECORDED', 1, 1, 1]);
  assert.equal(day.recommendations.status, 'UNAVAILABLE');
});

test('contract inconsistency or spoofed date pairs fail closed', () => {
  const raw = observation(earlier, [race('r1', earlier)]);
  assert.throws(() => summarizeOperationalDay({ ...raw, capture: {
    ...raw.capture, buy: 1, forecasts_ready: 0,
  } }), /INVALID_CONTRACT/);
  assert.throws(() => summarizeOperationalDay({ ...raw,
    import: { ...raw.import, count: 7 },
  }), /INVALID_CONTRACT/);
  assert.throws(() => summarizeOperationalDay({ ...raw,
    results: { ...raw.results, settled: 2 },
  }), /RESULT_INCONSISTENT/);
  assert.throws(() => buildOperationalReport(raw, raw), /DAY_PAIR_MISMATCH/);
});

test('two-date artifact reports accurate collection gates in Actions summary', () => {
  const report = buildOperationalReport(observation(earlier), observation(later));
  assert.equal(report.days.length, 2);
  assert.equal(report.days[0].import.status, 'NO_SCHEDULE_OBSERVED');
  assert.equal(report.days[0].results.due_coverage, null);
  assert.ok(operationalMarkdown(report).includes('UNAVAILABLE'));
  assert.ok(operationalMarkdown(report).includes(earlier));
});
