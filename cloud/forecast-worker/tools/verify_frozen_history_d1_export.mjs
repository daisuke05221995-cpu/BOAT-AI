#!/usr/bin/env node
// Verifies every D1-readback byte and BAH1 invariant, with no promotion to an
// active history pointer. Does not emit history content or private credentials.
import { readFileSync } from 'node:fs';
import { FROZEN_ANDROID_HISTORY_BASE, loadVerifiedHistoryCheckpoint } from '../src/model-a-history-store.mjs';

const [jsonFile, expectedSha] = process.argv.slice(2);
if (!jsonFile || process.argv.length !== 4 || expectedSha !== FROZEN_ANDROID_HISTORY_BASE.sha256) {
  throw new Error('Usage: node tools/verify_frozen_history_d1_export.mjs <wrangler-json> <expected-frozen-sha>');
}
const response = JSON.parse(readFileSync(jsonFile, 'utf8'));
const wrappers = Array.isArray(response) ? response : [response];
const rows = wrappers.flatMap(wrapper => {
  if (Array.isArray(wrapper?.results)) return wrapper.results;
  if (Array.isArray(wrapper?.result)) return wrapper.result.flatMap(result => result.results ?? []);
  return [];
});
if (rows.length !== FROZEN_ANDROID_HISTORY_BASE.chunkCount ||
    rows.some(row => row.sha256 !== expectedSha || row.kind !== 'FROZEN_BASE' ||
      row.previous_sha256 !== null || row.through_day !== FROZEN_ANDROID_HISTORY_BASE.throughDay)) {
  throw new Error('MODEL_A_HISTORY_REMOTE_D1_INCOMPLETE');
}
const metadata = rows[0];
const fields = ['kind', 'through_day', 'update_races', 'byte_length', 'chunk_count',
  'audit_json', 'audit_sha256', 'previous_sha256'];
if (rows.some(row => fields.some(key => row[key] !== metadata[key]))) {
  throw new Error('MODEL_A_HISTORY_REMOTE_D1_MIXED_METADATA');
}
const db = { prepare(sql) {
  if (sql.includes('model_a_history_generation')) return { bind: () => ({ first: async () => metadata }) };
  if (sql.includes('model_a_history_chunk')) return { bind: () => ({
    all: async () => ({ results: rows.map(({ chunk_index, chunk_sha256, base64_data }) =>
      ({ chunk_index, chunk_sha256, base64_data })) }),
  }) };
  throw new Error('MODEL_A_HISTORY_REMOTE_QUERY_UNEXPECTED');
} };
const restored = await loadVerifiedHistoryCheckpoint(db, expectedSha);
if (restored.state.lastDay !== FROZEN_ANDROID_HISTORY_BASE.throughDay ||
    restored.updateRaces !== FROZEN_ANDROID_HISTORY_BASE.updateRaces ||
    restored.bytes.length !== FROZEN_ANDROID_HISTORY_BASE.bytes ||
    Object.keys(restored.state.stats).length !== 33_363 ||
    Object.keys(restored.state.recent).length !== 1_726) {
  throw new Error('MODEL_A_HISTORY_REMOTE_D1_BASE_CHANGED');
}
process.stdout.write(JSON.stringify({ verified: true, sha256: restored.sha256,
  throughDay: restored.throughDay, updateRaces: restored.updateRaces,
  playerStats: Object.keys(restored.state.stats).length,
  racers: Object.keys(restored.state.recent).length, chunks: rows.length,
  active: false, status: 'STALE_FROZEN_BASE_ONLY' }) + '\n');
