// Strict, side-effect-free daily history reconciliation. This checks a supplied
// finalized schedule against normalized terminal results; it does NOT certify
// that the upstream provider supplied the complete national schedule. A
// separately audited provider/manifest is required before persistence/use.
import { ModelAPlayerHistory } from './model-a-history.mjs';
import { buildModelAFeatures } from './model-a-features.mjs';
import { isValidDate, japanDate, raceId } from './policy.mjs';

const MAX_RACES = 24 * 12;
const fail = code => { throw new Error(`MODEL_A_DAY_${code}`); };
const dayOrdinal = date => Math.trunc(Date.parse(`${date}T00:00:00Z`) / 86400000) + 719163;

function identity(race, date) {
  if (race?.date !== date) fail('WRONG_DATE');
  const key = raceId(date, race.stadiumNumber, race.raceNumber);
  if (!key || race.raceId !== key) fail('INVALID_RACE_ID');
  return key;
}

/**
 * @param {object} historyState Previously audited Model A history (never mutated).
 * @param {object} manifest Finalized external schedule manifest: date,
 *   scheduledRaceIds, expectedRaceCount, scheduleSource, resultSource,
 *   confirmedAt (ISO UTC, after the target day has ended in JST).
 * @param {object[]} races Normalized full-race inputs with result.status
 *   SETTLED + a six-lane finishOrder, or CANCELLED + a documented reason.
 * @param {number} nowMs Testable clock. No future-day confirmation permitted.
 * @returns {{state: object, audit: object}} Candidate state, NOT a deployment.
 */
export function reconcileModelAHistoryDay(historyState, manifest, races, nowMs = Date.now()) {
  const date = manifest?.date;
  if (!isValidDate(date) || !Number.isFinite(nowMs)) fail('INVALID_DATE');
  const day = dayOrdinal(date);
  const history = new ModelAPlayerHistory(structuredClone(historyState));
  if (history.lastDay !== day - 1) fail('NONCONSECUTIVE');
  if (japanDate(nowMs) <= date) fail('NOT_FINAL');
  const confirmedMs = Date.parse(manifest.confirmedAt);
  const endOfDayMs = Date.parse(`${date}T00:00:00+09:00`) + 86400000;
  if (typeof manifest.confirmedAt !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/.test(manifest.confirmedAt) ||
      !Number.isFinite(confirmedMs) || confirmedMs < endOfDayMs || confirmedMs > nowMs ||
      ![manifest.scheduleSource, manifest.resultSource].every(s =>
        typeof s === 'string' && s.trim().length > 0 && s.length <= 100)) fail('UNVERIFIED_MANIFEST');

  const scheduled = manifest.scheduledRaceIds;
  if (!Array.isArray(scheduled) || !scheduled.length || scheduled.length > MAX_RACES ||
      manifest.expectedRaceCount !== scheduled.length ||
      scheduled.some(id => typeof id !== 'string' ||
        !/^\d{4}-\d{2}-\d{2}-\d{2}-(?:[1-9]|1[0-2])$/.test(id) ||
        !id.startsWith(`${date}-`) ||
        !Number.isInteger(Number(id.slice(11, 13))) ||
        Number(id.slice(11, 13)) < 1 || Number(id.slice(11, 13)) > 24) ||
      new Set(scheduled).size !== scheduled.length) fail('INVALID_SCHEDULE');
  if (!Array.isArray(races) || races.length !== scheduled.length) fail('RACE_COUNT_MISMATCH');
  const expected = new Set(scheduled);
  const seen = new Set();
  const pending = [];
  let settled = 0, cancelled = 0;
  for (const race of [...races].sort((a, b) =>
    (a?.stadiumNumber ?? 0) - (b?.stadiumNumber ?? 0) ||
    (a?.raceNumber ?? 0) - (b?.raceNumber ?? 0))) {
    const key = identity(race, date);
    if (!expected.has(key)) fail('UNSCHEDULED_RACE');
    if (seen.has(key)) fail('DUPLICATE_RACE');
    seen.add(key);
    if (race.result?.status === 'CANCELLED') {
      if (typeof race.result.reason !== 'string' || !race.result.reason.trim() ||
          race.result.finishOrder?.length) fail('CANCELLATION_UNVERIFIED');
      cancelled++;
      continue;
    }
    if (race.result?.status !== 'SETTLED' ||
        !Array.isArray(race.result.finishOrder) || race.result.finishOrder.length !== 6 ||
        new Set(race.result.finishOrder).size !== 6 ||
        !race.result.finishOrder.every(v => Number.isInteger(v) && v >= 1 && v <= 6)) {
      fail('RESULT_INCOMPLETE');
    }
    const features = buildModelAFeatures(race, history);
    if (!features.usable || !features.historyFreshForDay || features.laneHistory.length !== 6) {
      fail('FEATURE_INCOMPLETE');
    }
    const finish = race.result.finishOrder;
    const top2 = new Set(finish.slice(0, 2)), top3 = new Set(finish.slice(0, 3));
    features.laneHistory.forEach((lane, index) => {
      pending.push({ ...lane, win: index + 1 === finish[0],
        top2: top2.has(index + 1), top3: top3.has(index + 1) });
    });
    settled++;
  }
  if (seen.size !== expected.size) fail('MISSING_RACE');
  // Only the clone is committed. No caller history is advanced on any error.
  history.commitDay(day, pending);
  return {
    state: history.exportState(),
    audit: { status: 'VALIDATED_AGAINST_SUPPLIED_MANIFEST', date, dayOrdinal: day,
      expectedRaces: scheduled.length, settledRaces: settled, cancelledRaces: cancelled,
      committedRaces: pending.length / 6, previousLastDay: day - 1, historyLastDay: day,
      scheduleSource: manifest.scheduleSource, resultSource: manifest.resultSource,
      confirmedAt: manifest.confirmedAt },
  };
}
