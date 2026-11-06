// Offline-only parser for the published boatraceopenapi v1 JSON *shape*.
// This is NOT a licensed live-feed adapter, national-schedule certification,
// or permission to backfill history. Do not call this from Worker cron.
import { isValidDate, raceId } from './policy.mjs';

const fail = code => { throw new Error(`MODEL_A_HISTORICAL_${code}`); };
const numeric = value => typeof value === 'number' && Number.isFinite(value) ? value : null;
const required = value => {
  const number = numeric(value);
  if (number === null) fail('PRERACE_INPUT_MISSING');
  return number;
};

function verifyRaceIdentity(obj, date, stadium, race, kind) {
  if (!obj || obj.date !== date || obj.stadium_number !== stadium || obj.race_number !== race) {
    fail(`${kind}_IDENTITY_MISMATCH`);
  }
}

function normalizeSettledRace(raw, date, stadium, number) {
  const program = raw.racers;
  if (!program || typeof program !== 'object' || Object.keys(program).length !== 6) fail('PROGRAM_ROSTER_MISSING');
  const preview = raw.preview;
  const result = raw.result;
  verifyRaceIdentity(preview, date, stadium, number, 'PREVIEW');
  verifyRaceIdentity(result, date, stadium, number, 'RESULT');
  if (!preview.racers || Object.keys(preview.racers).length !== 6 ||
      !result.racers || Object.keys(result.racers).length !== 6) fail('SIX_BOATS_MISSING');
  const courses = new Set(), players = new Set(), finish = new Map();
  const racers = [];
  for (let lane = 1; lane <= 6; lane++) {
    const key = String(lane);
    const p = program[key], e = preview.racers[key], r = result.racers[key];
    if (!p || !e || !r || p.entry_number !== lane || e.entry_number !== lane ||
        r.entry_number !== lane || !Number.isInteger(p.number) || p.number <= 0 ||
        r.number !== p.number || players.has(p.number)) fail('RACER_ID_MISMATCH');
    if (!Number.isInteger(e.course_number) || e.course_number < 1 || e.course_number > 6 ||
        courses.has(e.course_number)) fail('COURSE_MISMATCH');
    if (!Number.isInteger(r.place_number) || r.place_number < 1 || r.place_number > 6 ||
        finish.has(r.place_number)) fail('FINISH_ORDER_UNAVAILABLE');
    const ex = required(e.exhibition_time), st = required(e.start_timing);
    if (ex <= 0 || ex > 30 || st < -5 || st > 5) fail('PRERACE_INPUT_INVALID');
    players.add(p.number);
    courses.add(e.course_number);
    finish.set(r.place_number, lane);
    racers.push({
      lane, registrationNumber: p.number, classNumber: Number.isInteger(p.rank_number) ? p.rank_number : null,
      nationalWinRate: required(p.national_win_rate),
      nationalTop2: numeric(p.national_top_2_percent), nationalTop3: numeric(p.national_top_3_percent),
      localWinRate: numeric(p.local_win_rate), localTop2: numeric(p.local_top_2_percent),
      localTop3: numeric(p.local_top_3_percent),
      motorTop2: numeric(p.motor_top_2_percent), motorTop3: numeric(p.motor_top_3_percent),
      boatTop2: numeric(p.boat_top_2_percent), boatTop3: numeric(p.boat_top_3_percent),
      averageStart: numeric(p.average_start_timing), flyingCount: numeric(p.flying_count),
      lateCount: numeric(p.late_count), age: numeric(p.age), weight: numeric(p.weight),
      preview: { course: e.course_number, exhibitionTime: ex, startTiming: st,
        tilt: numeric(e.tilt_adjustment), weightAdjustment: numeric(e.weight_adjustment) },
    });
  }
  // Never use race-result weather/ST/position as pre-race features.
  const weather = ['wind_speed', 'wave_height', 'air_temperature', 'water_temperature'];
  if (weather.some(key => numeric(preview[key]) === null) ||
      preview.wind_speed < 0 || preview.wind_speed > 60 ||
      preview.wave_height < 0 || preview.wave_height > 200 ||
      preview.air_temperature < -50 || preview.air_temperature > 65 ||
      preview.water_temperature < -5 || preview.water_temperature > 50 ||
      !Number.isInteger(preview.wind_direction_number) ||
      preview.wind_direction_number < 0 || preview.wind_direction_number > 16 ||
      (preview.wind_direction_number === 0 && preview.wind_speed !== 0)) fail('PREVIEW_WEATHER_MISSING');
  return {
    date, stadiumNumber: stadium, raceNumber: number, raceId: raceId(date, stadium, number),
    racers, preview: {
      windSpeed: preview.wind_speed, waveHeight: preview.wave_height,
      airTemperature: preview.air_temperature, waterTemperature: preview.water_temperature,
      windDirectionNumber: preview.wind_direction_number,
    },
    result: { status: 'SETTLED', finishOrder: Array.from({ length: 6 }, (_, i) => finish.get(i + 1)) },
  };
}

export function normalizeHistoricalDayCandidate(feed, date) {
  if (!isValidDate(date)) fail('DATE_INVALID');
  const stadiums = feed?.programs?.stadiums;
  if (!stadiums || typeof stadiums !== 'object' || Array.isArray(stadiums)) fail('SCHEDULE_MISSING');
  const races = [], keys = new Set();
  for (const [stadiumKey, venue] of Object.entries(stadiums)) {
    const stadium = Number(stadiumKey);
    if (!Number.isInteger(stadium) || stadium < 1 || stadium > 24 ||
        !venue?.races || typeof venue.races !== 'object') fail('SCHEDULE_INVALID');
    for (const [raceKey, raw] of Object.entries(venue.races)) {
      const number = Number(raceKey), id = raceId(date, stadium, number);
      if (!id || keys.has(id)) fail('SCHEDULE_DUPLICATE');
      keys.add(id);
      verifyRaceIdentity(raw, date, stadium, number, 'PROGRAM');
      const cancelled = raw.day_number_source === '中止' || raw.day_number_source === '順延';
      if (cancelled) {
        races.push({ date, stadiumNumber: stadium, raceNumber: number, raceId: id,
          result: { status: 'CANCELLED', reason: raw.day_number_source } });
      } else {
        races.push(normalizeSettledRace(raw, date, stadium, number));
      }
    }
  }
  if (!races.length || races.length > 288) fail('SCHEDULE_EMPTY_OR_OVERSIZED');
  races.sort((a, b) => a.stadiumNumber - b.stadiumNumber || a.raceNumber - b.raceNumber);
  return {
    races,
    candidateRaceIds: races.map(r => r.raceId),
    audit: { status: 'SOURCE_COVERAGE_UNVERIFIED', date, observedRaces: races.length,
      settledRaces: races.filter(r => r.result.status === 'SETTLED').length,
      cancelledRaces: races.filter(r => r.result.status === 'CANCELLED').length,
      warning: 'Input format check only; no independent nationwide coverage or preclose timestamp proof' },
  };
}
