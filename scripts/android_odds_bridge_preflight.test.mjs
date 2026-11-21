import test from 'node:test';
import assert from 'node:assert/strict';
import { assessAndroidOddsSnapshot, expectedTrifectaCombinations } from './android_odds_bridge_preflight.mjs';

const deadline = Date.parse('2026-11-08T06:00:00Z'); // 15:00 JST
const received = deadline - 480_000;
const odds = () => expectedTrifectaCombinations().map((combination, index) => ({
  combination, decimal_odds: 1.1 + index / 10,
}));
const sample = () => ({
  schema_version: 1, race_date: '2026-11-08', stadium_number: 1,
  race_number: 5, deadline_ms: deadline, device_received_ms: received,
  source_observed_ms: null, source_id: 'android_official_local',
  odds: odds(),
});
const check = (value, now = received + 1_000) => assessAndroidOddsSnapshot(value, now);
const deny = (value, code, now) => {
  const result = check(value, now);
  assert.equal(result.accepted, false);
  assert.equal(result.reason, code);
  assert.equal(result.eligible_for_forecast, false);
  assert.equal(result.eligible_for_buy, false);
};

test('canonical 3-way combinations cover exactly 120 with no duplicates', () => {
  const keys = expectedTrifectaCombinations();
  assert.equal(keys.length, 120);
  assert.equal(new Set(keys).size, 120);
  assert.ok(keys.includes('1-2-3'));
  assert.ok(keys.includes('6-5-4'));
  assert.equal(keys.includes('1-1-2'), false);
});
test('full device odds remain quarantined and not BUY even at T8', () => {
  const result = check(sample());
  assert.equal(result.accepted, true);
  assert.equal(result.classification, 'DEVICE_ODDS_QUARANTINED');
  assert.equal(result.stage, 'T8_WINDOW');
  assert.equal(result.normalized_odds.length, 120);
  assert.equal(result.eligible_for_forecast, false);
  assert.equal(result.eligible_for_buy, false);
  assert.equal(result.source_observed_ms_claimed, null);
  assert.equal(result.source_time_independently_verified, false);
});
test('self-reported observation timestamp does not become independent verification', () => {
  const input = sample(); input.source_observed_ms = received - 1_000;
  const result = check(input);
  assert.equal(result.accepted, true);
  assert.equal(result.source_time_independently_verified, false);
  assert.equal(result.source_rights_independently_verified, false);
});
test('T5 window is distinguishable from T8 without implying usable forecast', () => {
  const input = sample(); input.device_received_ms = deadline - 300_000;
  const result = check(input, input.device_received_ms + 1_000);
  assert.equal(result.stage, 'T5_WINDOW');
  assert.equal(result.eligible_for_buy, false);
});
test('119 odds are never treated as complete', () => {
  const input = sample(); input.odds.pop();
  deny(input, 'ODDS_NOT_120');
});
test('duplicate combination cannot replace a missing combination', () => {
  const input = sample(); input.odds[119] = { ...input.odds[0] };
  deny(input, 'INVALID_ODDS_ROW');
});
test('zero, negative, infinite and non-numeric odds are rejected', () => {
  for (const value of [0, -1, Infinity, NaN, '3.1']) {
    const input = sample(); input.odds[0].decimal_odds = value;
    deny(input, 'INVALID_ODDS_ROW');
  }
});
test('unknown / malformed combination is rejected', () => {
  const input = sample(); input.odds[0].combination = '1-1-2';
  deny(input, 'INVALID_ODDS_ROW');
});
test('extra sensitive payload fields are rejected at root and row', () => {
  const input = sample(); input.account_id = 'never-send';
  deny(input, 'INVALID_SCHEMA_OR_EXTRA_FIELD');
  const row = sample(); row.odds[0].user_token = 'never-send';
  deny(row, 'INVALID_ODDS_ROW');
});
test('claimed approval flags cannot be used to certify licensing', () => {
  const input = sample(); input.permission_verified = true;
  deny(input, 'INVALID_SCHEMA_OR_EXTRA_FIELD');
});
test('missing source timestamp must be explicitly null, never device-time fallback', () => {
  const input = sample(); delete input.source_observed_ms;
  deny(input, 'SOURCE_TIME_INVALID_OR_STALE');
});
test('future source timestamp relative to device receipt is rejected', () => {
  const input = sample(); input.source_observed_ms = received + 5_000;
  deny(input, 'SOURCE_TIME_INVALID_OR_STALE');
});
test('stale claimed source timestamp is rejected', () => {
  const input = sample(); input.source_observed_ms = received - 121_000;
  deny(input, 'SOURCE_TIME_INVALID_OR_STALE');
});
test('late device and server ingestion cannot become pre-close evidence', () => {
  const input = sample(); input.device_received_ms = deadline;
  deny(input, 'AFTER_CLOSE_OR_LATE_SERVER_INGEST', deadline + 1_000);
  deny(sample(), 'AFTER_CLOSE_OR_LATE_SERVER_INGEST', deadline);
});
test('stale or future device clocks fail', () => {
  deny(sample(), 'DEVICE_CLOCK_UNTRUSTWORTHY_OR_STALE', received + 121_000);
  deny(sample(), 'DEVICE_CLOCK_UNTRUSTWORTHY_OR_STALE', received - 6_000);
});
test('mismatched JST race date and illegal race identity fail', () => {
  const wrong = sample(); wrong.race_date = '2026-11-07';
  deny(wrong, 'INVALID_RACE_IDENTITY');
  const bad = sample(); bad.race_number = 13;
  deny(bad, 'INVALID_RACE_IDENTITY');
});
test('invalid source labels cannot inject arbitrary data', () => {
  const input = sample(); input.source_id = 'secret@email.test';
  deny(input, 'INVALID_SOURCE_LABEL');
});
test('invalid data schema and missing numeric clocks fail', () => {
  deny(null, 'INVALID_SCHEMA_OR_EXTRA_FIELD');
  const input = sample(); input.deadline_ms = '06:00';
  deny(input, 'INVALID_CLOCK');
});
