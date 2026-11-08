// Research-only, fail-closed, pure purchase replay guard.
// This does not perform, authorize, schedule, or simulate a wager.
// No storage or network: integration must persist the attempt journal durably
// before ever attempting external submission.
import { createHash } from 'node:crypto';

const deny = reason => ({ allowed_for_offline_dry_run: false,
  allowed_for_live_submission: false, classification: 'UNAVAILABLE', reason });
const plain = x => x !== null && typeof x === 'object' && !Array.isArray(x) &&
  Object.getPrototypeOf(x) === Object.prototype;
const validInt = x => Number.isSafeInteger(x) && x > 0;
const validCombination = x => typeof x === 'string' &&
  /^[1-6]-[1-6]-[1-6]$/.test(x) && new Set(x.split('-')).size === 3;
const validDate = x => typeof x === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(x) &&
  !Number.isNaN(Date.parse(x + 'T00:00:00Z')) &&
  new Date(x + 'T00:00:00Z').toISOString().slice(0, 10) === x;

/**
 * Build a stable, non-PII plan fingerprint. Never include user credentials,
 * account identifiers, or raw receipt text.
 */
export function fingerprintPurchasePlan(plan) {
  if (!plain(plan) || !validDate(plan.race_date) ||
      !validInt(plan.stadium_number) || plan.stadium_number > 24 ||
      !validInt(plan.race_number) || plan.race_number > 12 ||
      !Array.isArray(plan.tickets) || plan.tickets.length === 0 ||
      plan.tickets.length > 120) return null;
  const seen = new Set();
  const tickets = [];
  for (const row of plan.tickets) {
    if (!plain(row) || !validCombination(row.combination) ||
        !validInt(row.yen) || row.yen % 100 !== 0 ||
        row.yen > 1_000_000 || seen.has(row.combination)) return null;
    seen.add(row.combination);
    tickets.push([row.combination, row.yen]);
  }
  tickets.sort((a, b) => a[0].localeCompare(b[0], 'en'));
  const canonical = JSON.stringify([plan.race_date, plan.stadium_number,
    plan.race_number, tickets]);
  return createHash('sha256').update(canonical).digest('hex');
}

/**
 * Journal must be supplied by the caller from durable local storage.
 * Fail closed if it is absent or corrupted. Any previous attempt for the
 * same plan, including UNKNOWN, blocks automatic replay. The user must
 * manually reconcile uncertain external outcomes; no time-based auto-reset.
 * This only checks offline eligibility; live submission always remains false.
 */
export function inspectPurchaseReplay(plan, journal) {
  const fingerprint = fingerprintPurchasePlan(plan);
  if (!fingerprint) return deny('INVALID_PURCHASE_PLAN');
  if (!Array.isArray(journal)) return deny('DURABLE_JOURNAL_REQUIRED');
  if (journal.length > 10_000) return deny('JOURNAL_TOO_LARGE');
  for (const row of journal) {
    if (!plain(row) || typeof row.fingerprint !== 'string' ||
        !/^[a-f0-9]{64}$/.test(row.fingerprint) ||
        !['PREPARED', 'SUBMITTING', 'UNKNOWN', 'CONFIRMED', 'REJECTED'].includes(row.state))
      return deny('INVALID_JOURNAL_ENTRY');
    if (row.fingerprint === fingerprint)
      return deny('DUPLICATE_OR_UNCERTAIN_SUBMISSION');
  }
  return { allowed_for_offline_dry_run: true,
    allowed_for_live_submission: false, classification: 'OFFLINE_ONLY',
    reason: 'NO_PRIOR_ATTEMPT_IN_SUPPLIED_JOURNAL',
    fingerprint };
}
