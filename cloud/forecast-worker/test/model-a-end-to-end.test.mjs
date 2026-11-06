import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { LightGbmTextModel } from '../src/lightgbm.mjs';
import { runFrozenModelAForecast } from '../src/model-a-runtime.mjs';
import { decodeModelAHistoryAsset } from '../src/model-a-history-codec.mjs';

const features = JSON.parse(readFileSync(new URL('./fixtures/python-model-a-features.json', import.meta.url)));
const golden = JSON.parse(readFileSync(new URL('./fixtures/python-model-a-end-to-end.json', import.meta.url)));
const clone = obj => JSON.parse(JSON.stringify(obj));
const stages = () => {
  const models = Array.from({ length: 3 }, (_, index) => {
    const bytes = readFileSync(new URL(`../../../app/src/main/assets/model_a_stage${index}.txt`, import.meta.url));
    assert.equal(createHash('sha256').update(bytes).digest('hex'), golden.model_sha256[`stage${index}`]);
    return LightGbmTextModel.parse(bytes.toString('utf8'));
  });
  return { stage0: row => models[0].predict(row), stage1: row => models[1].predict(row),
    stage2: row => models[2].predict(row) };
};

test('synthetic complete race -> history -> features -> all 120 Python LightGBM forecast goldens', () => {
  assert.equal(golden.schema_version, 1);
  assert.equal(golden.temperature, 1);
  assert.equal(golden.cases.length, 2);
  const models = stages();
  let maxAbsoluteError = 0;
  for (const sample of golden.cases) {
    const input = features.cases[sample.feature_case_index];
    const result = runFrozenModelAForecast(input.race, clone(input.state), models);
    assert.equal(result.available, true);
    assert.equal(result.reason, null);
    assert.equal(result.forecast.combinations.length, 120);
    assert.equal(result.forecast.combinations[0], '1-2-3');
    assert.equal(result.forecast.combinations.at(-1), '6-5-4');
    for (let index = 0; index < 120; index++) {
      const actual = result.forecast.probabilities[index];
      const expected = sample.probabilities[index];
      assert.ok(Number.isFinite(actual) && actual >= 0);
      maxAbsoluteError = Math.max(maxAbsoluteError, Math.abs(actual - expected));
    }
    assert.ok(Math.abs(result.forecast.probabilities.reduce((sum, x) => sum + x, 0) - 1) < 1e-10);
  }
  assert.ok(maxAbsoluteError < 1e-7, `End-to-end Python/JS parity discrepancy: ${maxAbsoluteError}`);
});

test('stale history and bad input never invoke any stage or invent BUY/SKIP', () => {
  const race = clone(features.cases[1].race);
  const state = clone(features.cases[1].state);
  let invocations = 0;
  const poison = { stage0: () => { invocations++; throw Error('must not score'); },
    stage1: () => { invocations++; throw Error('must not score'); },
    stage2: () => { invocations++; throw Error('must not score'); } };

  state.lastDay = features.cases[1].expected.predictionDayOrdinal - 2;
  const stale = runFrozenModelAForecast(race, state, poison);
  assert.deepEqual([stale.available, stale.reason], [false, 'MODEL_A_HISTORY_STALE']);
  assert.equal(stale.forecast, undefined);
  assert.equal(stale.buy, undefined);
  assert.equal(stale.skip, undefined);

  const invalidRace = clone(race);
  invalidRace.racers[0].preview.startTiming = null;
  const invalid = runFrozenModelAForecast(invalidRace, clone(features.cases[1].state), poison);
  assert.deepEqual([invalid.available, invalid.reason], [false, 'MODEL_A_INPUT_UNAVAILABLE']);
  assert.equal(invalid.forecast, undefined);

  const missingModels = runFrozenModelAForecast(race, clone(features.cases[1].state), {});
  assert.deepEqual([missingModels.available, missingModels.reason], [false, 'MODEL_A_MODELS_UNAVAILABLE']);
  assert.equal(invocations, 0);
});

test('actual Android history remains stale for November synthetic race and cannot be scored', () => {
  const history = decodeModelAHistoryAsset(readFileSync(
    new URL('../../../app/src/main/assets/model_a_history.bin', import.meta.url)));
  const result = runFrozenModelAForecast(features.cases[1].race, history, {
    stage0: () => { throw Error('must not score'); },
    stage1: () => { throw Error('must not score'); },
    stage2: () => { throw Error('must not score'); },
  });
  assert.equal(result.available, false);
  assert.equal(result.reason, 'MODEL_A_HISTORY_STALE');
  assert.equal(result.historyThroughDayOrdinal, 739_882);
  assert.equal(result.forecast, undefined);
});
