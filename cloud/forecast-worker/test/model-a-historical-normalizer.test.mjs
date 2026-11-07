import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeHistoricalDayCandidate } from '../src/model-a-historical-normalizer.mjs';
import { ModelAPlayerHistory } from '../src/model-a-history.mjs';
import { buildModelAFeatures } from '../src/model-a-features.mjs';

const date = '2026-11-06';
const record = () => ({
  date, stadium_number: 1, race_number: 1, day_number_source: '初日',
  racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
    entry_number: i + 1, number: 3000 + i, rank_number: 3, national_win_rate: 5.6,
    national_top_2_percent: 30, national_top_3_percent: 50,
    local_win_rate: 4.5, local_top_2_percent: 25, local_top_3_percent: 45,
    motor_top_2_percent: 31, motor_top_3_percent: 51, boat_top_2_percent: 29,
    boat_top_3_percent: 49, average_start_timing: 0.17, flying_count: 0,
    late_count: 0, age: 31, weight: 52,
  }])),
  preview: { date, stadium_number: 1, race_number: 1,
    wind_speed: 2, wind_direction_number: 3, wave_height: 2,
    air_temperature: 17, water_temperature: 15,
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
      entry_number: i + 1, course_number: i + 1, exhibition_time: 6.7 + i / 100,
      start_timing: 0.11 + i / 100, tilt_adjustment: 0, weight_adjustment: 0,
    }])),
  },
  result: { date, stadium_number: 1, race_number: 1,
    // These post-race values must never be used by the pre-race feature builder.
    wind_speed: 99, air_temperature: 99,
    racers: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(i + 1), {
      entry_number: i + 1, number: 3000 + i, course_number: 6 - i,
      start_timing: -0.99, place_number: i + 1,
    }])),
  },
});
const feed = race => ({ programs: { stadiums: { '1': { races: { '1': race } } } } });

test('offline historical candidate preserves pre-race fields and racer-ID verified finish order', () => {
  const candidate = normalizeHistoricalDayCandidate(feed(record()), date);
  assert.deepEqual(candidate.candidateRaceIds, [`${date}-01-1`]);
  assert.equal(candidate.audit.status, 'SOURCE_COVERAGE_UNVERIFIED');
  assert.deepEqual(candidate.races[0].result.finishOrder, [1, 2, 3, 4, 5, 6]);
  assert.equal(candidate.races[0].racers[0].preview.startTiming, 0.11);
  assert.equal(candidate.races[0].racers[0].preview.course, 1);
  assert.equal(candidate.races[0].preview.windSpeed, 2);
  const history = new ModelAPlayerHistory({ stats: {}, recent: {}, lastDay: 739925, updateRaces: 0 });
  assert.equal(buildModelAFeatures(candidate.races[0], history).usable, true);
});

test('result IDs, duplicate finishing places, missing ST and preview weather fail closed', () => {
  const wrongPlayer = record();
  wrongPlayer.result.racers['2'].number = 9999;
  assert.throws(() => normalizeHistoricalDayCandidate(feed(wrongPlayer), date), /RACER_ID_MISMATCH/);
  const tied = record();
  tied.result.racers['2'].place_number = 1;
  assert.throws(() => normalizeHistoricalDayCandidate(feed(tied), date), /FINISH_ORDER_UNAVAILABLE/);
  const noPreviewSt = record();
  delete noPreviewSt.preview.racers['2'].start_timing;
  assert.throws(() => normalizeHistoricalDayCandidate(feed(noPreviewSt), date), /PRERACE_INPUT_MISSING/);
  const noPreviewWeather = record();
  noPreviewWeather.preview.wind_speed = null;
  assert.throws(() => normalizeHistoricalDayCandidate(feed(noPreviewWeather), date), /PREVIEW_WEATHER_MISSING/);
});

test('a missing result cannot be marked as a cancellation without explicit source evidence', () => {
  const missing = record();
  missing.result = null;
  assert.throws(() => normalizeHistoricalDayCandidate(feed(missing), date), /RESULT_IDENTITY_MISMATCH/);
  missing.day_number_source = '中止';
  const candidate = normalizeHistoricalDayCandidate(feed(missing), date);
  assert.equal(candidate.audit.cancelledRaces, 1);
  assert.deepEqual(candidate.races[0].result, { status: 'CANCELLED', reason: '中止' });
});

test('wrong-day, duplicate venue/race keys and empty schedule are rejected', () => {
  const wrong = record();
  wrong.preview.date = '2026-11-05';
  assert.throws(() => normalizeHistoricalDayCandidate(feed(wrong), date), /PREVIEW_IDENTITY_MISMATCH/);
  assert.throws(() => normalizeHistoricalDayCandidate({ programs: { stadiums: {} } }, date), /SCHEDULE_EMPTY_OR_OVERSIZED/);
  const duplicate = { programs: { stadiums: { '1': { races: { '1': record() } },
    '01': { races: { '1': record() } } } } };
  assert.throws(() => normalizeHistoricalDayCandidate(duplicate, date), /SCHEDULE_DUPLICATE/);
});
