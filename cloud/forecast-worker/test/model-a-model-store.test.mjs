import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { LightGbmTextModel } from '../src/lightgbm.mjs';
import { FROZEN_MODEL_A_STAGE_MANIFEST, MODEL_ASSET_CHUNK_BYTES,
  sealFrozenModelABundle, stageFrozenModelABundle,
  loadVerifiedFrozenModelABundle } from '../src/model-a-model-store.mjs';

const schema = readFileSync(new URL('../migrations/0007_model_a_frozen_assets.sql', import.meta.url), 'utf8');
const assets = () => Array.from({ length: 3 }, (_, index) => readFileSync(
  new URL(`../../../app/src/main/assets/model_a_stage${index}.txt`, import.meta.url)));

function d1() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec('PRAGMA foreign_keys=ON');
  sqlite.exec(schema);
  const wrap = (sql, args = []) => ({
    bind: (...values) => wrap(sql, values),
    run: async () => ({ meta: { changes: sqlite.prepare(sql).run(...args).changes } }),
    first: async () => sqlite.prepare(sql).get(...args) ?? null,
    all: async () => ({ results: sqlite.prepare(sql).all(...args) }),
    execute: () => sqlite.prepare(sql).run(...args),
  });
  return {
    sqlite,
    prepare: sql => wrap(sql),
    batch: async statements => {
      sqlite.exec('BEGIN');
      try {
        const result = statements.map(statement => statement.execute());
        sqlite.exec('COMMIT');
        return result.map(row => ({ meta: { changes: row.changes } }));
      } catch (error) { sqlite.exec('ROLLBACK'); throw error; }
    },
  };
}

test('frozen Android models are SHA-verified, staged in small D1 chunks and loaded unmodified', async () => {
  const bytes = assets();
  const bundle = await sealFrozenModelABundle(bytes);
  assert.equal(bundle.manifest.length, 3);
  assert.deepEqual(bundle.manifest.map(x => x.featureCount), [545, 715, 885]);
  assert.equal(bundle.chunks.length, 12);
  assert.ok(bundle.chunks.every(x => Buffer.from(x.base64, 'base64').length <= MODEL_ASSET_CHUNK_BYTES));
  const db = d1();
  try {
    await stageFrozenModelABundle(db, bundle);
    const restored = await loadVerifiedFrozenModelABundle(db, bundle.bundleSha256);
    assert.deepEqual(restored.models.map(x => x.featureCount), [545, 715, 885]);
    assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM model_a_frozen_bundle').get().n, 1);
    const expected = bytes.map(b => LightGbmTextModel.parse(b.toString('utf8')));
    for (let i = 0; i < 3; i++) {
      const row = Array.from({ length: FROZEN_MODEL_A_STAGE_MANIFEST[i].featureCount },
        (_, index) => Math.fround((index % 37 - 18) / 13));
      assert.equal(restored.models[i].predict(row), expected[i].predict(row));
    }
  } finally { db.sqlite.close(); }
});

test('invalid asset hash, wrong stage count and corrupt D1 chunk fail closed', async () => {
  const bytes = assets();
  await assert.rejects(sealFrozenModelABundle(bytes.slice(0, 2)), /STAGE_COUNT/);
  const changed = bytes.map(b => Uint8Array.from(b));
  changed[1][55] ^= 1;
  await assert.rejects(sealFrozenModelABundle(changed), /SHA256_MISMATCH/);
  const bundle = await sealFrozenModelABundle(bytes);
  const db = d1();
  try {
    await stageFrozenModelABundle(db, bundle);
    db.sqlite.prepare(`UPDATE model_a_frozen_chunk SET base64_data='AA=='
      WHERE bundle_sha256=? AND stage_index=1 AND chunk_index=0`).run(bundle.bundleSha256);
    await assert.rejects(loadVerifiedFrozenModelABundle(db, bundle.bundleSha256), /CHUNK_CORRUPT/);
    // No active pointer exists, so an unverified or stale bundle is never an
    // operational forecast even if its metadata remains in D1.
    assert.equal(db.sqlite.prepare(`SELECT COUNT(*) AS n FROM sqlite_master
      WHERE name='model_a_frozen_active'`).get().n, 0);
  } finally { db.sqlite.close(); }
});

test('staging remains atomic on a duplicate chunk failure', async () => {
  const bundle = await sealFrozenModelABundle(assets());
  const db = d1();
  try {
    const bad = { ...bundle, chunks: [...bundle.chunks.slice(0, 11), bundle.chunks[0]] };
    await assert.rejects(stageFrozenModelABundle(db, bad));
    assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM model_a_frozen_bundle').get().n, 0);
    assert.equal(db.sqlite.prepare('SELECT COUNT(*) AS n FROM model_a_frozen_chunk').get().n, 0);
  } finally { db.sqlite.close(); }
});
