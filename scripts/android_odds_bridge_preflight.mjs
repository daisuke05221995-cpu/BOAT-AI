// Research-only Android odds snapshot preflight. No network, DB, model or wager side effects.
// A device's source label or clock is NOT proof of feed rights or origin observation.
const EXPECTED = Object.freeze(Array.from({ length: 6 }, (_, a) => a + 1)
  .flatMap(first => Array.from({ length: 6 }, (_, b) => b + 1)
    .filter(second => second !== first)
    .flatMap(second => Array.from({ length: 6 }, (_, c) => c + 1)
      .filter(third => third !== first && third !== second)
      .map(third => `${first}-${second}-${third}`))));
const COMBINATIONS = new Set(EXPECTED);
const FIELDS = new Set([
  'schema_version', 'race_date', 'stadium_number', 'race_number', 'deadline_ms',
  'device_received_ms', 'source_observed_ms', 'source_id', 'odds',
]);
const reject = reason => ({
  accepted: false, classification: 'UNAVAILABLE', reason,
  eligible_for_forecast: false, eligible_for_buy: false,
});
const integer = n => Number.isSafeInteger(n) && n >= 0;
const jstDate = ms => new Date(ms + 9 * 60 * 60_000).toISOString().slice(0, 10);

/**
 * Strict preflight for a later, permission-reviewed private collector bridge.
 * Only synthetic or separately authorized snapshots should be passed here.
 * Always quarantines values: this is NOT a licensed provider adapter.
 *
 * @param {object} snapshot Untrusted Android receipt, not a source attestation.
 * @param {number} serverNowMs Independently sampled receipt time.
 */
export function assessAndroidOddsSnapshot(snapshot, serverNowMs) {
  if (!snapshot || typeof snapshot !== 'object' || Array.isArray(snapshot) ||
      snapshot.schema_version !== 1 || Object.keys(snapshot).some(k => !FIELDS.has(k)))
    return reject('INVALID_SCHEMA_OR_EXTRA_FIELD');
  if (!integer(serverNowMs) || !integer(snapshot.deadline_ms) ||
      !integer(snapshot.device_received_ms)) return reject('INVALID_CLOCK');
  if (typeof snapshot.race_date !== 'string' ||
      !/^\\d{4}-\\d{2}-\\d{2}$/.test(snapshot.race_date) ||
      !Number.isInteger(snapshot.stadium_number) || snapshot.stadium_number < 1 ||
      snapshot.stadium_number > 24 || !Number.isInteger(snapshot.race_number) ||
      snapshot.race_number < 1 || snapshot.race_number > 12 ||
      jstDate(snapshot.deadline_ms) !== snapshot.race_date)
    return reject('INVALID_RACE_IDENTITY');
  if (typeof snapshot.source_id !== 'string' ||
      !/^[a-zA-Z0-9_.-]{1,100}$/.test(snapshot.source_id))
    return reject('INVALID_SOURCE_LABEL');
  if (snapshot.device_received_ms >= snapshot.deadline_ms ||
      serverNowMs >= snapshot.deadline_ms)
    return reject('AFTER_CLOSE_OR_LATE_SERVER_INGEST');
  if (snapshot.device_received_ms > serverNowMs + 5_000 ||
      serverNowMs - snapshot.device_received_ms > 120_000)
    return reject('DEVICE_CLOCK_UNTRUSTWORTHY_OR_STALE');
  const observed = snapshot.source_observed_ms;
  if (observed !== null && (!integer(observed) ||
      observed > snapshot.device_received_ms ||
      snapshot.device_received_ms - observed > 120_000))
    return reject('SOURCE_TIME_INVALID_OR_STALE');
  if (!Array.isArray(snapshot.odds) || snapshot.odds.length !== 120)
    return reject('ODDS_NOT_120');
  const found = new Map();
  for (const row of snapshot.odds) {
    if (!row || typeof row !== 'object' || Array.isArray(row) ||
        Object.keys(row).sort().join(',') !== 'combination,decimal_odds' ||
        !COMBINATIONS.has(row.combination) || found.has(row.combination) ||
        typeof row.decimal_odds !== 'number' ||
        !Number.isFinite(row.decimal_odds) ||
        row.decimal_odds <= 0 || row.decimal_odds > 1_000_000)
      return reject('INVALID_ODDS_ROW');
    found.set(row.combination, row.decimal_odds);
  }
  if (found.size !== 120) return reject('INCOMPLETE_COMBINATIONS');
  const lead = snapshot.deadline_ms - snapshot.device_received_ms;
  const stage = lead >= 360_000 && lead <= 600_000 ? 'T8_WINDOW' :
    lead >= 180_000 && lead < 360_000 ? 'T5_WINDOW' : 'OTHER_PRE_CLOSE';
  return {
    accepted: true, classification: 'DEVICE_ODDS_QUARANTINED',
    reason: 'DEVICE_SOURCE_AND_USAGE_RIGHTS_UNVERIFIED',
    eligible_for_forecast: false, eligible_for_buy: false,
    race_key: `${snapshot.race_date}:${snapshot.stadium_number}:${snapshot.race_number}`,
    stage, device_received_ms: snapshot.device_received_ms,
    source_observed_ms_claimed: observed,
    source_time_independently_verified: false,
    source_rights_independently_verified: false,
    // Do not log/export values; reserved for local, permission-reviewed integration.
    normalized_odds: EXPECTED.map(combination => ({
      combination, decimal_odds: found.get(combination),
    })),
  };
}

export const expectedTrifectaCombinations = () => [...EXPECTED];
