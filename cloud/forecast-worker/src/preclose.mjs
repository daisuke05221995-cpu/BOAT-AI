import { validOdds } from './policy.mjs';

// A provider's observed_at means it actually observed the source's current
// exhibition/odds for this race then. It must not mean a cached HTTP response
// was served to the Worker at that time.
export const SOURCE_MAX_AGE_MS = 2 * 60_000;
const FUTURE_CLOCK_SKEW_MS = 15_000;

function sourceTime(value, nowMs, deadlineMs, kind) {
  if (typeof value !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(value)) {
    throw new Error(`${kind}_TIME_MISSING`);
  }
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) throw new Error(`${kind}_TIME_MISSING`);
  if (ms >= deadlineMs) throw new Error(`${kind}_POST_CLOSE`);
  if (ms > nowMs + FUTURE_CLOCK_SKEW_MS) throw new Error(`${kind}_TIME_IN_FUTURE`);
  if (nowMs - ms > SOURCE_MAX_AGE_MS) throw new Error(`${kind}_STALE`);
  return ms;
}

function validateIdentity(snapshot, row, kind) {
  if (snapshot?.date !== row.race_date ||
      snapshot?.stadium_number !== row.stadium_number ||
      snapshot?.race_number !== row.race_number) {
    throw new Error(`${kind}_WRONG_RACE`);
  }
  if (typeof snapshot.source !== 'string' || !snapshot.source.trim() || snapshot.source.length > 100) {
    throw new Error(`${kind}_SOURCE_MISSING`);
  }
}

export function validExhibition(preview, row) {
  if (!preview || typeof preview !== 'object' || !row ||
      preview.date !== row.race_date ||
      preview.stadium_number !== row.stadium_number ||
      preview.race_number !== row.race_number) return false;
  const racers = preview.racers;
  if (!racers || typeof racers !== 'object' || Object.keys(racers).length !== 6) return false;
  // Model A requires preview ST and pre-race weather, not just six exhibition
  // times. Missing fields must not be promoted to a complete T-8 capture.
  if (!Number.isFinite(preview.wind_speed) || preview.wind_speed < 0 || preview.wind_speed > 60 ||
      !Number.isFinite(preview.wave_height) || preview.wave_height < 0 || preview.wave_height > 200 ||
      !Number.isFinite(preview.air_temperature) || preview.air_temperature < -50 || preview.air_temperature > 65 ||
      !Number.isFinite(preview.water_temperature) || preview.water_temperature < -5 || preview.water_temperature > 50 ||
      !(Number.isInteger(preview.wind_direction_number) &&
        (preview.wind_direction_number >= 1 && preview.wind_direction_number <= 16 ||
         (preview.wind_direction_number === 0 && preview.wind_speed === 0)))) return false;
  const courses = new Set();
  for (let lane = 1; lane <= 6; lane++) {
    const racer = racers[String(lane)];
    if (!racer || !Number.isInteger(racer.course_number) ||
        racer.course_number < 1 || racer.course_number > 6 ||
        typeof racer.exhibition_time !== 'number' || !Number.isFinite(racer.exhibition_time) ||
        racer.exhibition_time <= 0 || racer.exhibition_time > 30 ||
        typeof racer.start_timing !== 'number' || !Number.isFinite(racer.start_timing) ||
        racer.start_timing < -5 || racer.start_timing > 5) return false;
    courses.add(racer.course_number);
  }
  return courses.size === 6;
}

export function verifiedPreviewPayload(snapshot, row, nowMs) {
  validateIdentity(snapshot, row, 'PREVIEW');
  const observedMs = sourceTime(snapshot.observed_at, nowMs, row.deadline_ms, 'PREVIEW');
  if (!validExhibition(snapshot.preview, row)) throw new Error('PREVIEW_NOT_COMPLETE');
  if (typeof snapshot.preview.weather_source !== 'string' ||
      !snapshot.preview.weather_source.trim() || snapshot.preview.weather_source.length > 100) {
    throw new Error('WEATHER_SOURCE_MISSING');
  }
  const weatherObservedMs = sourceTime(snapshot.preview.weather_observed_at, nowMs, row.deadline_ms, 'WEATHER');
  return { preview: snapshot.preview, source: snapshot.source, observedMs,
    weatherSource: snapshot.preview.weather_source, weatherObservedMs };
}

export function verifiedOddsPayload(snapshot, row, nowMs) {
  validateIdentity(snapshot, row, 'ODDS');
  const observedMs = sourceTime(snapshot.observed_at, nowMs, row.deadline_ms, 'ODDS');
  if (!validOdds(snapshot)) throw new Error('ODDS_NOT_COMPLETE');
  return { odds: snapshot.odds, source: snapshot.source, observedMs };
}

export function verifiedStoredCapture(row) {
  if (!row || !Number.isFinite(row.captured_ms) || row.captured_ms >= row.deadline_ms ||
      !row.preview_json || !row.odds_json ||
      !Number.isFinite(row.preview_observed_ms) || !Number.isFinite(row.odds_observed_ms) ||
      !Number.isFinite(row.weather_observed_ms) || !row.weather_source) return false;
  try {
    const preview = verifiedPreviewPayload({
      date: row.race_date, stadium_number: row.stadium_number, race_number: row.race_number,
      source: row.preview_source, observed_at: new Date(row.preview_observed_ms).toISOString(),
      preview: JSON.parse(row.preview_json),
    }, row, row.captured_ms);
    if (preview.weatherSource !== row.weather_source ||
        preview.weatherObservedMs !== row.weather_observed_ms) return false;
    verifiedOddsPayload({
      date: row.race_date, stadium_number: row.stadium_number, race_number: row.race_number,
      source: row.odds_source, observed_at: new Date(row.odds_observed_ms).toISOString(),
      odds: JSON.parse(row.odds_json),
    }, row, row.captured_ms);
    return true;
  } catch {
    return false;
  }
}
