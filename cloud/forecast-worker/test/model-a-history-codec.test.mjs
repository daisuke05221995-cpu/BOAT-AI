import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { decodeModelAHistoryAsset, verifyModelAHistoryAsset } from '../src/model-a-history-codec.mjs';
import { ModelAPlayerHistory } from '../src/model-a-history.mjs';

const assetUrl = new URL('../../../app/src/main/assets/model_a_history.bin', import.meta.url);
const manifestUrl = new URL('../../../app/src/main/assets/model_a_deployment.json', import.meta.url);

test('actual frozen Android BAH1 history hash and binary data decode exactly', async () => {
  const bytes = readFileSync(assetUrl);
  const manifest = JSON.parse(readFileSync(manifestUrl, 'utf8')).assets['model_a_history.bin'];
  assert.equal(bytes.length, 4_222_646);
  assert.equal(createHash('sha256').update(bytes).digest('hex'), manifest.sha256);
  const state = await verifyModelAHistoryAsset(bytes, manifest);
  assert.equal(state.lastDay, 739_882); // Android frozen history through 2026-09-23.
  assert.equal(state.updateRaces, 141_542);
  assert.equal(Object.keys(state.stats).length, 33_363);
  assert.equal(Object.keys(state.recent).length, 1_726);
  const appearances = Object.values(state.recent).reduce((sum, row) => sum + row.days.length, 0);
  assert.equal(appearances, state.updateRaces * 6);
  assert.ok(state.stats.global[0] > 0);
  assert.ok(Object.values(state.recent).every(({ days, cumulative }) =>
    cumulative.length === days.length + 1 &&
    days.every((day, index) => day <= state.lastDay && (index === 0 || day >= days[index - 1]))));
  assert.equal(new ModelAPlayerHistory(state).lastDay, state.lastDay);
});

test('unverified, corrupted and truncated Android assets are rejected', async () => {
  const source = readFileSync(assetUrl);
  const manifest = JSON.parse(readFileSync(manifestUrl, 'utf8')).assets['model_a_history.bin'];
  const changed = Buffer.from(source);
  changed[20] ^= 1;
  await assert.rejects(verifyModelAHistoryAsset(changed, manifest), /ASSET_SHA256_MISMATCH/);
  await assert.rejects(verifyModelAHistoryAsset(source, { ...manifest, bytes: 3 }), /ASSET_MANIFEST_MISMATCH/);
  assert.throws(() => decodeModelAHistoryAsset(source.subarray(0, 500)), /TRUNCATED/);
  const badMagic = Buffer.from(source);
  badMagic[0] = 0;
  assert.throws(() => decodeModelAHistoryAsset(badMagic), /BAD_MAGIC/);
  const badVersion = Buffer.from(source);
  badVersion.writeInt32BE(2, 4);
  assert.throws(() => decodeModelAHistoryAsset(badVersion), /UNSUPPORTED_VERSION/);
  const extra = Buffer.concat([source, Buffer.from([0])]);
  assert.throws(() => decodeModelAHistoryAsset(extra), /TRAILING_BYTES/);
});
