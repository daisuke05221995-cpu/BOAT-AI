// Offline-only purchase review consistency checker. No device, network, storage or bets.
// Accept only normalized, redacted rows supplied by a separate on-device parser.
import { fingerprintPurchasePlan } from './purchase_replay_guard.mjs';
const deny = reason => ({ classification: 'UNAVAILABLE', reason, ready_for_live_submission: false, consistent_for_offline_review: false });
const plain = x => x !== null && typeof x === 'object' && !Array.isArray(x) && Object.getPrototypeOf(x) === Object.prototype;
const yen = x => Number.isSafeInteger(x) && x > 0 && x % 100 === 0;
const combo = x => typeof x === 'string' && /^[1-6]-[1-6]-[1-6]$/.test(x) && new Set(x.split('-')).size === 3;
/**
 * Fail closed on mismatched venue/race/date, missing/extra ticket, altered stake
 * or total. A correct review still NEVER authorizes submission.
 * The receipt is NOT inferred here; final receipt requires independent validation.
 */
export function inspectOfflinePurchaseReview(plan, review) {
  if (!fingerprintPurchasePlan(plan)) return deny('INVALID_PURCHASE_PLAN');
  if (!plain(review) || !Array.isArray(review.tickets) ||
      review.tickets.length !== plan.tickets.length ||
      review.race_date !== plan.race_date ||
      review.stadium_number !== plan.stadium_number ||
      review.race_number !== plan.race_number)
    return deny('REVIEW_RACE_OR_ROW_COUNT_MISMATCH');
  if (!Number.isSafeInteger(review.total_yen) || review.total_yen <= 0)
    return deny('INVALID_REVIEW_TOTAL');
  const seen = new Set();
  const reviewRows = new Map();
  for (const row of review.tickets) {
    if (!plain(row) || !combo(row.combination) || !yen(row.yen) || seen.has(row.combination))
      return deny('INVALID_OR_DUPLICATE_REVIEW_ROW');
    seen.add(row.combination);
    reviewRows.set(row.combination, row.yen);
  }
  if (plan.tickets.some(row => reviewRows.get(row.combination) !== row.yen))
    return deny('REVIEW_SELECTION_OR_STAKE_MISMATCH');
  const total = plan.tickets.reduce((n, row) => n + row.yen, 0);
  if (!Number.isSafeInteger(total) || total !== review.total_yen)
    return deny('REVIEW_TOTAL_MISMATCH');
  return { classification: 'OFFLINE_REVIEW_CONSISTENT',
    reason: 'REVIEW_ONLY_RECEIPT_NOT_VERIFIED',
    fingerprint: fingerprintPurchasePlan(plan),
    row_count: reviewRows.size, total_yen: total,
    consistent_for_offline_review: true, ready_for_live_submission: false };
}
