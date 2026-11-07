// Immutable, dormant D1 staging for frozen Android Model A LightGBM assets.
// No Worker forecast route, cron or purchase policy uses this until verified
// fresh historical data and licensed live inputs are available.
import { LightGbmTextModel } from './lightgbm.mjs';

export const FROZEN_MODEL_A_STAGE_MANIFEST = Object.freeze([
  Object.freeze({ bytes: 870836, sha256: 'ee67bc585ad4b19904d64ea8c77e25964ed41887b58e94a425bbd10c1d5a1a45', featureCount: 545 }),
  Object.freeze({ bytes: 866899, sha256: 'ad8425277311dd7080b0a05f719a322632d5993ab4382cadc721f152ddcfb1e7', featureCount: 715 }),
  Object.freeze({ bytes: 847788, sha256: '23e78898a8229794d5c1b819297d2cb77d23ec07edeb4ab6cb07a7d5758eac8a', featureCount: 885 }),
]);

export const MODEL_ASSET_CHUNK_BYTES = 256 * 1024;
// D1 limits each SQL statement to 100KB, even when the row itself can hold
// 2MB. SQL-file imports use small idempotent appends; Worker-bound parameters
// in stageFrozenModelABundle are not subject to large SQL *text* statements.
export const MODEL_SQL_LITERAL_CHARS = 64 * 1024;
const HEX = /^[0-9a-f]{64}$/;
const encoder = new TextEncoder();
const decoder = new TextDecoder('utf-8', { fatal: true });
const fail = message => { throw new Error(`MODEL_A_FROZEN_ASSET_${message}`); };

async function sha256(bytes) {
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', bytes)),
    byte => byte.toString(16).padStart(2, '0')).join('');
}

function asBytes(value) {
  if (!(value instanceof Uint8Array) || !value.length) fail('INVALID_BYTES');
  return value;
}

function base64Encode(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i += 8192) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 8192));
  }
  return btoa(binary);
}

function base64Decode(value) {
  if (typeof value !== 'string' || !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(value)) {
    fail('CORRUPT_CHUNK');
  }
  const binary = atob(value);
  return Uint8Array.from(binary, character => character.charCodeAt(0));
}

function readModel(bytes, stage) {
  let model;
  try { model = LightGbmTextModel.parse(decoder.decode(bytes)); }
  catch { fail('MODEL_PARSE_FAILED'); }
  if (model.featureCount !== FROZEN_MODEL_A_STAGE_MANIFEST[stage].featureCount) fail('FEATURE_WIDTH_MISMATCH');
  return model;
}

// Seal only the exact 3 model assets shipped with Android. This is not a
// retraining hook and cannot accept an arbitrary model from a feed or D1.
export async function sealFrozenModelABundle(bytesByStage) {
  if (!Array.isArray(bytesByStage) || bytesByStage.length !== 3) fail('STAGE_COUNT');
  const chunks = [];
  for (let stage = 0; stage < 3; stage++) {
    const bytes = asBytes(bytesByStage[stage]);
    const expected = FROZEN_MODEL_A_STAGE_MANIFEST[stage];
    if (bytes.length !== expected.bytes || await sha256(bytes) !== expected.sha256) fail('SHA256_MISMATCH');
    readModel(bytes, stage);
    for (let at = 0, index = 0; at < bytes.length; at += MODEL_ASSET_CHUNK_BYTES, index++) {
      const part = bytes.subarray(at, at + MODEL_ASSET_CHUNK_BYTES);
      chunks.push({ stage, index, sha256: await sha256(part), base64: base64Encode(part) });
    }
  }
  const manifest = FROZEN_MODEL_A_STAGE_MANIFEST.map((stage, index) => ({ ...stage,
    chunks: chunks.filter(chunk => chunk.stage === index).length }));
  const bundleSha256 = await sha256(encoder.encode(JSON.stringify(manifest)));
  return { bundleSha256, manifest, chunks };
}

// CLI import path for an authenticated GitHub Actions deployment. Wrangler
// imports SQL files without explicit BEGIN/COMMIT directives; each immutable
// entry is inserted only when absent, so interrupted imports are resumable.
// No active model pointer exists and no forecast is enabled by this SQL.
export function renderFrozenModelABundleSql(bundle, stagedMs = Date.now()) {
  if (!HEX.test(bundle?.bundleSha256 ?? '') ||
      !Array.isArray(bundle?.manifest) || bundle.manifest.length !== 3 ||
      !Array.isArray(bundle?.chunks) || bundle.chunks.length !== 12 ||
      !Number.isSafeInteger(stagedMs) || stagedMs < 0) fail('INVALID_SQL_EXPORT');
  for (let stage = 0; stage < 3; stage++) {
    const value = bundle.manifest[stage];
    const expected = FROZEN_MODEL_A_STAGE_MANIFEST[stage];
    if (value.bytes !== expected.bytes || value.sha256 !== expected.sha256 ||
        value.featureCount !== expected.featureCount || value.chunks !== 4) fail('INVALID_SQL_EXPORT');
  }
  const q = value => `'${String(value).replaceAll("'", "''")}'`;
  const statements = [
    `INSERT OR IGNORE INTO model_a_frozen_bundle (bundle_sha256, stage_manifest_json, staged_ms) VALUES (${q(bundle.bundleSha256)}, ${q(JSON.stringify(bundle.manifest))}, ${stagedMs});`,
  ];
  for (let stage = 0; stage < 3; stage++) for (let index = 0; index < 4; index++) {
    const chunk = bundle.chunks[stage * 4 + index];
    if (chunk?.stage !== stage || chunk?.index !== index ||
        !HEX.test(chunk.sha256 ?? '') ||
        typeof chunk.base64 !== 'string' ||
        !/^[A-Za-z0-9+/]+={0,2}$/.test(chunk.base64)) fail('INVALID_SQL_EXPORT');
    statements.push(`INSERT OR IGNORE INTO model_a_frozen_chunk (bundle_sha256, stage_index, chunk_index, chunk_sha256, base64_data) VALUES (${q(bundle.bundleSha256)}, ${stage}, ${index}, ${q(chunk.sha256)}, '');`);
    for (let at = 0; at < chunk.base64.length; at += MODEL_SQL_LITERAL_CHARS) {
      const piece = chunk.base64.slice(at, at + MODEL_SQL_LITERAL_CHARS);
      statements.push(`UPDATE model_a_frozen_chunk SET base64_data=base64_data || ${q(piece)} WHERE bundle_sha256=${q(bundle.bundleSha256)} AND stage_index=${stage} AND chunk_index=${index} AND length(base64_data)=${at};`);
    }
  }
  if (statements.some(statement => encoder.encode(statement).length > 100_000)) fail('SQL_STATEMENT_TOO_LARGE');
  return `${statements.join('\n')}\n`;
}

// A single D1 batch gives atomic staging, not activation. Existing generations
// are kept; no DELETE, overwrite, or current-forecast pointer is touched.
export async function stageFrozenModelABundle(db, bundle, stagedMs = Date.now()) {
  if (!bundle || !HEX.test(bundle.bundleSha256 ?? '') || !Number.isFinite(stagedMs) ||
      !Array.isArray(bundle.chunks) || bundle.chunks.length !== 12 ||
      !Array.isArray(bundle.manifest) || bundle.manifest.length !== 3) fail('INVALID_STAGE');
  const insert = db.prepare(`INSERT INTO model_a_frozen_bundle
    (bundle_sha256, stage_manifest_json, staged_ms) VALUES (?, ?, ?)`)
    .bind(bundle.bundleSha256, JSON.stringify(bundle.manifest), stagedMs);
  const addChunk = db.prepare(`INSERT INTO model_a_frozen_chunk
    (bundle_sha256, stage_index, chunk_index, chunk_sha256, base64_data) VALUES (?, ?, ?, ?, ?)`);
  await db.batch([insert, ...bundle.chunks.map(chunk => addChunk.bind(bundle.bundleSha256,
    chunk.stage, chunk.index, chunk.sha256, chunk.base64))]);
}

export async function loadVerifiedFrozenModelABundle(db, bundleSha256) {
  if (!HEX.test(bundleSha256 ?? '')) fail('INVALID_ID');
  const stored = await db.prepare('SELECT * FROM model_a_frozen_bundle WHERE bundle_sha256=?')
    .bind(bundleSha256).first();
  if (!stored) fail('NOT_FOUND');
  let manifest;
  try { manifest = JSON.parse(stored.stage_manifest_json); } catch { fail('MANIFEST_CORRUPT'); }
  if (!Array.isArray(manifest) || manifest.length !== 3) fail('MANIFEST_CORRUPT');
  const expected = FROZEN_MODEL_A_STAGE_MANIFEST;
  for (let i = 0; i < 3; i++) {
    if (manifest[i]?.bytes !== expected[i].bytes || manifest[i]?.sha256 !== expected[i].sha256 ||
        manifest[i]?.featureCount !== expected[i].featureCount || manifest[i]?.chunks !== 4) fail('MANIFEST_MISMATCH');
  }
  if (await sha256(encoder.encode(JSON.stringify(manifest))) !== bundleSha256) fail('MANIFEST_SHA256_MISMATCH');
  const { results: rows } = await db.prepare(`SELECT stage_index, chunk_index, chunk_sha256, base64_data
    FROM model_a_frozen_chunk WHERE bundle_sha256=? ORDER BY stage_index, chunk_index`).bind(bundleSha256).all();
  if (!rows || rows.length !== 12) fail('MISSING_CHUNKS');
  const models = [];
  for (let stage = 0; stage < 3; stage++) {
    const parts = [];
    let total = 0;
    for (let index = 0; index < 4; index++) {
      const row = rows[stage * 4 + index];
      if (row.stage_index !== stage || row.chunk_index !== index) fail('CHUNK_SEQUENCE');
      const bytes = base64Decode(row.base64_data);
      if (!bytes.length || bytes.length > MODEL_ASSET_CHUNK_BYTES || await sha256(bytes) !== row.chunk_sha256) fail('CHUNK_CORRUPT');
      total += bytes.length;
      parts.push(bytes);
    }
    if (total !== expected[stage].bytes) fail('STAGE_LENGTH_MISMATCH');
    const joined = new Uint8Array(total);
    let offset = 0;
    for (const part of parts) { joined.set(part, offset); offset += part.length; }
    if (await sha256(joined) !== expected[stage].sha256) fail('STAGE_SHA256_MISMATCH');
    models.push(readModel(joined, stage));
  }
  return { bundleSha256, models, stages: {
    stage0: row => models[0].predict(row),
    stage1: row => models[1].predict(row),
    stage2: row => models[2].predict(row),
  } };
}
