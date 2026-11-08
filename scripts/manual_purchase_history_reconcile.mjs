// Research-only manual-purchase handoff reconciliation.
// The official app must be operated by the account holder. This module
// NEVER confirms a wager, creates a payment, reads credentials or taps a UI.
import { fingerprintPurchasePlan } from './purchase_replay_guard.mjs';

const plain = x => x !== null && typeof x === 'object' &&
  !Array.isArray(x) && Object.getPrototypeOf(x) === Object.prototype;
const stop = (reason, fingerprint = null) => ({
  classification: 'UNAVAILABLE', reason, fingerprint,
  manual_review_required: true, ready_for_live_submission: false,
  purchase_confirmed: false, retry_allowed: false,
});
const validLine = x => plain(x) && Object.keys(x).sort().join(',') ===
  'amount,combination,raceNumber,stadiumNumber' &&
  Number.isInteger(x.stadiumNumber) && x.stadiumNumber >= 1 && x.stadiumNumber <= 24 &&
  Number.isInteger(x.raceNumber) && x.raceNumber >= 1 && x.raceNumber <= 12 &&
  typeof x.combination === 'string' && /^[1-6]-[1-6]-[1-6]$/.test(x.combination) &&
  new Set(x.combination.split('-')).size === 3 &&
  Number.isSafeInteger(x.amount) && x.amount >= 100 &&
  x.amount <= 100_000 && x.amount % 100 === 0;
const key = x => [x.stadiumNumber, x.raceNumber, x.combination, x.amount].join('|');
/**
 * This is a read-only check of an operator-entered receipt transcription.
 * Receipt text is not independent proof of acceptance: only the official
 * account's transaction history can establish the purchase.
 * The output deliberately never contains a receipt number or raw input.
 */
export function reconcileManualPurchaseEvidence(plan, evidence, journal) {
  const fingerprint = fingerprintPurchasePlan(plan);
  if (!fingerprint) return stop('INVALID_PLAN');
  if (!Array.isArray(journal) || journal.length > 10_000 ||
      journal.some(x => !plain(x) || !/^[a-f0-9]{64}$/.test(x.fingerprint) ||
        !['PREPARED','SUBMITTING','UNKNOWN','CONFIRMED','REJECTED'].includes(x.state) ||
        !Number.isSafeInteger(x.sequence) || x.sequence < 1) ||
      new Set(journal.map(x => x.fingerprint)).size !== journal.length)
    return stop('DURABLE_JOURNAL_UNVERIFIED', fingerprint);
  if (journal.some(x => x.fingerprint === fingerprint))
    return stop('EXISTING_ATTEMPT_REQUIRES_OFFICIAL_HISTORY_CHECK', fingerprint);
  if (!plain(evidence) ||
      Object.keys(evidence).sort().join(',') !==
      'date,lines,officialHistoryChecked,officialHistoryStatus,totalYen')
    return stop('INVALID_EVIDENCE_SCHEMA', fingerprint);
  if (evidence.officialHistoryChecked !== true ||
      !['ACCEPTED','NOT_FOUND','UNKNOWN'].includes(evidence.officialHistoryStatus))
    return stop('OFFICIAL_HISTORY_NOT_VERIFIED', fingerprint);
  if (evidence.officialHistoryStatus !== 'ACCEPTED')
    return stop('OFFICIAL_HISTORY_NOT_ACCEPTED', fingerprint);
  if (typeof evidence.date !== 'string' ||
      !/^\d{4}-\d{2}-\d{2}$/.test(evidence.date) ||
      !Array.isArray(evidence.lines) || evidence.lines.length === 0 ||
      evidence.lines.length > 100 || !evidence.lines.every(validLine) ||
      !Number.isSafeInteger(evidence.totalYen) || evidence.totalYen < 100)
    return stop('INVALID_HISTORY_LINES', fingerprint);
  // Match the existing fingerprintPurchasePlan schema exactly. One race
  // per plan, no inferred venue, date, ticket or amount fields.
  const expected = plan.tickets.map(ticket => ({
    stadiumNumber: plan.stadium_number, raceNumber: plan.race_number,
    combination: ticket.combination, amount: ticket.yen,
  }));
  if (expected.length !== evidence.lines.length || !expected.every(validLine) ||
      new Set(expected.map(key)).size !== expected.length ||
      new Set(evidence.lines.map(key)).size !== evidence.lines.length ||
      expected.some(x => !evidence.lines.some(y => key(x) === key(y))) ||
      evidence.lines.reduce((sum, x) => sum + x.amount, 0) !== evidence.totalYen ||
      expected.reduce((sum, x) => sum + x.amount, 0) !== evidence.totalYen ||
      evidence.date !== plan.race_date)
    return stop('OFFICIAL_HISTORY_PLAN_MISMATCH', fingerprint);
  return {
    classification: 'MANUAL_HISTORY_MATCH_REQUIRES_OPERATOR_CONFIRMATION',
    reason: 'OPERATOR_ATTESTATION_NOT_INDEPENDENT_RECEIPT_PROOF',
    fingerprint, matched_lines: expected.length,
    manual_review_required: true, ready_for_live_submission: false,
    purchase_confirmed: false, retry_allowed: false,
  };
}
