import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, readdir, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { quarantineReceipt } from './odds_receipt_ledger.mjs';
const sample = () => ({ receiptId: 'receipt_12345', raceKey: '20261109_01_01', payload: { source: 'DEVICE_CLAIM', odds: { '1-2-3': 4.5 } } });
async function withDir(fn) { const dir = await mkdtemp(join(tmpdir(), 'odds-ledger-')); try { await fn(dir); } finally { await rm(dir, { recursive: true, force: true }); } }
test('new receipt is quarantined, never BUY/SKIP', () => withDir(async d => { const r = await quarantineReceipt(d, sample()); assert.equal(r.status, 'QUARANTINED'); assert.equal(r.reason, 'NEW_RECEIPT'); }));
test('exact replay is idempotent', () => withDir(async d => { await quarantineReceipt(d, sample()); assert.equal((await quarantineReceipt(d, sample())).reason, 'DUPLICATE_RECEIPT'); }));
test('key order does not affect fingerprint', () => withDir(async d => { await quarantineReceipt(d, sample()); const x = sample(); x.payload = { odds: { '1-2-3': 4.5 }, source: 'DEVICE_CLAIM' }; assert.equal((await quarantineReceipt(d, x)).reason, 'DUPLICATE_RECEIPT'); }));
test('same id changed odds is unavailable', () => withDir(async d => { await quarantineReceipt(d, sample()); const x = sample(); x.payload.odds['1-2-3'] = 9; assert.equal((await quarantineReceipt(d, x)).reason, 'RECEIPT_ID_CONFLICT'); }));
test('same id changed race is unavailable', () => withDir(async d => { await quarantineReceipt(d, sample()); const x = sample(); x.raceKey = '20261109_01_02'; assert.equal((await quarantineReceipt(d, x)).reason, 'LEDGER_CONFLICT'); }));
test('concurrent identical writes create one record', () => withDir(async d => { const r = await Promise.all(Array.from({ length: 20 }, () => quarantineReceipt(d, sample()))); assert.equal(r.filter(x => x.reason === 'NEW_RECEIPT').length, 1); assert.equal((await readdir(d)).length, 1); }));
test('concurrent conflicting writes never both become new', () => withDir(async d => { const x = sample(); const y = sample(); y.payload.odds['1-2-3'] = 8; const r = await Promise.all([quarantineReceipt(d, x), quarantineReceipt(d, y)]); assert.equal(r.filter(z => z.reason === 'NEW_RECEIPT').length, 1); assert.ok(r.every(z => z.status !== 'BUY' && z.status !== 'SKIP')); }));
test('path traversal id rejected', () => withDir(async d => { const x = sample(); x.receiptId = '../outside'; assert.equal((await quarantineReceipt(d, x)).status, 'UNAVAILABLE'); assert.equal((await readdir(d)).length, 0); }));
test('invalid payload rejected', () => withDir(async d => { const x = sample(); x.payload = null; assert.equal((await quarantineReceipt(d, x)).reason, 'INVALID_RECEIPT'); }));
test('persisted record contains no raw odds', () => withDir(async d => { await quarantineReceipt(d, sample()); const f = (await readdir(d))[0]; const data = await readFile(join(d, f), 'utf8'); assert.equal(data.includes('4.5'), false); assert.equal(data.includes('DEVICE_CLAIM'), false); }));


test('reject credential field without creating a file', () => withDir(async d => { const x=sample(); x.payload.token='redacted'; assert.equal((await quarantineReceipt(d,x)).reason,'INVALID_RECEIPT'); assert.equal((await readdir(d)).length,0); }));
test('reject nested credentials', () => withDir(async d => { const x=sample(); x.payload.meta={authorization:'redacted'}; assert.equal((await quarantineReceipt(d,x)).status,'UNAVAILABLE'); }));
test('reject NaN and Infinity', () => withDir(async d => { for(const v of [NaN,Infinity,-Infinity]) { const x=sample(); x.payload.odds['1-2-3']=v; assert.equal((await quarantineReceipt(d,x)).reason,'INVALID_RECEIPT'); } }));
test('reject undefined and functions', () => withDir(async d => { for(const v of [undefined,()=>1,BigInt(1)]) { const x=sample(); x.payload.extra=v; assert.equal((await quarantineReceipt(d,x)).reason,'INVALID_RECEIPT'); } }));
test('reject cyclic payload', () => withDir(async d => { const x=sample(); x.payload.self=x.payload; assert.equal((await quarantineReceipt(d,x)).reason,'INVALID_RECEIPT'); }));
test('reject getter without invoking it', () => withDir(async d => { const x=sample(); let called=false; Object.defineProperty(x.payload,'unsafe',{enumerable:true,get(){called=true;throw Error('getter')}}); assert.equal((await quarantineReceipt(d,x)).reason,'INVALID_RECEIPT'); assert.equal(called,false); }));
test('reject excessive payload size', () => withDir(async d => { const x=sample(); x.payload.large='x'.repeat(70000); assert.equal((await quarantineReceipt(d,x)).reason,'INVALID_RECEIPT'); }));
test('reject exotic prototype payload', () => withDir(async d => { const x=sample(); x.payload=new Date(); assert.equal((await quarantineReceipt(d,x)).reason,'INVALID_RECEIPT'); }));
test('reject sparse array', () => withDir(async d => { const x=sample(); x.payload.extra=new Array(3); assert.equal((await quarantineReceipt(d,x)).reason,'INVALID_RECEIPT'); }));
test('valid nested JSON remains quarantined', () => withDir(async d => { const x=sample(); x.payload.meta={items:[1,true,null,'ok']}; assert.equal((await quarantineReceipt(d,x)).status,'QUARANTINED'); }));

test('preexisting torn ledger record fails closed without overwrite', () => withDir(async d => {
  const file = join(d, createHash('sha256').update(sample().receiptId).digest('hex') + '.json');
  await writeFile(file, '{');
  const r = await quarantineReceipt(d, sample());
  assert.equal(r.status, 'UNAVAILABLE'); assert.equal(r.reason, 'LEDGER_UNREADABLE');
  assert.equal(await readFile(file, 'utf8'), '{');
  assert.deepEqual(await readdir(d), [file.split('/').pop()]);
}));
test('orphaned temp file never counts as a committed receipt', () => withDir(async d => {
  await writeFile(join(d, '.orphan.tmp'), '{');
  const r = await quarantineReceipt(d, sample());
  assert.equal(r.reason, 'NEW_RECEIPT');
  assert.equal((await quarantineReceipt(d, sample())).reason, 'DUPLICATE_RECEIPT');
  assert.equal((await readdir(d)).length, 2);
}));
test('successful publish has complete JSON and cleans temporary files', () => withDir(async d => {
  await quarantineReceipt(d, sample());
  const names = await readdir(d); assert.equal(names.length, 1);
  assert.equal(names[0].endsWith('.json'), true);
  const saved = JSON.parse(await readFile(join(d, names[0]), 'utf8'));
  assert.equal(saved.status, 'QUARANTINED');
  assert.equal(saved.receiptId, sample().receiptId);
  assert.equal(typeof saved.digest, 'string');
}));
