import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { auditRaceLedger } from './odds_ledger_race_audit.mjs';
const sha = s => createHash('sha256').update(s).digest('hex');
async function withDir(fn) { const d=await mkdtemp(join(tmpdir(),'race-audit-')); try { await fn(d); } finally { await rm(d,{recursive:true,force:true}); } }
async function put(d,id,race='20261109_01_01',fingerprint=sha('odds')) { await writeFile(join(d,sha(id)+'.json'),JSON.stringify({receiptId:id,raceKey:race,digest:fingerprint,status:'QUARANTINED'})); }
test('empty ledger stays quarantined and never becomes BUY/SKIP',()=>withDir(async d=>{assert.deepEqual(await auditRaceLedger(d),{status:'QUARANTINED',reason:'AUDIT_ONLY',receiptCount:0,raceCount:0});}));
test('single valid receipt remains audit only',()=>withDir(async d=>{await put(d,'receipt_111');assert.equal((await auditRaceLedger(d)).reason,'AUDIT_ONLY');}));
test('two distinct races are accepted for audit',()=>withDir(async d=>{await put(d,'receipt_111');await put(d,'receipt_222','20261109_01_02');assert.equal((await auditRaceLedger(d)).raceCount,2);}));
test('different receipt IDs for one race are conflict even with equal odds hash',()=>withDir(async d=>{await put(d,'receipt_111');await put(d,'receipt_222');assert.equal((await auditRaceLedger(d)).reason,'RACE_RECEIPT_CONFLICT');}));
test('different odds hashes for one race are conflict',()=>withDir(async d=>{await put(d,'receipt_111');await put(d,'receipt_222','20261109_01_01',sha('different'));assert.equal((await auditRaceLedger(d)).status,'UNAVAILABLE');}));
test('tampered file name is rejected',()=>withDir(async d=>{await put(d,'receipt_111');await writeFile(join(d,sha('wrong')+'.json'),JSON.stringify({receiptId:'receipt_222',raceKey:'20261109_01_02',digest:sha('x'),status:'QUARANTINED'}));assert.equal((await auditRaceLedger(d)).reason,'LEDGER_RECORD_INVALID');}));
test('torn JSON is unavailable',()=>withDir(async d=>{await writeFile(join(d,sha('receipt_111')+'.json'),'{');assert.equal((await auditRaceLedger(d)).reason,'LEDGER_RECORD_UNREADABLE');}));
test('orphan temp file is ignored',()=>withDir(async d=>{await writeFile(join(d,'.orphan.tmp'),'{');assert.equal((await auditRaceLedger(d)).receiptCount,0);}));
test('extra persisted fields fail closed',()=>withDir(async d=>{await writeFile(join(d,sha('receipt_111')+'.json'),JSON.stringify({receiptId:'receipt_111',raceKey:'20261109_01_01',digest:sha('x'),status:'QUARANTINED',token:'not-stored'}));assert.equal((await auditRaceLedger(d)).reason,'LEDGER_RECORD_INVALID');}));
test('missing directory is unavailable, not SKIP',async()=>{assert.equal((await auditRaceLedger(join(tmpdir(),'missing-ledger-'+Date.now()))).status,'UNAVAILABLE');});
