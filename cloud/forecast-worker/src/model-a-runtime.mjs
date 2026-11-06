// Side-effect-free frozen Model A inference boundary for a future licensed
// live-data adapter. No network, persistent writes, odds or BUY/SKIP policy.
// In particular, a valid historical asset MUST NOT be treated as current.
import { ModelAPlayerHistory } from './model-a-history.mjs';
import { buildModelAFeatures } from './model-a-features.mjs';
import { predictModelA } from './model-a-chain.mjs';

export function runFrozenModelAForecast(race, historyState, stages) {
  const history = new ModelAPlayerHistory(historyState);
  const features = buildModelAFeatures(race, history);
  if (!features.usable) {
    return {
      available: false, reason: 'MODEL_A_INPUT_UNAVAILABLE', detail: features.reason,
      predictionDayOrdinal: features.predictionDayOrdinal,
      historyThroughDayOrdinal: features.historyThroughDayOrdinal,
    };
  }
  if (!features.historyFreshForDay) {
    return {
      available: false, reason: 'MODEL_A_HISTORY_STALE',
      detail: 'Complete previous-calendar-day player history not verified',
      predictionDayOrdinal: features.predictionDayOrdinal,
      historyThroughDayOrdinal: features.historyThroughDayOrdinal,
    };
  }
  if (typeof stages?.stage0 !== 'function' || typeof stages?.stage1 !== 'function' ||
      typeof stages?.stage2 !== 'function') {
    return { available: false, reason: 'MODEL_A_MODELS_UNAVAILABLE', detail: 'Frozen stage models not loaded',
      predictionDayOrdinal: features.predictionDayOrdinal,
      historyThroughDayOrdinal: features.historyThroughDayOrdinal };
  }
  return {
    available: true, reason: null,
    predictionDayOrdinal: features.predictionDayOrdinal,
    historyThroughDayOrdinal: features.historyThroughDayOrdinal,
    forecast: predictModelA(features.input, stages, 1),
  };
}
