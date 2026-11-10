// Research-only redacted receipt reconciliation. No app, network, storage or betting.
// A parsed receipt is never proof of official acceptance unless separately verified.
import { inspectOfflinePurchaseReview } from './purchase_review_consistency.mjs';

const deny = reason => ({
  classification: 'UNAVAILABLE', reason, receipt_matches_offline: false,
  receipt_officially_verified: false, ready_for_live_submission: false,
  purchase_confirmed: false,
});
const plain = x => x !== null && typeof x === 'object' && !Array.isArray(x) &&
  Object.getPrototypeOf(x) === Object.prototype;
const amount = x => Number.isSafeInteger(x) && x > 0 && x % 100 === 0;
const combo = x => typeof x === 'string' && /^[1-6]-[1-6]-[1-6]$/.test(x) &&
  new Set(x.split('-')).size === 3;

/**
 * Compare a planned purchase, normalized pre-submit review, and normalized
 * post-submit receipt. Never accept a screenshot, inferred UI text or arbitrary
 * success flag as a verified purchase. Do not persist/export receipt numbers,
 * user identifiers, authentication information or raw page text.
 *
 * receipt shape: { race_date, stadium_number, race_number, tickets:
 * [{ combination, yen }], total_yen, receipt_status: 'ACCEPTED' }
 * All fields must come from independently parsed visible evidence; if
 * unavailable, return UNAVAILABLE, not SKIP, BUY or CONFIRMED.
 */
export function inspectOfflineReceiptConsistency(plan, review, receipt) {
  const reviewCheck = inspectOfflinePurchaseReview(plan, review);
  if (!reviewCheck.consistent_for_offline_review)
    return deny('PRE_SUBMISSION_REVIEW_NOT_CONSISTENT');
  if (!plain(receipt) || receipt.receipt_status !== 'ACCEPTED')
    return deny('RECEIPT_NOT_EXPLICITLY_ACCEPTED');
  if (receipt.race_date !== plan.race_date ||
      receipt.stadium_number !== plan.stadium_number ||
      receipt.race_number !== plan.race_number)
    return deny('RECEIPT_RACE_MISMATCH');
  if (!Array.isArray(receipt.tickets) ||
      receipt.tickets.length !== plan.tickets.length)
    return deny('RECEIPT_ROW_COUNT_MISMATCH');
  if (!amount(receipt.total_yen) || receipt.total_yen !== reviewCheck.total_yen)
    return deny('RECEIPT_TOTAL_MISMATCH');
  const seen = new Set();
  const rows = new Map();
  for (const row of receipt.tickets) {
    if (!plain(row) || !combo(row.combination) || !amount(row.yen) ||
        seen.has(row.combination)) return deny('INVALID_OR_DUPLICATE_RECEIPT_ROW');
    seen.add(row.combination);
    rows.set(row.combination, row.yen);
  }
  if (plan.tickets.some(row => rows.get(row.combination) !== row.yen))
    return deny('RECEIPT_SELECTION_OR_STAKE_MISMATCH');
  return {
    classification: 'OFFLINE_RECEIPT_FIELDS_CONSISTENT',
    reason: 'INDEPENDENT_OFFICIAL_RECEIPT_VERIFICATION_REQUIRED',
    fingerprint: reviewCheck.fingerprint,
    row_count: rows.size, total_yen: receipt.total_yen,
    receipt_matches_offline: true, receipt_officially_verified: false,
    ready_for_live_submission: false, purchase_confirmed: false,
  };
}
