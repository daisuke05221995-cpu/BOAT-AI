// Frozen v0.16 Android ModelAFeatureBuilder input contract. This module only
// computes pre-race features; it never fetches data, results or odds.

const F32 = (value) => typeof value === 'number' && Number.isFinite(value) ? Math.fround(value) : NaN;
const EMPTY = (reason, day, history) => ({
  input: null, laneHistory: [], usable: false, reason,
  predictionDayOrdinal: day, historyThroughDayOrdinal: history.lastDay,
  historyFreshForDay: day !== null && history.lastDay === day - 1,
});

function ordinal(input) {
  if (typeof input !== 'string') return null;
  const prefix = input.slice(0, 10);
  if (!/^\d{4}-\d{2}-\d{2}$/.test(prefix)) return null;
  const [year, month, day] = prefix.split('-').map(Number);
  const millis = Date.UTC(year, month - 1, day);
  const date = new Date(millis);
  if (date.getUTCFullYear() !== year || date.getUTCMonth() !== month - 1 || date.getUTCDate() !== day) return null;
  return Math.trunc(millis / 86400000) + 719163; // Python date.toordinal()
}

function racerClass(racer) {
  if (racer.classNumber !== null && racer.classNumber !== undefined) return racer.classNumber;
  const value = String(racer.rank ?? '').trim().toUpperCase();
  if (value === 'A1') return 1;
  if (value === 'A2') return 2;
  if (value === 'B1') return 3;
  if (value === 'B2') return 4;
  return /^[1-4]$/.test(value) ? Number(value) : 0;
}

function windDirection(preview) {
  const number = preview?.windDirectionNumber;
  if (Number.isInteger(number) && number >= 1 && number <= 16) return number;
  const match = typeof preview?.windDirection === 'string' ? preview.windDirection.match(/\d+/) : null;
  const parsed = match ? Number(match[0]) : null;
  return Number.isInteger(parsed) && parsed >= 1 && parsed <= 16 ? parsed : null;
}

function currentRow(racer, cls) {
  const preview = racer.preview;
  const row = [racer.nationalWinRate, racer.localWinRate, racer.nationalTop2,
    racer.localTop2, racer.nationalTop3, racer.localTop3,
    racer.motorTop2, racer.motorTop3, racer.boatTop2, racer.boatTop3,
    racer.averageStart, racer.flyingCount, racer.lateCount, racer.age, racer.weight,
    preview?.exhibitionTime, preview?.startTiming, preview?.course,
    preview?.tilt, preview?.weightAdjustment].map(F32);
  for (let i = 1; i <= 4; i++) row.push(cls === 0 ? NaN : F32(cls === i ? 1 : 0));
  row.push(preview?.course === null || preview?.course === undefined ? NaN :
    F32(preview.course !== racer.lane ? 1 : 0));
  return row;
}

function relativeRows(current) {
  const exhibitions = current.map((row) => row[15]);
  const starts = current.map((row) => row[16]);
  const min = Math.min(...exhibitions), max = Math.max(...exhibitions);
  return current.map((_, lane) => [
    F32(1 + exhibitions.filter((other) => exhibitions[lane] > other).length),
    F32(1 + starts.filter((other) => starts[lane] > other).length),
    F32(exhibitions[lane] - min),
    F32(exhibitions[lane] - max),
    F32(exhibitions[lane] - exhibitions[0]),
  ]);
}

function globalFeatures(race, reactions) {
  const preview = race.preview;
  const direction = windDirection(preview);
  const out = [preview?.windSpeed, preview?.waveHeight,
    preview?.airTemperature, preview?.waterTemperature].map(F32);
  for (let i = 1; i <= 16; i++) out.push(direction === null ? NaN : F32(direction === i ? 1 : 0));
  const weak = Math.max(reactions[0][1], 0) + Math.max(reactions[0][3], 0);
  const strong = reactions.slice(1).filter((row) => row[1] <= -0.5 || row[3] <= -0.5).length;
  out.push(F32(weak), F32(strong), F32(race.stadiumNumber), F32(race.raceNumber));
  return out;
}

export function buildModelAFeatures(race, history) {
  const day = ordinal(race?.date);
  if (day === null) return EMPTY('Invalid race date', null, history);
  if (day <= history.lastDay) return EMPTY('History is not strictly earlier than prediction day', day, history);
  if (!Number.isInteger(race.stadiumNumber) || race.stadiumNumber < 1 || race.stadiumNumber > 24 ||
      !Number.isInteger(race.raceNumber) || race.raceNumber <= 0) {
    return EMPTY('Invalid venue/race number', day, history);
  }
  if (!Array.isArray(race.racers) || race.racers.length !== 6 ||
      new Set(race.racers.map((r) => r?.lane)).size !== 6 ||
      !race.racers.every((r) => Number.isInteger(r?.lane) && r.lane >= 1 && r.lane <= 6)) {
    return EMPTY('Model A requires exactly lanes 1..6', day, history);
  }
  const racers = [...race.racers].sort((a, b) => a.lane - b.lane);
  const ids = racers.map((r) => r.registrationNumber);
  if (ids.some((id) => !Number.isInteger(id) || id <= 0) || new Set(ids).size !== 6) {
    return EMPTY('Missing or duplicate racer registration number', day, history);
  }
  const classes = racers.map(racerClass);
  const current = racers.map((racer, lane) => currentRow(racer, classes[lane]));
  const courses = current.map((row) => row[17]);
  if (current.some((row) => [0, 15, 16, 17].some((index) => !Number.isFinite(row[index]))) ||
      courses.some((course) => !Number.isInteger(course) || course < 1 || course > 6) ||
      new Set(courses).size !== 6) {
    return EMPTY('Missing required Model A pre-race input', day, history);
  }

  const relative = relativeRows(current);
  const laneHistory = [];
  const reactions = [];
  const boat = current.map((row, lane) => {
    const snapshot = history.snapshot({
      player: ids[lane], course: row[17], racerClass: classes[lane],
      exhibitionTime: row[15], previewStartTiming: row[16], courseChanged: row[24] === 1,
      day,
    });
    laneHistory.push({ player: ids[lane], course: row[17], racerClass: classes[lane],
      exhibitionTime: row[15], previewStartTiming: row[16], flags: snapshot.flags });
    reactions.push(snapshot.reaction);
    const features = [...row, ...relative[lane], ...snapshot.history, ...snapshot.reaction].map(F32);
    if (features.length !== 82) throw new Error('MODEL_A_FEATURE_WIDTH_MISMATCH');
    return features;
  });
  const global = globalFeatures(race, reactions);
  if (global.length !== 24) throw new Error('MODEL_A_GLOBAL_WIDTH_MISMATCH');
  return {
    input: { boat, global, venue: race.stadiumNumber, raceNumber: race.raceNumber },
    laneHistory, usable: true, reason: null, predictionDayOrdinal: day,
    historyThroughDayOrdinal: history.lastDay,
    historyFreshForDay: history.lastDay === day - 1,
  };
}
