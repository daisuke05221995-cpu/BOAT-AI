import test from 'node:test';
import assert from 'node:assert/strict';
import { DatabaseSync } from 'node:sqlite';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { ModelAPlayerHistory } from '../src/model-a-history.mjs';
import { encodeModelAHistoryAsset } from '../src/model-a-history-codec.mjs';
import { HISTORY_CHUNK_BYTES, sealAndroidHistoryBase, sealReconciledHistoryDay,
  stageHistoryCheckpoint, loadVerifiedHistoryCheckpoint,
  activateVerifiedHistoryCheckpoint } from '../src/model-a-history-store.mjs';

const schema = readFileSync(new URL('../migrations/0004_model_a_history_generations.sql', import.meta.url), 'utf8');
const sha = bytes => createHash('sha256').update(bytes).digest('hex');
const makeState = () => ({ lastDay: 10, updateRaces: 1,
  stats: { global: [6, 1, 2, 3, 40, 270, 1, 0.2] },
  recent: Object.fromEntries(Array.from({ length: 6 }, (_, i) => [String(100 + i), {
    days: [10], cumulative: [[0, 0, 0], [0, 0, 1]],
  }])) });

// Small D1-compatible wrapper around real SQLite, including transactional
// batches. Local tests exercise the exact SQL used by the Worker.
function mockD1() {
  const sqlite = new DatabaseSync(':memory:');
  sqlite.exec('PRAGMA foreign_keys=ON');
  sqlite.exec(schema);
  const wrap = (sql, args = []) => ({
    bind: (...newArgs) => wrap(sql, newArgs),
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

async function checkpointPair() {
  const baseState = makeState();
  const baseBytes = encodeModelAHistoryAsset(baseState);
  const base = await sealAndroidHistoryBase(baseBytes, { bytes: baseBytes.length, sha256: sha(baseBytes) });
  const nextState = structuredClone(baseState);
  new ModelAPlayerHistory(nextState).commitDay(11,
    Array.from({ length: 6 }, (_, index) => ({ player: index + 100, course: index + 1,
      racerClass: 3, exhibitionTime: 6.8, previewStartTiming: 0.12,
      win: index === 0, top2: index <= 1, top3: index <= 2,
      flags: { fastExhibition: false, goodPreviewStart: false, courseChanged: false },
    })));
  const day = await sealReconciledHistoryDay({ state: nextState,
    audit: { status: 'VALIDATED_AGAINST_SUPPLIED_MANIFEST', historyLastDay: 11, committedRaces: 1 } }, base.sha256);
  return { base, day };
}

test('staged base and next day are verified and activated by consecutive CAS only', async () => {
  const db = mockD1();
  const { base, day } = await checkpointPair();
  await stageHistoryCheckpoint(db, base);
  await stageHistoryCheckpoint(db, day);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM model_a_history_active').first()).n, 0);
  assert.equal((await loadVerifiedHistoryCheckpoint(db, day.sha256)).throughDay, 11);
  assert.deepEqual(await activateVerifiedHistoryCheckpoint(db, base.sha256),
    { sha256: base.sha256, throughDay: 10 });
  assert.deepEqual(await activateVerifiedHistoryCheckpoint(db, day.sha256),
    { sha256: day.sha256, throughDay: 11 });
  assert.equal((await db.prepare('SELECT sha256 FROM model_a_history_active').first()).sha256, day.sha256);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM model_a_history_generation').first()).n, 2);
  await assert.rejects(activateVerifiedHistoryCheckpoint(db, base.sha256), /NONCONSECUTIVE/);
  await assert.rejects(activateVerifiedHistoryCheckpoint(db, day.sha256), /NONCONSECUTIVE/);
  db.sqlite.close();
});

test('bad chunk never activates and leaves the previously verified history untouched', async () => {
  const db = mockD1();
  const { base, day } = await checkpointPair();
  await stageHistoryCheckpoint(db, base);
  await activateVerifiedHistoryCheckpoint(db, base.sha256);
  await stageHistoryCheckpoint(db, day);
  db.sqlite.prepare(`UPDATE model_a_history_chunk SET base64_data='AA=='
    WHERE sha256=? AND chunk_index=0`).run(day.sha256);
  await assert.rejects(loadVerifiedHistoryCheckpoint(db, day.sha256), /CHUNK_CORRUPT/);
  await assert.rejects(activateVerifiedHistoryCheckpoint(db, day.sha256), /CHUNK_CORRUPT/);
  assert.equal((await db.prepare('SELECT sha256 FROM model_a_history_active').first()).sha256, base.sha256);
  db.sqlite.close();
});

test('audit tampering is detected even if history bytes have the correct checksum', async () => {
  const db = mockD1();
  const { base } = await checkpointPair();
  await stageHistoryCheckpoint(db, base);
  db.sqlite.prepare(`UPDATE model_a_history_generation SET audit_json='{"status":"VERIFIED_ANDROID_BASE","historyLastDay":999}'
    WHERE sha256=?`).run(base.sha256);
  await assert.rejects(loadVerifiedHistoryCheckpoint(db, base.sha256), /AUDIT_CORRUPT/);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM model_a_history_active').first()).n, 0);
  db.sqlite.close();
});

test('failed multi-chunk staging rolls back everything atomically', async () => {
  const db = mockD1();
  const { base } = await checkpointPair();
  const duplicate = { ...base, chunks: [base.chunks[0], base.chunks[0]] };
  await assert.rejects(stageHistoryCheckpoint(db, duplicate));
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM model_a_history_generation').first()).n, 0);
  assert.equal((await db.prepare('SELECT COUNT(*) AS n FROM model_a_history_chunk').first()).n, 0);
  db.sqlite.close();
});

test('frozen Android 4.22 MB history is sealed in D1-safe chunks and reconstituted byte-for-byte', async () => {
  const db = mockD1();
  const bytes = readFileSync(new URL('../../../app/src/main/assets/model_a_history.bin', import.meta.url));
  const base = await sealAndroidHistoryBase(bytes, { bytes: bytes.length, sha256: sha(bytes) });
  assert.ok(base.chunks.length > 1);
  assert.ok(base.chunks.every(chunk => Buffer.from(chunk.base64, 'base64').length <= HISTORY_CHUNK_BYTES));
  await stageHistoryCheckpoint(db, base);
  const restored = await loadVerifiedHistoryCheckpoint(db, base.sha256);
  assert.equal(Buffer.compare(restored.bytes, bytes), 0);
  assert.equal(restored.state.lastDay, 739_882);
  assert.equal(restored.state.updateRaces, 141_542);
  // Stored 2026-09-23 history remains dated 2026-09-23, not artificially current.
  db.sqlite.close();
});
