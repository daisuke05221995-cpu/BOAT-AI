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
  course_number: index + 1, exhibition_time: 6.75, start_timing: 0.12,
}]));
const preview = { date: row.race_date, stadium_number: 1, race_number: 1, racers,
  wind_speed: 2, wave_height: 3, air_temperature: 19, water_temperature: 17,
  wind_direction_number: 5, weather_source: 'licensed-weather',
  weather_observed_at: new Date(now - 30_000).toISOString(),
};
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
  assert.equal(p.weatherObservedMs, now - 30_000);
  assert.equal(o.observedMs, now - 30_000);
  const stored = { ...row, captured_ms: now,
    preview_json: JSON.stringify(p.preview), preview_source: p.source, preview_observed_ms: p.observedMs,
    weather_source: p.weatherSource, weather_observed_ms: p.weatherObservedMs,
    odds_json: JSON.stringify(o.odds), odds_source: o.source, odds_observed_ms: o.observedMs,
  };
  assert.equal(verifiedStoredCapture(stored), true);
  assert.equal(verifiedStoredCapture({ ...stored, weather_observed_ms: now - 29_000 }), false);
  const served = serializeForecast({ ...stored, model_version: 'model-a', decision: 'SKIP',
    forecast_json: '{"combinations":[],"stakes":[]}' }, now);
  assert.equal(served.status, 'READY');
  assert.equal(served.weather_source, 'licensed-weather');
  assert.equal(served.weather_observed_at, new Date(now - 30_000).toISOString());
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

test('missing preview ST or weather is incomplete, never silently promoted', () => {
  const missingSt = structuredClone(preview);
  delete missingSt.racers['3'].start_timing;
  assert.throws(() => verifiedPreviewPayload(payload('preview', missingSt), row, now), /PREVIEW_NOT_COMPLETE/);
  const missingWind = { ...preview, wind_speed: undefined };
  assert.throws(() => verifiedPreviewPayload(payload('preview', missingWind), row, now), /PREVIEW_NOT_COMPLETE/);
  const noWeatherTime = { ...preview, weather_observed_at: undefined };
  assert.throws(() => verifiedPreviewPayload(payload('preview', noWeatherTime), row, now), /WEATHER_TIME_MISSING/);
  assert.throws(() => verifiedPreviewPayload(payload('preview', { ...preview, weather_source: '' }), row, now), /WEATHER_SOURCE_MISSING/);
  assert.throws(() => verifiedPreviewPayload(payload('preview', { ...preview,
    weather_observed_at: new Date(now - 120_001).toISOString() }), row, now), /WEATHER_STALE/);
});

test('calm wind is explicit, negative flying exhibition ST is valid, non-finite values are not', () => {
  const calm = { ...preview, wind_speed: 0, wind_direction_number: 0,
    racers: { ...racers, 1: { ...racers['1'], start_timing: -0.03 } } };
  assert.ok(verifiedPreviewPayload(payload('preview', calm), row, now));
  const impossible = { ...calm, racers: { ...calm.racers, 1: { ...calm.racers['1'], start_timing: Infinity } } };
  assert.throws(() => verifiedPreviewPayload(payload('preview', impossible), row, now), /PREVIEW_NOT_COMPLETE/);
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
