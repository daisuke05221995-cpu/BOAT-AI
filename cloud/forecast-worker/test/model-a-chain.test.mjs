import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { LightGbmTextModel } from '../src/lightgbm.mjs';
import { createModelAFeatureRows, predictModelA, modelACombinations } from '../src/model-a-chain.mjs';

const input = () => ({
  boat: Array.from({ length: 6 }, (_, lane) => Array.from({ length: 82 }, (_, feature) =>
    (lane + 1) * 0.1 + feature * 0.003)),
  global: Array.from({ length: 24 }, (_, index) => index * 0.05),
  venue: 7, raceNumber: 9,
});

test('LightGBM numeric split and NaN routing match Android fixture', () => {
  const model = LightGbmTextModel.parse(`tree\nversion=v4\nnum_class=1\nnum_tree_per_iteration=1\nmax_feature_idx=1
Tree=0\nnum_leaves=3\nnum_cat=0\nsplit_feature=0 1\nthreshold=1.5 0.0
decision_type=2 10\nleft_child=-1 -2\nright_child=1 -3\nleaf_value=0.25 1.5 -2.0
is_linear=0\nshrinkage=1\nend of trees`);
  assert.equal(model.treeCount, 1);
  assert.equal(model.featureCount, 2);
  assert.equal(model.predict([1, 99]), 0.25);
  assert.equal(model.predict([2, NaN]), 1.5);
  assert.equal(model.predict([2, -0.1]), 1.5);
  assert.equal(model.predict([2, 0.1]), -2.0);
});

test('LightGBM sums serialized trees and refuses categorical/linear model drift', () => {
  const model = LightGbmTextModel.parse(`tree\nnum_class=1\nnum_tree_per_iteration=1\nmax_feature_idx=0
Tree=0\nnum_leaves=2\nnum_cat=0\nsplit_feature=0\nthreshold=0
decision_type=2\nleft_child=-1\nright_child=-2\nleaf_value=0.3 0.7\nis_linear=0
Tree=1\nnum_leaves=2\nnum_cat=0\nsplit_feature=0\nthreshold=1
decision_type=8\nleft_child=-1\nright_child=-2\nleaf_value=-0.2 0.4\nis_linear=0
end of trees`);
  assert.ok(Math.abs(model.predict([-1]) - 0.1) < 1e-12);
  assert.ok(Math.abs(model.predict([0.5]) - 0.5) < 1e-12);
  assert.ok(Math.abs(model.predict([NaN]) - 0.7) < 1e-12);
  assert.throws(() => LightGbmTextModel.parse(`max_feature_idx=0\nTree=0\nnum_leaves=2
num_cat=1\nsplit_feature=0\nthreshold=0\ndecision_type=1
left_child=-1\nright_child=-2\nleaf_value=0 1\nis_linear=0\nend of trees`), /UNSUPPORTED_LIGHTGBM_TREE/);
});

test('frozen Model A stage rows have widths 545/715/885 and float32 missing flags', () => {
  const values = input();
  values.boat[2][7] = NaN;
  const row = createModelAFeatureRows(values);
  assert.equal(row([], 0).length, 545);
  assert.equal(row([1], 0).length, 715);
  const missing = row([0, 1], 2);
  assert.equal(missing.length, 885);
  assert.equal(missing[82 * 3 + 7], 1);
  assert.ok(missing.some(Number.isNaN));
  assert.ok(missing.every(v => !Object.is(v, Infinity) && !Object.is(v, -Infinity)));
});

test('frozen Model A probability chain preserves 120 permutation order and mass', () => {
  const stages = { stage0: () => 0, stage1: () => 0, stage2: () => 0 };
  const forecast = predictModelA(input(), stages);
  assert.equal(forecast.combinations.length, 120);
  assert.equal(forecast.combinations[0], '1-2-3');
  assert.equal(forecast.combinations.at(-1), '6-5-4');
  assert.equal(new Set(modelACombinations).size, 120);
  assert.ok(forecast.probabilities.every(p => Math.abs(p - 1 / 120) < 1e-12));
  assert.ok(Math.abs(forecast.probabilities.reduce((sum, p) => sum + p, 0) - 1) < 1e-12);
});

test('lane-sensitive scoring and temperature yield normalized nonuniform probabilities', () => {
  const laneScore = row => row.slice(82 * 4, 82 * 4 + 6).indexOf(1);
  const stages = { stage0: laneScore, stage1: laneScore, stage2: laneScore };
  const forecast = predictModelA(input(), stages, 1.2);
  assert.ok(forecast.probabilities.every(p => p > 0 && Number.isFinite(p)));
  assert.ok(Math.abs(forecast.probabilities.reduce((sum, p) => sum + p, 0) - 1) < 1e-12);
  const firstMarginal = Array.from({ length: 6 }, (_, lane) => forecast.probabilities.reduce(
    (sum, p, i) => sum + (Number(forecast.combinations[i][0]) === lane + 1 ? p : 0), 0));
  assert.ok(firstMarginal.every((p, i) => i === 0 || p > firstMarginal[i - 1]));
});

test('actual Android frozen LightGBM model assets parse and score finite stage rows', () => {
  const rows = createModelAFeatureRows(input());
  for (let stage = 0; stage < 3; stage++) {
    const contents = readFileSync(new URL(`../../../app/src/main/assets/model_a_stage${stage}.txt`, import.meta.url), 'utf8');
    const model = LightGbmTextModel.parse(contents);
    const vector = rows(Array.from({ length: stage }, (_, i) => i), stage);
    assert.equal(model.featureCount, [545, 715, 885][stage]);
    assert.ok(model.treeCount > 0);
    assert.ok(Number.isFinite(model.predict(vector)));
  }
});

test('real frozen three-stage models produce finite 120-way forecast on deterministic features', () => {
  const models = Array.from({ length: 3 }, (_, stage) => LightGbmTextModel.parse(readFileSync(
    new URL(`../../../app/src/main/assets/model_a_stage${stage}.txt`, import.meta.url), 'utf8')));
  const forecast = predictModelA(input(), {
    stage0: row => models[0].predict(row),
    stage1: row => models[1].predict(row),
    stage2: row => models[2].predict(row),
  });
  assert.equal(forecast.probabilities.length, 120);
  assert.ok(forecast.probabilities.every(p => Number.isFinite(p) && p >= 0));
  assert.ok(Math.abs(forecast.probabilities.reduce((sum, p) => sum + p, 0) - 1) < 1e-10);
});

test('all 120 Model A probabilities match independent Python LightGBM v4.6 goldens', () => {
  const fixture = JSON.parse(readFileSync(new URL('./fixtures/python-model-a-parity.json', import.meta.url), 'utf8'));
  assert.equal(fixture.schema_version, 1);
  assert.equal(fixture.temperature, 1);
  assert.equal(fixture.cases.length, 4);
  const models = Array.from({ length: 3 }, (_, stage) => {
    const content = readFileSync(new URL(`../../../app/src/main/assets/model_a_stage${stage}.txt`, import.meta.url));
    const hash = createHash('sha256').update(content).digest('hex');
    assert.equal(hash, fixture.model_sha256[`stage${stage}`]);
    return LightGbmTextModel.parse(content.toString('utf8'));
  });
  let maxAbsoluteError = 0;
  for (const sample of fixture.cases) {
    const input = {
      ...sample.input,
      boat: sample.input.boat.map(lane => lane.map(value => value === null ? NaN : value)),
      global: sample.input.global.map(value => value === null ? NaN : value),
    };
    const actual = predictModelA(input, {
      stage0: values => models[0].predict(values),
      stage1: values => models[1].predict(values),
      stage2: values => models[2].predict(values),
    });
    assert.equal(actual.probabilities.length, 120);
    sample.probabilities.forEach((expected, index) => {
      maxAbsoluteError = Math.max(maxAbsoluteError, Math.abs(expected - actual.probabilities[index]));
    });
  }
  assert.ok(maxAbsoluteError < 1e-7, `Python LightGBM discrepancy: ${maxAbsoluteError}`);
});
