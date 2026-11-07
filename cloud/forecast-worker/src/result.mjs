const isPositivePayout = value => Number.isInteger(value) && value >= 100;

function validTrifecta(combination) {
  if (typeof combination !== 'string' || !/^[1-6]-[1-6]-[1-6]$/.test(combination)) return false;
  return new Set(combination.split('-')).size === 3;
}

// This is a post-race settlement only. Neither these fields nor their timestamps
// may be supplied to the pre-close Model A feature builder.
export function normalizePublishedResult(observation, row) {
  if (!observation || observation.date !== row.race_date ||
    observation.stadium_number !== row.stadium_number || observation.race_number !== row.race_number) return null;

  const result = observation.result;
  if (result && (result.date !== row.race_date ||
    result.stadium_number !== row.stadium_number || result.race_number !== row.race_number)) return null;
  if (observation.day_number_source === '順延' || observation.day_number_source === '中止') {
    // A postponed meeting can carry a placeholder result object with an empty
    // dividend array. Explicit status + no dividends is terminal; a conflict
    // between the published day status and a dividend must remain unresolved.
    if (result && (!Array.isArray(result.payouts?.trifecta) || result.payouts.trifecta.length)) return null;
    return { status: observation.day_number_source === '順延' ? 'POSTPONED' : 'CANCELLED',
      trifecta_combination: null, trifecta_payout: null };
  }
  if (!result || result.date !== row.race_date ||
    result.stadium_number !== row.stadium_number || result.race_number !== row.race_number) return null;

  const triples = result.payouts?.trifecta;
  if (!Array.isArray(triples) || triples.length === 0) return null;
  // F/L returns can make the entire 3-trifecta pool unformed. A 100-yen
  // returned stake is not a winning 100-yen payout and must never be HIT.
  if (triples.length === 1 && triples[0].combination == null &&
    triples[0].label === '不成立' && triples[0].amount === 100) {
    return { status: 'UNFORMED', trifecta_combination: null,
      trifecta_payout: null, refund_per_100: 100 };
  }
  if (!triples.every(p => validTrifecta(p.combination) && isPositivePayout(p.amount))) return null;
  if (new Set(triples.map(p => p.combination)).size !== triples.length) return null;
  const payouts = triples.map(p => ({ combination: p.combination, payout: p.amount }));
  return { status: 'SETTLED', trifecta_combination: payouts.length === 1 ? payouts[0].combination : null,
    trifecta_payout: payouts.length === 1 ? payouts[0].payout : null,
    trifecta_payouts: payouts };
}

export function resultRetryDue(row, nowMs, retryMs = 15 * 60_000) {
  if (row.result_json || !Number.isFinite(row.deadline_ms) ||
    nowMs < row.deadline_ms + 20 * 60_000) return false;
  return !Number.isFinite(row.result_last_attempt_ms) ||
    nowMs - row.result_last_attempt_ms >= retryMs;
}
