// Offline-only, fail-closed consistency check for two Android odds receipts.
// Does not certify provider time, licensing, or authorize any forecast/purchase.
import { classifyAndroidOddsCoverage } from './android_odds_coverage_classifier.mjs';
const blocked = reason => ({status:'UNAVAILABLE',reason,eligible_for_buy:false,eligible_for_skip:false});
const plain = v => v !== null && typeof v === 'object' && !Array.isArray(v) && Object.getPrototypeOf(v) === Object.prototype;
export function compareAndroidOddsReceipts(a,b,requested, raceA,raceB) {
  if (!plain(a)||!plain(b)||!plain(raceA)||!plain(raceB)) return blocked('INVALID_INPUT');
  for (const key of ['date','stadiumNumber','raceNumber','deadlineMs']) {
    if (raceA[key] !== raceB[key] || raceA[key] == null) return blocked('RACE_IDENTITY_MISMATCH');
  }
  if (!Number.isSafeInteger(raceA.deadlineMs) || raceA.deadlineMs<=0 ||
      a.fetchedAt>=raceA.deadlineMs || b.fetchedAt>=raceA.deadlineMs)
    return blocked('LATE_OR_INVALID_DEADLINE');
  const x=classifyAndroidOddsCoverage(a,requested),y=classifyAndroidOddsCoverage(b,requested);
  if (x.classification==='UNAVAILABLE'||y.classification==='UNAVAILABLE') return blocked('INVALID_RECEIPT');
  if (x.classification!==y.classification || x.coverage!==y.coverage) return blocked('COVERAGE_OR_SOURCE_KIND_MISMATCH');
  if (x.classification==='BOATRACE_CSV_ESTIMATE') return blocked('ESTIMATED_VALUES_NOT_LIVE');
  if (a.source!==b.source) return blocked('SOURCE_LABEL_MISMATCH');
  if (Math.abs(a.fetchedAt-b.fetchedAt)>120000) return blocked('RECEIPT_TIMES_TOO_FAR_APART');
  const keys=Object.keys(a.odds);
  if (keys.some(k=>a.odds[k]!==b.odds[k])) return blocked('ODDS_VALUES_DISAGREE');
  return {status:'CONSISTENT_DEVICE_RECEIPTS_ONLY',reason:'INDEPENDENT_SOURCE_TIME_AND_RIGHTS_UNVERIFIED',
    coverage:x.coverage,combination_count:keys.length,eligible_for_forecast:false,
    eligible_for_buy:false,eligible_for_skip:false,source_time_independently_verified:false,
    source_rights_independently_verified:false};
}
