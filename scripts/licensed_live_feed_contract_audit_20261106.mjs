#!/usr/bin/env node
// Offline audit of the existing capture contract. No network, data feeds, model,
// personal records, credentials, or historical holdout files are accessed.
// This records current validation behavior. PASS is not evidence of a licensed
// provider, real T-8 freshness, or successful live prediction.
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { verifiedPreviewPayload, verifiedOddsPayload } from '../cloud/forecast-worker/src/preclose.mjs';
import { nextCaptureStage } from '../cloud/forecast-worker/src/policy.mjs';

const now = Date.parse('2026-11-07T02:52:00Z'); // synthetic clock, not a live observation
const row = { race_date: '2026-11-07', stadium_number: 1, race_number: 1,
  deadline_ms: now + 480000 };
const envelope = { date: row.race_date, stadium_number: 1, race_number: 1,
  source: 'synthetic-not-live', observed_at: new Date(now).toISOString() };
const preview = { ...envelope, preview: { date: row.race_date, stadium_number: 1,
  race_number: 1, wind_speed: 2.1, wind_direction_number: 1, wave_height: 3,
  air_temperature: 21, water_temperature: 20,
  weather_source: 'synthetic-weather-not-live',
  weather_observed_at: new Date(now).toISOString(),
  racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) =>
    [String(i + 1), { course_number: i + 1, exhibition_time: 6.7 + i / 100,
      start_timing: 0.12 + i / 100 }])) } };
const odds = {};
for (let a = 1; a <= 6; a++) for (let b = 1; b <= 6; b++) for (let c = 1; c <= 6; c++)
  if (a !== b && a !== c && b !== c) odds[[a, b, c].join('-')] = 12.4;
const fullOdds = { ...envelope, odds };
const cases = [];
function check(id, run) {
  run(); // any unexpected behavior throws and exits nonzero
  cases.push({ id, result: 'PASS' });
}

check('complete_preview_with_st_weather_accepted', () =>
  assert.ok(verifiedPreviewPayload(preview, row, now)));
check('minimal_preview_without_st_weather_rejected', () => {
  const value = structuredClone(preview);
  delete value.preview.wind_speed;
  delete value.preview.racers['1'].start_timing;
  assert.throws(() => verifiedPreviewPayload(value, row, now), /PREVIEW_NOT_COMPLETE/);
});
check('missing_single_exhibition_st_rejected', () => {
  const value = structuredClone(preview);
  delete value.preview.racers['3'].start_timing;
  assert.throws(() => verifiedPreviewPayload(value, row, now), /PREVIEW_NOT_COMPLETE/);
});
check('missing_weather_measurement_rejected', () => {
  const value = structuredClone(preview);
  delete value.preview.water_temperature;
  assert.throws(() => verifiedPreviewPayload(value, row, now), /PREVIEW_NOT_COMPLETE/);
});
check('missing_weather_source_rejected', () => {
  const value = structuredClone(preview);
  delete value.preview.weather_source;
  assert.throws(() => verifiedPreviewPayload(value, row, now), /WEATHER_SOURCE_MISSING/);
});
check('missing_weather_observation_time_rejected', () => {
  const value = structuredClone(preview);
  delete value.preview.weather_observed_at;
  assert.throws(() => verifiedPreviewPayload(value, row, now), /WEATHER_TIME_MISSING/);
});
check('stale_weather_observation_rejected', () => {
  const value = structuredClone(preview);
  value.preview.weather_observed_at = new Date(now - 121000).toISOString();
  assert.throws(() => verifiedPreviewPayload(value, row, now), /WEATHER_STALE/);
});
check('future_weather_observation_rejected', () => {
  const value = structuredClone(preview);
  value.preview.weather_observed_at = new Date(now + 16000).toISOString();
  assert.throws(() => verifiedPreviewPayload(value, row, now), /WEATHER_TIME_IN_FUTURE/);
});
check('weather_observation_at_deadline_rejected', () => {
  const value = structuredClone(preview);
  value.observed_at = new Date(row.deadline_ms - 60000).toISOString();
  value.preview.weather_observed_at = new Date(row.deadline_ms).toISOString();
  assert.throws(() => verifiedPreviewPayload(value, row, row.deadline_ms - 1000), /WEATHER_POST_CLOSE/);
});
check('missing_source_time_rejected', () => assert.throws(() =>
  verifiedPreviewPayload({ ...preview, observed_at: null }, row, now), /PREVIEW_TIME_MISSING/));
check('source_age_121s_rejected', () => assert.throws(() =>
  verifiedPreviewPayload({ ...preview, observed_at: new Date(now - 121000).toISOString() }, row, now), /PREVIEW_STALE/));
check('source_age_120s_accepted', () => assert.ok(
  verifiedPreviewPayload({ ...preview, observed_at: new Date(now - 120000).toISOString() }, row, now)));
check('source_clock_16s_future_rejected', () => assert.throws(() =>
  verifiedPreviewPayload({ ...preview, observed_at: new Date(now + 16000).toISOString() }, row, now), /PREVIEW_TIME_IN_FUTURE/));
check('wrong_race_rejected', () => assert.throws(() =>
  verifiedPreviewPayload({ ...preview, race_number: 2 }, row, now), /PREVIEW_WRONG_RACE/));
check('duplicate_course_rejected', () => {
  const value = structuredClone(preview);
  value.preview.racers['6'].course_number = 1;
  assert.throws(() => verifiedPreviewPayload(value, row, now), /PREVIEW_NOT_COMPLETE/);
});
check('five_boats_rejected', () => {
  const value = structuredClone(preview);
  delete value.preview.racers['6'];
  assert.throws(() => verifiedPreviewPayload(value, row, now), /PREVIEW_NOT_COMPLETE/);
});
check('all_120_positive_odds_accepted', () => assert.equal(
  Object.keys(verifiedOddsPayload(fullOdds, row, now).odds).length, 120));
check('119_odds_rejected', () => {
  const value = structuredClone(fullOdds);
  delete value.odds['1-2-3'];
  assert.throws(() => verifiedOddsPayload(value, row, now), /ODDS_NOT_COMPLETE/);
});
check('zero_odds_rejected', () => {
  const value = structuredClone(fullOdds);
  value.odds['1-2-3'] = 0;
  assert.throws(() => verifiedOddsPayload(value, row, now), /ODDS_NOT_COMPLETE/);
});
check('at_deadline_source_observation_rejected', () => assert.throws(() =>
  verifiedOddsPayload({ ...fullOdds, observed_at: new Date(row.deadline_ms).toISOString() },
    row, row.deadline_ms), /ODDS_POST_CLOSE/));
check('t_minus_8_initial_stage', () =>
  assert.equal(nextCaptureStage({ ...row, capture_stage: 0 }, now), 1));
check('t_minus_5_retry_stage', () =>
  assert.equal(nextCaptureStage({ ...row, capture_stage: 1 }, row.deadline_ms - 300000), 2));
check('no_capture_at_deadline', () =>
  assert.equal(nextCaptureStage({ ...row, capture_stage: 0 }, row.deadline_ms), null));

const sourceFiles = ['cloud/forecast-worker/src/preclose.mjs', 'cloud/forecast-worker/src/policy.mjs']
  .map(path => ({ path, sha256: createHash('sha256')
    .update(readFileSync(new URL('../' + path, import.meta.url))).digest('hex') }));
console.log(JSON.stringify({
  schema_version: 1,
  kind: 'OFFLINE_SYNTHETIC_CONTRACT_AUDIT',
  executed_at: new Date().toISOString(),
  runtime: process.version,
  live_measurement: false,
  source_files: sourceFiles,
  case_count: cases.length,
  cases,
  findings: [
    'Current preview gate rejects missing exhibition ST, weather measurements, weather source and weather observation time.',
    'Offline shape and timestamp checks alone do not establish live feed licensing, T-8 availability or upstream timestamp authenticity.',
  ],
}, null, 2));
