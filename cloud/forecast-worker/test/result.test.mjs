import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizePublishedResult, resultRetryDue } from '../src/result.mjs';

const row = { race_date: '2026-11-07', stadium_number: 3, race_number: 2,
  deadline_ms: Date.parse('2026-11-07T02:25:00Z') };
const base = { date: row.race_date, stadium_number: row.stadium_number,
  race_number: row.race_number, day_number_source: '3日目' };
const reported = (...trifecta) => ({ ...base, result: {
  date: row.race_date, stadium_number: row.stadium_number,
  race_number: row.race_number, payouts: { trifecta },
} });

test('normal verified result keeps exact payout and all combinations for ties', () => {
  const standard = normalizePublishedResult(reported({ combination: '1-4-5', amount: 6240 }), row);
  assert.deepEqual(standard, { status: 'SETTLED', trifecta_combination: '1-4-5',
    trifecta_payout: 6240, trifecta_payouts: [{ combination: '1-4-5', payout: 6240 }] });
  const tied = normalizePublishedResult(reported(
    { combination: '1-4-5', amount: 6240 }, { combination: '1-5-4', amount: 5940 }), row);
  assert.equal(tied.status, 'SETTLED');
  assert.equal(tied.trifecta_combination, null);
  assert.equal(tied.trifecta_payouts.length, 2);
});

test('non-formation refunds never invent a winning combination', () => {
  const returned = normalizePublishedResult(reported({ combination: null, amount: 100, label: '不成立' }), row);
  assert.deepEqual(returned, { status: 'UNFORMED', trifecta_combination: null,
    trifecta_payout: null, refund_per_100: 100 });
  assert.equal(normalizePublishedResult(reported({ combination: null, amount: 0, label: '不成立' }), row), null);
});

test('explicitly postponed and cancelled races terminate without fictitious results', () => {
  assert.equal(normalizePublishedResult({ ...base, result: null, day_number_source: '順延' }, row).status, 'POSTPONED');
  assert.equal(normalizePublishedResult({ ...reported(), day_number_source: '順延' }, row).status, 'POSTPONED');
  assert.equal(normalizePublishedResult({ ...base, result: null, day_number_source: '中止' }, row).status, 'CANCELLED');
  assert.equal(normalizePublishedResult({ ...reported({ combination: '1-2-3', amount: 500 }),
    day_number_source: '順延' }, row), null);
  assert.equal(normalizePublishedResult({ ...base, result: null }, row), null);
});

test('wrong date, venue, race, partial payout and malformed combinations are rejected', () => {
  assert.equal(normalizePublishedResult({ ...reported({ combination: '1-2-3', amount: 500 }), date: '2026-11-06' }, row), null);
  assert.equal(normalizePublishedResult({ ...reported({ combination: '1-2-3', amount: 500 }), result: { date: row.race_date, stadium_number: 2, race_number: 2 } }, row), null);
  assert.equal(normalizePublishedResult(reported({ combination: '1-1-2', amount: 500 }), row), null);
  assert.equal(normalizePublishedResult(reported({ combination: '1-2-3', amount: 0 }), row), null);
  assert.equal(normalizePublishedResult(reported({ combination: '1-2-3', amount: 500 }, { combination: null, amount: 100, label: '不成立' }), row), null);
});

test('result retry allows legacy exhausted stages but respects cutoff and backoff', () => {
  const nowMs = row.deadline_ms + 60 * 60_000;
  assert.equal(resultRetryDue({ ...row, result_stage: 2 }, nowMs), true);
  assert.equal(resultRetryDue({ ...row, result_stage: 2, result_last_attempt_ms: nowMs - 14 * 60_000 }, nowMs), false);
  assert.equal(resultRetryDue({ ...row, result_stage: 1, result_last_attempt_ms: nowMs - 15 * 60_000 }, nowMs), true);
  assert.equal(resultRetryDue({ ...row, result_json: '{"status":"SETTLED"}' }, nowMs), false);
  assert.equal(resultRetryDue({ ...row }, row.deadline_ms + 19 * 60_000), false);
});
