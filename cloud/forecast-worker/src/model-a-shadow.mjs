// Forecast-only bridge: authorized pre-close snapshots -> immutable D1 assets
// -> frozen Model A 120-way probabilities. This never decides BUY/SKIP or
// modifies Android-facing forecasts. A stale/missing history fails closed.
import { assembleAuthorizedModelARace } from './model-a-live-input.mjs';
import { loadVerifiedHistoryCheckpoint } from './model-a-history-store.mjs';
import { loadVerifiedFrozenModelABundle } from './model-a-model-store.mjs';
import { runFrozenModelAForecast } from './model-a-runtime.mjs';

const HEX = /^[0-9a-f]{64}$/;
const SOURCE_KINDS = ['roster', 'preview', 'weather', 'odds'];
const reasonOf = error => String(error?.message ?? 'UNKNOWN').slice(0, 120);
const fail = reason => ({ status: 'UNAVAILABLE', reason, forecast: null,
  provenance: null, historySha256: null, modelBundleSha256: null });

export function parseShadowApprovals(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  let parsed;
  try { parsed = JSON.parse(value); } catch { throw new Error('MODEL_A_APPROVALS_INVALID'); }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object' ||
      SOURCE_KINDS.some(kind => !Array.isArray(parsed[kind]) || !parsed[kind].length ||
        !parsed[kind].every(source => typeof source === 'string' && source.length > 0 && source.length <= 100))) {
    throw new Error('MODEL_A_APPROVALS_INVALID');
  }
  return parsed;
}

function previousDayOrdinal(date) {
  const ms = Date.parse(`${date}T00:00:00Z`);
  if (!Number.isFinite(ms) || new Date(ms).toISOString().slice(0, 10) !== date) {
    throw new Error('MODEL_A_DATE_INVALID');
  }
  // Same proleptic-Gregorian ordinal used by Android/Python Model A.
  return Math.floor(ms / 86_400_000) + 719_163 - 1;
}

function cached(cache, key, create) {
  if (!cache.has(key)) cache.set(key, Promise.resolve().then(create));
  return cache.get(key);
}

export async function evaluateModelAShadow({ db, row, nowMs, rosterSnapshot,
  previewSnapshot, oddsSnapshot, approvals, bundleSha256, cache = new Map(),
  loadHistory = loadVerifiedHistoryCheckpoint,
  loadModels = loadVerifiedFrozenModelABundle }) {
  if (!rosterSnapshot || !previewSnapshot || !oddsSnapshot) return fail('MODEL_A_LIVE_SOURCES_INCOMPLETE');
  if (!approvals) return fail('MODEL_A_SOURCES_NOT_APPROVED');
  let assembled;
  try {
    assembled = assembleAuthorizedModelARace(row, rosterSnapshot, previewSnapshot,
      oddsSnapshot, nowMs, approvals);
  } catch (error) { return fail(reasonOf(error)); }
  if (!HEX.test(bundleSha256 ?? '')) return fail('MODEL_A_BUNDLE_NOT_CONFIGURED');

  let pointer;
  try { pointer = await db.prepare('SELECT * FROM model_a_history_active WHERE singleton=1').first(); }
  catch { return fail('MODEL_A_HISTORY_POINTER_UNAVAILABLE'); }
  if (!pointer || !HEX.test(pointer.sha256 ?? '')) return fail('MODEL_A_HISTORY_NOT_ACTIVE');
  if (pointer.through_day !== previousDayOrdinal(row.race_date)) return fail('MODEL_A_HISTORY_STALE');

  let history;
  let models;
  try {
    [history, models] = await Promise.all([
      cached(cache, `history:${pointer.sha256}`, () => loadHistory(db, pointer.sha256)),
      cached(cache, `models:${bundleSha256}`, () => loadModels(db, bundleSha256)),
    ]);
  } catch (error) { return fail(`MODEL_A_ASSET_LOAD_FAILED:${reasonOf(error)}`); }
  // The active pointer may be raced by an update: the verified asset must
  // still correspond to the precise previous calendar day of this race.
  if (history.sha256 !== pointer.sha256 || history.throughDay !== pointer.through_day ||
      models.bundleSha256 !== bundleSha256) return fail('MODEL_A_ASSET_POINTER_MISMATCH');
  let prediction;
  try { prediction = runFrozenModelAForecast(assembled.race, history.state, models.stages); }
  catch (error) { return fail(`MODEL_A_INFERENCE_FAILED:${reasonOf(error)}`); }
  if (!prediction.available) return fail(prediction.reason);
  const { combinations, probabilities } = prediction.forecast;
  if (combinations?.length !== 120 || probabilities?.length !== 120 ||
      probabilities.some(p => !Number.isFinite(p) || p < 0) ||
      Math.abs(probabilities.reduce((sum, p) => sum + p, 0) - 1) > 1e-8) {
    return fail('MODEL_A_PROBABILITY_INTEGRITY_FAILED');
  }
  return { status: 'FORECAST_ONLY', reason: null,
    forecast: { combinations, probabilities }, provenance: assembled.provenance,
    historySha256: history.sha256, modelBundleSha256: models.bundleSha256 };
}
