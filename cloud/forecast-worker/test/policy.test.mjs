import test from 'node:test';
import assert from 'node:assert/strict';
import {
  EIGHT_MIN, FIVE_MIN, japanDate, parseJstDeadline, raceId,
  isValidDate, extractSchedule, nextCaptureStage, nextResultStage, validOdds,
} from '../src/policy.mjs';
import { dailyImportDue, serializeForecast } from '../src/worker.mjs';

const deadline = Date.parse('2026-11-06T13:00:00+09:00');

test('JST time is independent of server timezone and date', () => {
  assert.equal(parseJstDeadline('2026-11-06 13:00:00'), deadline);
  assert.equal(japanDate(Date.parse('2026-11-05T16:00:00Z')), '2026-11-06');
  assert.equal(parseJstDeadline('2026-02-30 13:00:00'), null);
  assert.equal(parseJstDeadline('2026-11-06T13:00:00Z'), null);
  assert.equal(parseJstDeadline(''), null);
});

test('race IDs match Android race IDs including venue zero padding', () => {
  assert.equal(raceId('2026-11-06', 1, 2), '2026-11-06-01-2');
  assert.equal(raceId('2026-11-06', 24, 12), '2026-11-06-24-12');
  assert.equal(raceId('2026-11-06', 25, 1), null);
  assert.equal(raceId('2026-11-06', 1, 13), null);
});

test('invalid and impossible dates are rejected', () => {
  assert.equal(isValidDate('2026-11-06'), true);
  assert.equal(isValidDate('2026-02-30'), false);
  assert.equal(isValidDate('2026-11-06xxx'), false);
  assert.equal(isValidDate(null), false);
});

test('T-8 exactly once; T-5 only after failed first attempt', () => {
  const first = { capture_stage: 0, deadline_ms: deadline };
  const retriable = { capture_stage: 1, deadline_ms: deadline };
  const completed = { capture_stage: 2, deadline_ms: deadline };
  assert.equal(nextCaptureStage(first, deadline - EIGHT_MIN - 1), null);
  assert.equal(nextCaptureStage(first, deadline - EIGHT_MIN), 1);
  assert.equal(nextCaptureStage(retriable, deadline - EIGHT_MIN + 1), null);
  assert.equal(nextCaptureStage(retriable, deadline - FIVE_MIN - 1), null);
  assert.equal(nextCaptureStage(retriable, deadline - FIVE_MIN), 2);
  assert.equal(nextCaptureStage(first, deadline - FIVE_MIN), 2); // missed T-8
  assert.equal(nextCaptureStage(completed, deadline - FIVE_MIN), null);
  assert.equal(nextCaptureStage(retriable, deadline), null);
});

test('result collection starts after 20 minutes, one fallback after 45', () => {
  assert.equal(nextResultStage({ result_stage: 0, deadline_ms: deadline }, deadline + 20 * 60_000 - 1), null);
  assert.equal(nextResultStage({ result_stage: 0, deadline_ms: deadline }, deadline + 20 * 60_000), 1);
  assert.equal(nextResultStage({ result_stage: 1, deadline_ms: deadline }, deadline + 44 * 60_000), null);
  assert.equal(nextResultStage({ result_stage: 1, deadline_ms: deadline }, deadline + 45 * 60_000), 2);
  assert.equal(nextResultStage({ result_stage: 2, deadline_ms: deadline }, deadline + 46 * 60_000), null);
});

test('schedule parsing preserves only complete date-matched races', () => {
  const payload = { programs: { stadiums: { 1: { races: {
    1: { date: '2026-11-06', closed_at: '2026-11-06 13:00:00' },
    2: { date: '2026-11-05', closed_at: '2026-11-06 13:30:00' },
    3: { date: '2026-11-06', closed_at: '' },
  } } } } };
  assert.deepEqual(extractSchedule(payload, '2026-11-06'), [{
    race_id: '2026-11-06-01-1', race_date: '2026-11-06',
    stadium_number: 1, race_number: 1, deadline_ms: deadline,
  }]);
});

test('incomplete odds can never mark a race actionable', () => {
  const complete = {};
  for (let a = 1; a <= 6; a++) for (let b = 1; b <= 6; b++) for (let c = 1; c <= 6; c++) {
    if (a !== b && b !== c && a !== c) complete[`${a}-${b}-${c}`] = 10.1;
  }
  assert.equal(Object.keys(complete).length, 120);
  assert.equal(validOdds({ odds: complete }), true);
  assert.equal(validOdds({ odds: { '1-2-3': 10.1 } }), false);
  assert.equal(validOdds({ odds: { ...complete, '1-1-2': 1 } }), false);
  assert.equal(validOdds({ odds: { ...complete, '1-2-3': 0 } }), false);
});

test('daily schedule is imported once after 06 JST; missing source gets hourly retry', () => {
  const at7 = Date.parse('2026-11-06T07:00:00+09:00');
  const at21 = Date.parse('2026-11-06T21:00:00+09:00');
  const before6 = Date.parse('2026-11-06T05:59:00+09:00');
  const nextDay = Date.parse('2026-11-07T01:00:00+09:00');
  assert.equal(dailyImportDue('2026-11-06', at7, null), true);
  assert.equal(dailyImportDue('2026-11-06', at21, null), true); // late deploy recovery
  assert.equal(dailyImportDue('2026-11-06', before6, null), false);
  assert.equal(dailyImportDue('2026-11-06', nextDay, null), false);
  assert.equal(dailyImportDue('2026-11-06', at7, { last_attempt_ms: at7 - 50_000, race_count: 0 }), false);
  assert.equal(dailyImportDue('2026-11-06', at7, { last_attempt_ms: at7 - 3_600_000, race_count: 0 }), true);
  assert.equal(dailyImportDue('2026-11-06', at7, { last_attempt_ms: at7 - 3_600_000, race_count: 120 }), false);
});

test('no model means no READY/BUY even when preclose odds were saved', () => {
  const record = { race_id: '2026-11-06-01-1', deadline_ms: deadline,
    capture_stage: 2, captured_ms: deadline - 6 * 60_000,
    odds_source: 'provider', odds_json: '{"1-2-3":10}',
    model_version: null, forecast_json: null, decision: null, failure_code: null };
  const serialized = serializeForecast(record, deadline - 4 * 60_000);
  assert.equal(serialized.status, 'UNAVAILABLE');
  assert.equal(serialized.decision, null);
  assert.deepEqual(serialized.quality_flags, ['MODEL_NOT_DEPLOYED']);
  assert.deepEqual(serialized.combinations, []);
});

test('even a model field cannot make a post-close observation READY', () => {
  const row = { race_id: '2026-11-06-01-1', deadline_ms: deadline, capture_stage: 2,
    captured_ms: deadline + 1, model_version: 'v0.16', decision: 'BUY',
    forecast_json: '{"combinations":["1-2-3"],"stakes":[100]}', failure_code: null };
  assert.equal(serializeForecast(row, deadline + 2).status, 'UNAVAILABLE');
  assert.equal(serializeForecast(row, deadline + 2).decision, null);
});
