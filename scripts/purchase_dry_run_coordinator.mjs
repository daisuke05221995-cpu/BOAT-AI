// Research-only non-purchase dry-run coordinator.
// Pure: no Android interaction, credentials, storage, network, or submission.
// Every stage is evidence-gated; no stage ever enables a live transaction.
import { inspectPurchaseReplay } from './purchase_replay_guard.mjs';
import { inspectOfflinePurchaseReview } from './purchase_review_consistency.mjs';
import { inspectOfflineReceiptConsistency } from './purchase_receipt_consistency.mjs';
import { auditPurchaseControlMap } from './purchase_control_map_audit.mjs';

const stop = (stage, reason, fingerprint = null) => ({
  classification: 'UNAVAILABLE', stage, reason, fingerprint,
  ready_for_offline_dry_run: false, ready_for_live_submission: false,
  purchase_confirmed: false,
});
/**
 * Modes:
 *  CALIBRATION: only redacted, on-device-probed selector metadata; no taps.
 *  REVIEW: compare a normalized review with plan; no submit.
 *  RECEIPT_AUDIT: inspect a supplied synthetic/redacted receipt, NOT a purchase.
 *
 * Caller must explicitly pass a durable journal snapshot. This function does
 * not write to it; no caller may infer that an actual attempt was persisted.
 */
export function inspectPurchaseDryRun(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input))
    return stop('INPUT', 'MISSING_DRY_RUN_INPUT');
  const { mode, plan, journal, controlMap, review, receipt } = input;
  if (!['CALIBRATION', 'REVIEW', 'RECEIPT_AUDIT'].includes(mode))
    return stop('INPUT', 'UNKNOWN_DRY_RUN_MODE');
  const replay = inspectPurchaseReplay(plan, journal);
  if (!replay.allowed_for_offline_dry_run)
    return stop('REPLAY', replay.reason);
  // Never infer a selector from a screenshot or unverified button position.
  const controls = auditPurchaseControlMap(controlMap);
  if (!controls.ready_for_offline_dry_run)
    return stop('CONTROL_MAP', 'CONTROL_MAP_NOT_CALIBRATED', replay.fingerprint);
  if (mode === 'CALIBRATION')
    return {
      classification: 'OFFLINE_CALIBRATION_ONLY', stage: 'CALIBRATION',
      reason: 'CONTROL_MAP_ONLY_NO_TAPS', fingerprint: replay.fingerprint,
      ready_for_offline_dry_run: true, ready_for_live_submission: false,
      purchase_confirmed: false,
    };
  const reviewCheck = inspectOfflinePurchaseReview(plan, review);
  if (!reviewCheck.consistent_for_offline_review)
    return stop('REVIEW', reviewCheck.reason, replay.fingerprint);
  if (mode === 'REVIEW')
    return {
      classification: 'OFFLINE_REVIEW_ONLY', stage: 'REVIEW',
      reason: 'SUBMISSION_NOT_PERMITTED', fingerprint: replay.fingerprint,
      ready_for_offline_dry_run: true, ready_for_live_submission: false,
      purchase_confirmed: false,
    };
  const receiptCheck = inspectOfflineReceiptConsistency(plan, review, receipt);
  if (!receiptCheck.receipt_matches_offline)
    return stop('RECEIPT_AUDIT', receiptCheck.reason, replay.fingerprint);
  return {
    classification: 'OFFLINE_RECEIPT_AUDIT_ONLY', stage: 'RECEIPT_AUDIT',
    reason: 'OFFICIAL_ACCEPTANCE_NOT_INDEPENDENTLY_VERIFIED',
    fingerprint: replay.fingerprint,
    ready_for_offline_dry_run: true, ready_for_live_submission: false,
    purchase_confirmed: false,
  };
}
