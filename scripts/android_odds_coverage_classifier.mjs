// Offline provenance classifier for existing Android odds. No network, wagering or persistence.
// A source label alone is never proof of the provider observation timestamp or reuse rights.
const own = (o,k) => Object.prototype.hasOwnProperty.call(o,k);
const plain = o => o !== null && typeof o === 'object' && !Array.isArray(o) &&
  Object.getPrototypeOf(o) === Object.prototype;
const sourceNames = new Set(['公式PC版','公式スマホ版']);
const fail = reason => ({
  classification:'UNAVAILABLE', reason, coverage:'UNAVAILABLE',
  eligible_for_forecast:false, eligible_for_buy:false, eligible_for_skip:false,
  source_time_independently_verified:false, source_rights_independently_verified:false,
});
const combination = v => typeof v === 'string' && /^[1-6]-[1-6]-[1-6]$/.test(v) &&
  new Set(v.split('-')).size === 3;
const expected = new Set(Array.from({length:6},(_,i)=>i+1).flatMap(a=>
  Array.from({length:6},(_,i)=>i+1).filter(b=>b!==a).flatMap(b=>
    Array.from({length:6},(_,i)=>i+1).filter(c=>c!==a&&c!==b).map(c=>`${a}-${b}-${c}`))));
/**
 * Classification only, not a feed adapter.
 * Input result is the existing Android OddsFetchResult data shape.
 * requested is the explicit caller-requested set, never inferred from the returned odds.
 * Any mixed/unknown source or suspicious payload is UNAVAILABLE, not SKIP.
 */
export function classifyAndroidOddsCoverage(result, requested) {
  if (!plain(result) || !plain(result.odds) || typeof result.source !== 'string' ||
      !Array.isArray(result.diagnostics) || !Number.isSafeInteger(result.fetchedAt) ||
      result.fetchedAt <= 0 || !Array.isArray(requested) ||
      requested.length < 1 || requested.length > 120 ||
      requested.some(v=>!combination(v)) || new Set(requested).size!==requested.length)
    return fail('INVALID_RESULT_OR_REQUEST');
  const keys=Object.keys(result.odds);
  if (keys.length===0 || keys.length>120 || keys.some(v=>!combination(v)) ||
      keys.some(k=>!Number.isFinite(result.odds[k]) || result.odds[k]<=0) ||
      keys.some(k=>!expected.has(k)))
    return fail('INVALID_ODDS_MAP');
  if (requested.some(k=>!own(result.odds,k)))
    return fail('REQUESTED_COMBINATION_MISSING');
  // An unexpected extra combination is not proof that a full snapshot was requested.
  if (keys.some(k=>!requested.includes(k)))
    return fail('UNREQUESTED_COMBINATION_PRESENT');
  if (/BoatraceCSV|推定|予備/.test(result.source))
    return {
      ...fail('ESTIMATED_NOT_OBSERVED'), classification:'BOATRACE_CSV_ESTIMATE',
      coverage: keys.length===120?'ESTIMATED_120_VALUES':'ESTIMATED_SELECTED_ONLY',
      combination_count:keys.length,
    };
  if (!sourceNames.has(result.source)) return fail('UNKNOWN_SOURCE_LABEL');
  const full = requested.length===120 && keys.length===120 &&
    [...expected].every(k=>own(result.odds,k));
  return {
    ...fail('UNVERIFIED_SOURCE_TIME_AND_RIGHTS'),
    classification: full?'ANDROID_120_VALUES_UNATTESTED':'ANDROID_SELECTED_ONLY',
    coverage: full?'120_COMBINATIONS_PRESENT':'SELECTED_COMBINATIONS_ONLY',
    combination_count:keys.length,
  };
}
