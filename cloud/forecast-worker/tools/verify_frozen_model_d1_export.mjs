#!/usr/bin/env node
// Verify a temporary authenticated Wrangler JSON query against every original
// Android stage SHA-256. Does not write to D1 or emit model contents.
import { readFileSync } from 'node:fs';
import { loadVerifiedFrozenModelABundle } from '../src/model-a-model-store.mjs';
import { runFrozenModelAForecast } from '../src/model-a-runtime.mjs';

const [path, expectedSha] = process.argv.slice(2);
if (!path || !/^[0-9a-f]{64}$/.test(expectedSha ?? '') || process.argv.length !== 4) {
  throw new Error('Usage: node tools/verify_frozen_model_d1_export.mjs <wrangler-json> <expected-sha256>');
}
const envelope = JSON.parse(readFileSync(path, 'utf8'));
const wrappers = Array.isArray(envelope) ? envelope : [envelope];
const rows = wrappers.flatMap(wrapper => {
  if (Array.isArray(wrapper?.results)) return wrapper.results;
  if (Array.isArray(wrapper?.result)) return wrapper.result.flatMap(result => result.results ?? []);
  return [];
});
if (rows.length !== 12 || rows.some(row => row.bundle_sha256 !== expectedSha ||
    typeof row.stage_manifest_json !== 'string')) throw new Error('MODEL_A_REMOTE_D1_INCOMPLETE');
const savedManifest = rows[0].stage_manifest_json;
if (rows.some(row => row.stage_manifest_json !== savedManifest)) throw new Error('MODEL_A_REMOTE_D1_MIXED_MANIFESTS');

// Reuse the same independent read-side checksum, parse, and feature-width
// boundary as the Cloudflare Worker. No synthetic success based on row count.
const db = { prepare(sql) {
  if (sql.includes('model_a_frozen_bundle')) return { bind: () => ({
    first: async () => ({ stage_manifest_json: savedManifest }),
  }) };
  if (sql.includes('model_a_frozen_chunk')) return { bind: () => ({
    all: async () => ({ results: rows.map(({ stage_index, chunk_index, chunk_sha256, base64_data }) =>
      ({ stage_index, chunk_index, chunk_sha256, base64_data })) }),
  }) };
  throw new Error('UNEXPECTED_REMOTE_QUERY');
} };
const verified = await loadVerifiedFrozenModelABundle(db, expectedSha);
if (verified.models.length !== 3) throw new Error('MODEL_A_REMOTE_D1_INVALID_MODEL_COUNT');
// These are immutable, synthetic end-to-end independent Python LightGBM
// goldens, not real-time forecasts or a retrospective tuning experiment.
// Verify that the ACTUAL D1-loaded bytes also produce all 120 trifecta
// probabilities, not merely a parsable model tree with the expected hash.
const features = JSON.parse(readFileSync(new URL('../test/fixtures/python-model-a-features.json', import.meta.url), 'utf8'));
const golden = JSON.parse(readFileSync(new URL('../test/fixtures/python-model-a-end-to-end.json', import.meta.url), 'utf8'));
if (golden.schema_version !== 1 || golden.temperature !== 1 || golden.cases.length !== 2 ||
    verified.models.some((_, index) =>
      golden.model_sha256[`stage${index}`] !== JSON.parse(savedManifest)[index].sha256)) {
  throw new Error('MODEL_A_REMOTE_D1_GOLDEN_MISMATCH');
}
let maxAbsoluteError = 0;
for (const sample of golden.cases) {
  const input = features.cases[sample.feature_case_index];
  if (!input || sample.probabilities?.length !== 120) throw new Error('MODEL_A_REMOTE_D1_GOLDEN_INVALID');
  const forecast = runFrozenModelAForecast(input.race, structuredClone(input.state), verified.stages);
  if (!forecast.available || forecast.forecast?.probabilities?.length !== 120 ||
      forecast.forecast.combinations[0] !== '1-2-3' ||
      forecast.forecast.combinations.at(-1) !== '6-5-4') throw new Error('MODEL_A_REMOTE_D1_PARITY_UNAVAILABLE');
  for (let i = 0; i < 120; i++) {
    const actual = forecast.forecast.probabilities[i];
    if (!Number.isFinite(actual) || actual < 0) throw new Error('MODEL_A_REMOTE_D1_NONFINITE_PROBABILITY');
    maxAbsoluteError = Math.max(maxAbsoluteError, Math.abs(actual - sample.probabilities[i]));
  }
  if (Math.abs(forecast.forecast.probabilities.reduce((sum, value) => sum + value, 0) - 1) >= 1e-10) {
    throw new Error('MODEL_A_REMOTE_D1_PROBABILITY_SUM');
  }
}
if (maxAbsoluteError >= 1e-7) throw new Error(`MODEL_A_REMOTE_D1_PARITY_DIFF_${maxAbsoluteError}`);
process.stdout.write(JSON.stringify({ verified: true, bundleSha256: expectedSha,
  models: verified.models.length, featureWidths: verified.models.map(model => model.featureCount),
  remoteChunks: rows.length, parityCases: golden.cases.length, parityProbabilities: golden.cases.length * 120,
  maxAbsoluteError }) + '\n');
