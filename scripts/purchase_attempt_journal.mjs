// Research-only immutable purchase-attempt journal reducer.
// No I/O, credentials, Android UI operations or actual wagering.
// A real integration MUST atomically persist PREPARED before any external submit.
// This module intentionally cannot authorize a live submission.
import { fingerprintPurchasePlan } from './purchase_replay_guard.mjs';
const states = new Set(['PREPARED','SUBMITTING','UNKNOWN','CONFIRMED','REJECTED']);
const plain = x => x !== null && typeof x === 'object' && !Array.isArray(x) &&
  Object.getPrototypeOf(x) === Object.prototype;
const deny = reason => ({ accepted: false, classification: 'UNAVAILABLE',
  reason, journal: null, ready_for_live_submission: false });
const validRow = x => plain(x) && /^[a-f0-9]{64}$/.test(x.fingerprint) &&
  states.has(x.state) && Number.isSafeInteger(x.sequence) && x.sequence > 0;
const copy = rows => rows.map(x => ({ fingerprint: x.fingerprint,
  state: x.state, sequence: x.sequence }));
/**
 * Initialize a single plan only when the caller proves its durable journal
 * was read. Never silently replace a missing journal with an empty array.
 */
export function preparePurchaseAttempt(plan, durableJournal) {
  const fingerprint = fingerprintPurchasePlan(plan);
  if (!fingerprint) return deny('INVALID_PURCHASE_PLAN');
  if (!Array.isArray(durableJournal)) return deny('DURABLE_JOURNAL_REQUIRED');
  if (durableJournal.length > 10_000 || !durableJournal.every(validRow))
    return deny('INVALID_DURABLE_JOURNAL');
  if (new Set(durableJournal.map(x => x.fingerprint)).size !== durableJournal.length)
    return deny('DUPLICATE_JOURNAL_FINGERPRINT');
  if (durableJournal.some(x => x.fingerprint === fingerprint))
    return deny('PLAN_ALREADY_PREPARED_OR_ATTEMPTED');
  const next = copy(durableJournal);
  next.push({ fingerprint, state: 'PREPARED',
    sequence: Math.max(0, ...next.map(x => x.sequence)) + 1 });
  return { accepted: true, classification: 'OFFLINE_PREPARED_ONLY',
    reason: 'CALLER_MUST_DURABLY_COMMIT_BEFORE_ANY_EXTERNAL_ACTION',
    fingerprint, journal: next, ready_for_live_submission: false };
}
/**
 * A compare-and-swap journal transition for OFFLINE analysis.
 * UNKNOWN is terminal for automation, including after timeout or app restart.
 * CONFIRMED/REJECTED are terminal too. No reset/retry/re-submit path.
 */
export function transitionPurchaseAttempt(journal, fingerprint, expectedSequence, nextState) {
  if (!Array.isArray(journal) || journal.length > 10_000 ||
      !journal.every(validRow) ||
      new Set(journal.map(x => x.fingerprint)).size !== journal.length)
    return deny('INVALID_DURABLE_JOURNAL');
  if (typeof fingerprint !== 'string' || !/^[a-f0-9]{64}$/.test(fingerprint) ||
      !Number.isSafeInteger(expectedSequence) || expectedSequence < 1)
    return deny('INVALID_TRANSITION_REQUEST');
  const i = journal.findIndex(x => x.fingerprint === fingerprint);
  if (i < 0) return deny('UNKNOWN_PLAN');
  const row = journal[i];
  if (row.sequence !== expectedSequence) return deny('STALE_JOURNAL_SEQUENCE');
  if (!((row.state === 'PREPARED' && nextState === 'SUBMITTING') ||
        (row.state === 'SUBMITTING' && ['UNKNOWN','CONFIRMED','REJECTED'].includes(nextState))))
    return deny('ILLEGAL_OR_TERMINAL_TRANSITION');
  const next = copy(journal);
  next[i] = { ...next[i], state: nextState, sequence: row.sequence + 1 };
  return { accepted: true, classification: 'OFFLINE_JOURNAL_TRANSITION_ONLY',
    reason: 'DURABLE_COMMIT_REQUIRED_AND_NO_LIVE_SUBMISSION_AUTHORITY',
    journal: next, ready_for_live_submission: false };
}
