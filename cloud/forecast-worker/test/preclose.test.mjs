import test from 'node:test';
import assert from 'node:assert/strict';
import {
  verifiedOddsPayload, verifiedPreviewPayload, verifiedStoredCapture,
} from '../src/preclose.mjs';
import { serializeForecast } from '../src/worker.mjs';

const now = Date.parse('2026-11-06T03:52:00Z');
const row = {
  race_id: '2026-11-06-01-1', race_date: '2026-11-06', stadium_number: 1, race_number: 1,
  deadline_ms: now + 8 * 60_000, capture_stage: 2,
};
const racers = Object.fromEntries(Array.from({ length: 6 }, (_, index) => [String(index + 1), {
  course_number: index + 1, exhibition_time: 6.75,
}]));
const preview = { date: row.race_date, stadium_number: 1, race_number: 1, racers };
const odds = Object.fromEntries(Array.from({ length: 6 }, (_, a) => a + 1)
  .flatMap(a => Array.from({ length: 6 }, (_, b) => b + 1)
    .flatMap(b => Array.from({ length: 6 }, (_, c) => c + 1)
      .filter(c => a !== b && a !== c && b !== c)
      .map(c => [`${a}-${b}-${c}`, 12.5]))));
const payload = (kind, content, observed_at = new Date(now - 30_000).toISOString()) => ({
  date: row.race_date, stadium_number: 1, race_number: 1,
  source: `authorized-${kind}`, observed_at, [kind]: content,
});

test('six unique course observations and all 120 trifecta odds are accepted', () => {
  const p = verifiedPreviewPayload(payload('preview', preview), row, now);
  const o = verifiedOddsPayload(payload('odds', odds), row, now);
  assert.equal(p.observedMs, now - 30_000);
  assert.equal(o.observedMs, now - 30_000);
  const stored = { ...row, captured_ms: now,
    preview_json: JSON.stringify(p.preview), preview_source: p.source, preview_observed_ms: p.observedMs,
    odds_json: JSON.stringify(o.odds), odds_source: o.source, odds_observed_ms: o.observedMs,
  };
  assert.equal(verifiedStoredCapture(stored), true);
  assert.equal(serializeForecast({ ...stored, model_version: 'model-a', decision: 'SKIP',
    forecast_json: '{"combinations":[],"stakes":[]}' }, now).status, 'READY');
});

test('missing 1 trifecta entry fails closed before model use', () => {
  const partial = { ...odds };
  delete partial['6-5-4'];
  assert.throws(() => verifiedOddsPayload(payload('odds', partial), row, now), /ODDS_NOT_COMPLETE/);
});

test('wrong race, incomplete exhibition, or undeclared source cannot be accepted', () => {
  assert.throws(() => verifiedPreviewPayload({ ...payload('preview', preview), race_number: 2 }, row, now), /PREVIEW_WRONG_RACE/);
  assert.throws(() => verifiedPreviewPayload(payload('preview', { ...preview, racers: { ...racers, 6: { course_number: 1, exhibition_time: 6.75 } } }), row, now), /PREVIEW_NOT_COMPLETE/);
  assert.throws(() => verifiedPreviewPayload({ ...payload('preview', preview), source: '' }, row, now), /PREVIEW_SOURCE_MISSING/);
  assert.throws(() => verifiedOddsPayload({ ...payload('odds', odds), stadium_number: 2 }, row, now), /ODDS_WRONG_RACE/);
});

test('provider timestamps must be present, fresh, before close, and not in the future', () => {
  assert.throws(() => verifiedPreviewPayload(payload('preview', preview, ''), row, now), /PREVIEW_TIME_MISSING/);
  assert.throws(() => verifiedPreviewPayload(payload('preview', preview, new Date(now - 120_001).toISOString()), row, now), /PREVIEW_STALE/);
  assert.throws(() => verifiedOddsPayload(payload('odds', odds, new Date(now + 20_000).toISOString()), row, now), /ODDS_TIME_IN_FUTURE/);
  assert.throws(() => verifiedOddsPayload(payload('odds', odds, new Date(row.deadline_ms).toISOString()), row, now), /ODDS_POST_CLOSE/);
});

test('legacy, unverified and post-close cached data cannot make a BUY/READY', () => {
  const stored = { ...row, captured_ms: now, preview_source: 'authorized-preview',
    preview_json: JSON.stringify(preview), odds_json: JSON.stringify(odds), odds_source: 'authorized-odds',
    forecast_json: '{"combinations":["1-2-3"],"stakes":[100]}', model_version: 'model-a', decision: 'BUY' };
  assert.equal(verifiedStoredCapture(stored), false);
  assert.equal(serializeForecast(stored, now).status, 'UNAVAILABLE');
  assert.deepEqual(serializeForecast(stored, now).quality_flags, ['CAPTURE_NOT_VERIFIED']);
  const afterClose = { ...stored, preview_observed_ms: now - 10_000,
    odds_observed_ms: now - 10_000, captured_ms: row.deadline_ms };
  assert.equal(verifiedStoredCapture(afterClose), false);
  assert.equal(serializeForecast(afterClose, row.deadline_ms).status, 'UNAVAILABLE');
});
