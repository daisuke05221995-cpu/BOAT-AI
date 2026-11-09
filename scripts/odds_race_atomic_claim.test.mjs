import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readdir, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { quarantineReceipt } from './odds_receipt_ledger.mjs';
import { claimQuarantinedRace } from './odds_race_atomic_claim.mjs';
const sample = id => ({ receiptId: id, raceKey: '20261109_01_01', payload: { source: 'DEVICE_CLAIM', odds: { '1-2-3': 4.5 } } });
async function withDir(fn) { const d = await mkdtemp(join(tmpdir(), 'race-claim-')); try { await fn(d); } finally { await rm(d, { recursive: true, force: true }); } }
test('one race claim remains quarantined', () => withDir(async d => {
  await quarantineReceipt(d, sample('receipt_12345'));
  assert.deepEqual(await claimQuarantinedRace(d, 'receipt_12345', '20261109_01_01'), { status: 'QUARANTINED', reason: 'RACE_CLAIMED' });
}));
test('same receipt is idempotent', () => withDir(async d => {
  await quarantineReceipt(d, sample('receipt_12345'));
  await claimQuarantinedRace(d, 'receipt_12345', '20261109_01_01');
  assert.equal((await claimQuarantinedRace(d, 'receipt_12345', '20261109_01_01')).reason, 'RACE_ALREADY_CLAIMED_BY_SAME_RECEIPT');
}));
test('different IDs cannot claim same race concurrently', () => withDir(async d => {
  await Promise.all(['receipt_12345', 'receipt_67890'].map(id => quarantineReceipt(d, sample(id))));
  const results = await Promise.all(['receipt_12345', 'receipt_67890'].map(id => claimQuarantinedRace(d, id, '20261109_01_01')));
  assert.equal(results.filter(x => x.reason === 'RACE_CLAIMED').length, 1);
  assert.equal(results.filter(x => x.reason === 'RACE_ALREADY_CLAIMED').length, 1);
  assert.equal((await readdir(join(d, '.race-index'))).length, 1);
}));
test('missing receipt cannot reserve race', () => withDir(async d => {
  assert.equal((await claimQuarantinedRace(d, 'receipt_12345', '20261109_01_01')).status, 'UNAVAILABLE');
}));
test('wrong race cannot claim receipt', () => withDir(async d => {
  await quarantineReceipt(d, sample('receipt_12345'));
  assert.equal((await claimQuarantinedRace(d, 'receipt_12345', '20261109_01_02')).reason, 'RECEIPT_INVALID');
}));
test('tampered receipt cannot claim race', () => withDir(async d => {
  await quarantineReceipt(d, sample('receipt_12345'));
  const f = (await readdir(d)).find(x => x.endsWith('.json'));
  await writeFile(join(d, f), '{"status":"BUY"}');
  assert.equal((await claimQuarantinedRace(d, 'receipt_12345', '20261109_01_01')).reason, 'RECEIPT_INVALID');
}));
test('invalid identifiers fail closed', () => withDir(async d => {
  assert.equal((await claimQuarantinedRace(d, '../bad', '20261109_01_01')).reason, 'INVALID_ID');
}));
test('index corruption never authorizes a new claim', () => withDir(async d => {
  await quarantineReceipt(d, sample('receipt_12345'));
  await claimQuarantinedRace(d, 'receipt_12345', '20261109_01_01');
  const index = join(d, '.race-index');
  await writeFile(join(index, (await readdir(index))[0]), '{}');
  assert.equal((await claimQuarantinedRace(d, 'receipt_12345', '20261109_01_01')).reason, 'INDEX_INVALID');
}));
