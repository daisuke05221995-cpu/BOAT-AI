// Research-only adapter of the existing Android OddsFetchResult data shape.
// No network, no Android changes, no storage, no model inference or betting.
// An Android field named "source" is NOT an independently verified permission grant.
import { assessAndroidOddsSnapshot } from './android_odds_bridge_preflight.mjs';

const OFFICIAL_LABELS = Object.freeze({
  '公式PC版': 'android_official_pc',
  '公式スマホ版': 'android_official_sp',
});
const unavailable = reason => ({
  accepted: false,
  classification: 'UNAVAILABLE',
  reason,
  eligible_for_forecast: false,
  eligible_for_buy: false,
});
const plainObject = value => value !== null && typeof value === 'object' &&
  !Array.isArray(value) && Object.getPrototypeOf(value) === Object.prototype;

/**
 * `OddsFetchResult` fields in app/src/main/java/jp/boatai/app/Models.kt:
 * odds: Map<String,Double>, source: String, diagnostics: List, fetchedAt: Long.
 *
 * The repository fetches only requested combinations, and may return
 * BoatraceCSV estimated odds as a fallback. Both are NOT a full live snapshot.
 *
 * `race.deadlineMs` must come from independently validated race schedule
 * information at the time of future integration; it is not an Android model
 * field that may be guessed or inferred from result timestamps.
 */
export function inspectExistingAndroidOddsResult(result, race, serverNowMs) {
  if (!plainObject(result) || !plainObject(race) ||
      !plainObject(result.odds) || typeof result.source !== 'string' ||
      !Number.isSafeInteger(result.fetchedAt) || result.fetchedAt < 0 ||
      !Array.isArray(result.diagnostics))
    return unavailable('INVALID_ANDROID_RESULT_SHAPE');
  if (!Object.prototype.hasOwnProperty.call(OFFICIAL_LABELS, result.source))
    return unavailable(/BoatraceCSV|推定|予備/.test(result.source) ?
      'ESTIMATED_OR_FALLBACK_ODDS_NOT_LIVE' : 'UNKNOWN_ODDS_SOURCE');
  const entries = Object.entries(result.odds);
  // A successful Android request can be a selected 3-6-pick request.
  // Requiring all 120 entries prevents calling this a full snapshot.
  if (entries.length !== 120)
    return unavailable('ANDROID_SELECTED_ODDS_NOT_120');
  const odds = entries.map(([combination, decimal_odds]) => ({
    combination, decimal_odds,
  }));
  const payload = {
    schema_version: 1,
    race_date: race.date,
    stadium_number: race.stadiumNumber,
    race_number: race.raceNumber,
    deadline_ms: race.deadlineMs,
    device_received_ms: result.fetchedAt,
    source_observed_ms: null, // OddsFetchResult does NOT provide provider observation time.
    source_id: OFFICIAL_LABELS[result.source],
    odds,
  };
  const preflight = assessAndroidOddsSnapshot(payload, serverNowMs);
  if (!preflight.accepted) return preflight;
  // Neither the map nor the source label proves observation time/rights.
  return {
    ...preflight,
    eligible_for_forecast: false,
    eligible_for_buy: false,
    provenance_status: 'ANDROID_RECEIPT_ONLY',
    source_observed_ms_claimed: null,
    source_time_independently_verified: false,
    source_rights_independently_verified: false,
  };
}
