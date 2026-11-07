#!/usr/bin/env node
// Verify a temporary authenticated Wrangler JSON query against every original
// Android stage SHA-256. Does not write to D1 or emit model contents.
import { readFileSync } from 'node:fs';
import { loadVerifiedFrozenModelABundle } from '../src/model-a-model-store.mjs';

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
process.stdout.write(JSON.stringify({ verified: true, bundleSha256: expectedSha,
  models: verified.models.length, featureWidths: verified.models.map(model => model.featureCount),
  remoteChunks: rows.length }) + '\n');
