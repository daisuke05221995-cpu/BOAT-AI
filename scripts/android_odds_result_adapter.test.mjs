import test from 'node:test';
import assert from 'node:assert/strict';
import { inspectExistingAndroidOddsResult } from './android_odds_result_adapter.mjs';
import { expectedTrifectaCombinations } from './android_odds_bridge_preflight.mjs';

const close = Date.parse('2026-11-08T06:00:00Z'); // 15:00 JST
const fetchedAt = close - 480_000; // T-8 on the device
const race = () => ({
  date: '2026-11-08', stadiumNumber: 1, raceNumber: 5, deadlineMs: close,
});
const full = () => ({
  odds: Object.fromEntries(expectedTrifectaCombinations().map((key, index) => [key, 1.1 + index / 10])),
  source: '公式PC版',
  diagnostics: [{ source: '公式PC版', status: 'OK', detail: 'fixture, not real data' }],
  fetchedAt,
});
const evalAndroid = (result, raceRecord = race(), now = fetchedAt + 1000) =>
  inspectExistingAndroidOddsResult(result, raceRecord, now);
test('full Android official-PC map is quarantined, never BUY or SKIP', () => {
  const q = evalAndroid(full());
  assert.equal(q.accepted, true);
  assert.equal(q.classification, 'DEVICE_ODDS_QUARANTINED');
  assert.equal(q.normalized_odds.length, 120);
  assert.equal(q.eligible_for_forecast, false);
  assert.equal(q.eligible_for_buy, false);
  assert.equal(q.provenance_status, 'ANDROID_RECEIPT_ONLY');
});
test('selected-only odds map (six picks) is not a full snapshot', () => {
  const s = full();
  s.odds = Object.fromEntries(Object.entries(s.odds).slice(0, 6));
  assert.equal(evalAndroid(s).reason, 'ANDROID_SELECTED_ODDS_NOT_120');
});
test('119 entries is incomplete even if the selected picks succeed', () => {
  const s = full(); delete s.odds['6-5-4'];
  assert.equal(evalAndroid(s).reason, 'ANDROID_SELECTED_ODDS_NOT_120');
});
test('120 estimated BoatraceCSV fallback odds are never treated as live official prices', () => {
  const s = full();
  s.source = 'BoatraceCSV約5分前→出走時推定v1';
  assert.equal(evalAndroid(s).reason, 'ESTIMATED_OR_FALLBACK_ODDS_NOT_LIVE');
});
test('unverified labels are not allowed even if they contain official text', () => {
  const s = full(); s.source = '公式PC版 - verified by device';
  assert.equal(evalAndroid(s).reason, 'UNKNOWN_ODDS_SOURCE');
});
test('official smartphone source recognized but observation timestamp remains unknown', () => {
  const s = full(); s.source = '公式スマホ版';
  const x = evalAndroid(s);
  assert.equal(x.accepted, true);
  assert.equal(x.source_observed_ms_claimed, null);
  assert.equal(x.source_time_independently_verified, false);
  assert.equal(x.source_rights_independently_verified, false);
});
test('diagnostics are not copied to transferable output', () => {
  const s = full(); s.diagnostics[0].detail = 'secret=do-not-export';
  const x = evalAndroid(s);
  assert.equal(JSON.stringify(x).includes('do-not-export'), false);
});
test('malformed odds result is rejected without guessing fields', () => {
  for (const bad of [null, {}, { ...full(), fetchedAt: 'today' }, { ...full(), odds: [] },
    { ...full(), diagnostics: null }]) {
    const x = evalAndroid(bad);
    assert.equal(x.classification, 'UNAVAILABLE');
    assert.equal(x.eligible_for_forecast, false);
  }
});
test('nonpositive and nonnumeric odds fail validation', () => {
  for (const bad of [-1, 0, NaN, '6.3']) {
    const s = full(); s.odds['1-2-3'] = bad;
    const x = evalAndroid(s);
    assert.equal(x.reason, 'INVALID_ODDS_ROW');
    assert.equal(x.eligible_for_buy, false);
  }
});
test('invalid combination key is rejected even with 120 entries', () => {
  const s = full(); delete s.odds['6-5-4']; s.odds['1-1-2'] = 99.9;
  assert.equal(evalAndroid(s).reason, 'INVALID_ODDS_ROW');
});
test('late server receipt means no pre-close capture', () => {
  assert.equal(evalAndroid(full(), race(), close + 100).reason, 'AFTER_CLOSE_OR_LATE_SERVER_INGEST');
});
test('stale Android receive timestamp is rejected; cannot backdate a pre-close capture', () => {
  assert.equal(evalAndroid(full(), race(), fetchedAt + 150_000).reason,
    'DEVICE_CLOCK_UNTRUSTWORTHY_OR_STALE');
});
test('invalid race date or venue cannot be silently fixed', () => {
  assert.equal(evalAndroid(full(), { ...race(), date: '2026-11-07' }).reason,
    'INVALID_RACE_IDENTITY');
  assert.equal(evalAndroid(full(), { ...race(), stadiumNumber: 25 }).reason,
    'INVALID_RACE_IDENTITY');
});
test('no official source observation time exists in Android result', () => {
  const s = full(); s.observed_at = '2026-11-08T05:59:00Z';
  const q = evalAndroid(s);
  assert.equal(q.source_observed_ms_claimed, null);
  assert.equal(q.source_time_independently_verified, false);
});
