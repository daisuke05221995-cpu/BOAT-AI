// Frozen Model A 3-stage probability chain, ported from Android
// ModelAConditionalPredictor. The caller must supply features built with the
// frozen 82-per-boat / 24-global history-aware contract. This never reads odds.

const BOAT_FEATURES = 82;
const GLOBAL_FEATURES = 24;

export function validateModelAInput(input) {
  if (!input || !Array.isArray(input.boat) || input.boat.length !== 6 ||
      !input.boat.every(row => Array.isArray(row) && row.length === BOAT_FEATURES &&
        row.every(v => typeof v === 'number' && !Object.is(v, Infinity) && !Object.is(v, -Infinity))) ||
      !Array.isArray(input.global) || input.global.length !== GLOBAL_FEATURES ||
      !input.global.every(v => typeof v === 'number' && !Object.is(v, Infinity) && !Object.is(v, -Infinity)) ||
      !Number.isInteger(input.venue) || input.venue < 1 || input.venue > 24 ||
      !Number.isInteger(input.raceNumber) || input.raceNumber < 1 || input.raceNumber > 12) {
    throw new Error('MODEL_A_INVALID_FEATURE_INPUT');
  }
}

export function createModelAFeatureRows(input) {
  validateModelAInput(input);
  const mean = new Array(BOAT_FEATURES);
  const spread = new Array(BOAT_FEATURES);
  for (let f = 0; f < BOAT_FEATURES; f++) {
    let count = 0, sum = Math.fround(0), lo = Infinity, hi = -Infinity;
    for (let lane = 0; lane < 6; lane++) {
      const value = input.boat[lane][f];
      if (Number.isFinite(value)) {
        sum = Math.fround(sum + Math.fround(value));
        count++;
        lo = Math.min(lo, value);
        hi = Math.max(hi, value);
      }
    }
    mean[f] = count ? sum / count : NaN;
    spread[f] = count ? hi - lo : NaN;
  }
  const raw = input.boat.map(boat => [
    ...boat,
    ...boat.map((v, f) => v - mean[f]),
    ...spread,
    ...boat.map(v => Number.isFinite(v) ? 0 : 1),
  ]);
  const global = [
    ...input.global.slice(0, 22),
    ...Array.from({ length: 24 }, (_, index) => Number(input.venue === index + 1)),
    input.raceNumber,
    ...input.boat[0],
    ...input.boat[0].map((v, f) => v - mean[f]),
  ];
  if (global.length !== 211) throw new Error('MODEL_A_GLOBAL_WIDTH_MISMATCH');
  const oneHot = lane => Array.from({ length: 6 }, (_, index) => Number(index === lane));
  return (prefix, candidate) => {
    if (!Array.isArray(prefix) || prefix.length > 2 ||
        !Number.isInteger(candidate) || candidate < 0 || candidate > 5 ||
        prefix.some(p => !Number.isInteger(p) || p < 0 || p > 5) ||
        new Set([...prefix, candidate]).size !== prefix.length + 1) {
      throw new Error('MODEL_A_INVALID_PREFIX');
    }
    const values = [...raw[candidate], ...oneHot(candidate), ...global];
    for (const selected of prefix) {
      values.push(...input.boat[selected]);
      for (let f = 0; f < BOAT_FEATURES; f++) values.push(input.boat[candidate][f] - input.boat[selected][f]);
      values.push(...oneHot(selected));
    }
    if (values.length !== 545 + 170 * prefix.length) throw new Error('MODEL_A_STAGE_WIDTH_MISMATCH');
    return values.map(Math.fround);
  };
}

export const modelACombinations = Object.freeze(Array.from({ length: 6 }, (_, a) => a)
  .flatMap(first => Array.from({ length: 6 }, (_, b) => b)
    .filter(second => second !== first)
    .flatMap(second => Array.from({ length: 6 }, (_, c) => c)
      .filter(third => third !== first && third !== second)
      .map(third => `${first + 1}-${second + 1}-${third + 1}`))));

function softmax(scores) {
  if (!scores.length || !scores.every(Number.isFinite)) throw new Error('MODEL_A_INVALID_RAW_SCORE');
  const max = Math.max(...scores);
  const exp = scores.map(score => Math.exp(score - max));
  const denominator = exp.reduce((sum, value) => sum + value, 0);
  if (!(denominator > 0) || !Number.isFinite(denominator)) throw new Error('MODEL_A_INVALID_SOFTMAX');
  return exp.map(value => value / denominator);
}

export function predictModelA(input, stages, temperature = 1) {
  if (!stages || ![stages.stage0, stages.stage1, stages.stage2].every(x => typeof x === 'function') ||
      !Number.isFinite(temperature) || temperature <= 0) throw new Error('MODEL_A_INVALID_MODEL');
  const row = createModelAFeatureRows(input);
  const first = softmax(Array.from({ length: 6 }, (_, lane) => stages.stage0(row([], lane))));
  const second = Array.from({ length: 6 }, (_, firstLane) => {
    const choices = Array.from({ length: 6 }, (_, n) => n).filter(n => n !== firstLane);
    const probs = softmax(choices.map(candidate => stages.stage1(row([firstLane], candidate))));
    return Array.from({ length: 6 }, (_, lane) => {
      const index = choices.indexOf(lane);
      return index === -1 ? 0 : probs[index];
    });
  });
  const third = Array.from({ length: 6 }, () => Array.from({ length: 6 }, () => new Array(6).fill(0)));
  for (let a = 0; a < 6; a++) for (let b = 0; b < 6; b++) {
    if (a === b) continue;
    const choices = Array.from({ length: 6 }, (_, n) => n).filter(n => n !== a && n !== b);
    const probs = softmax(choices.map(candidate => stages.stage2(row([a, b], candidate))));
    choices.forEach((candidate, index) => { third[a][b][candidate] = probs[index]; });
  }
  const probabilities = modelACombinations.map(combination => {
    const [a, b, c] = combination.split('-').map(n => Number(n) - 1);
    return first[a] * second[a][b] * third[a][b][c];
  });
  const sum = probabilities.reduce((total, p) => total + p, 0);
  if (probabilities.some(p => !Number.isFinite(p) || p < 0) || Math.abs(sum - 1) > 1e-10) {
    throw new Error('MODEL_A_PROBABILITY_MASS_INVALID');
  }
  const calibrated = temperature === 1 ? probabilities : (() => {
    const powered = probabilities.map(p => Math.max(p, 1e-15) ** (1 / temperature));
    const denominator = powered.reduce((total, p) => total + p, 0);
    return powered.map(p => p / denominator);
  })();
  return { combinations: modelACombinations, probabilities: calibrated };
}
