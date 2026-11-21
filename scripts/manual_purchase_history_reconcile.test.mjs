import test from 'node:test';
import assert from 'node:assert/strict';
import { fingerprintPurchasePlan } from './purchase_replay_guard.mjs';
import { reconcileManualPurchaseEvidence as reconcile } from './manual_purchase_history_reconcile.mjs';
const plan = () => ({race_date:'2026-11-08',stadium_number:1,race_number:7,
  tickets:[{combination:'1-2-3',yen:500},{combination:'2-3-4',yen:1000}]});
const evidence = () => ({date:'2026-11-08',officialHistoryChecked:true,
  officialHistoryStatus:'ACCEPTED',totalYen:1500,
  lines:[{stadiumNumber:1,raceNumber:7,combination:'1-2-3',amount:500},
    {stadiumNumber:1,raceNumber:7,combination:'2-3-4',amount:1000}]});
const check = (e=evidence(), j=[]) => reconcile(plan(),e,j);
test('matching transcribed official history still cannot confirm purchase',()=>{
  const x=check(); assert.equal(x.classification,'MANUAL_HISTORY_MATCH_REQUIRES_OPERATOR_CONFIRMATION');
  assert.equal(x.matched_lines,2);assert.equal(x.purchase_confirmed,false);
  assert.equal(x.ready_for_live_submission,false);assert.equal(x.retry_allowed,false);
});
test('missing journal fails closed',()=>assert.equal(check(evidence(),null).reason,'DURABLE_JOURNAL_UNVERIFIED'));
test('prior UNKNOWN journal blocks all automatic retry',()=>{
  const x=check(evidence(),[{fingerprint:fingerprintPurchasePlan(plan()),state:'UNKNOWN',sequence:1}]);
  assert.equal(x.reason,'EXISTING_ATTEMPT_REQUIRES_OFFICIAL_HISTORY_CHECK');
  assert.equal(x.retry_allowed,false);
});
test('unrelated journal does not falsely mark confirmed',()=>{
  const x=check(evidence(),[{fingerprint:'a'.repeat(64),state:'UNKNOWN',sequence:1}]);
  assert.equal(x.purchase_confirmed,false);assert.equal(x.matched_lines,2);
});
test('unverified history rejected',()=>{const e=evidence();e.officialHistoryChecked=false;
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_NOT_VERIFIED')});
for(const status of ['UNKNOWN','NOT_FOUND']) test(status+' cannot authorize replay',()=>{
  const e=evidence();e.officialHistoryStatus=status;
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_NOT_ACCEPTED');
});
test('extra private field fails closed',()=>{const e=evidence();e.account='secret';
  const x=check(e);assert.equal(x.reason,'INVALID_EVIDENCE_SCHEMA');
  assert.equal(JSON.stringify(x).includes('secret'),false);
});
test('wrong race date rejected',()=>{const e=evidence();e.date='2026-11-07';
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_PLAN_MISMATCH')});
test('missing ticket rejected',()=>{const e=evidence();e.lines.pop();
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_PLAN_MISMATCH')});
test('extra ticket rejected',()=>{const e=evidence();e.lines.push({...e.lines[0],combination:'3-4-5'});
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_PLAN_MISMATCH')});
test('duplicate ticket rejected',()=>{const e=evidence();e.lines[1]={...e.lines[0]};
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_PLAN_MISMATCH')});
test('incorrect stake rejected',()=>{const e=evidence();e.lines[0].amount=600;
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_PLAN_MISMATCH')});
test('incorrect total rejected',()=>{const e=evidence();e.totalYen=1600;
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_PLAN_MISMATCH')});
test('wrong venue rejected',()=>{const e=evidence();e.lines[0].stadiumNumber=2;
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_PLAN_MISMATCH')});
test('wrong race number rejected',()=>{const e=evidence();e.lines[0].raceNumber=8;
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_PLAN_MISMATCH')});
test('invalid combination rejected',()=>{const e=evidence();e.lines[0].combination='1-1-2';
  assert.equal(check(e).reason,'INVALID_HISTORY_LINES')});
test('invalid non-100-yen stake rejected',()=>{const e=evidence();e.lines[0].amount=550;
  assert.equal(check(e).reason,'INVALID_HISTORY_LINES')});
test('unrecognized status rejected',()=>{const e=evidence();e.officialHistoryStatus='SUCCESS';
  assert.equal(check(e).reason,'OFFICIAL_HISTORY_NOT_VERIFIED')});
test('invalid journal state rejected',()=>{const x=check(evidence(),[{fingerprint:'a'.repeat(64),state:'READY',sequence:1}]);
  assert.equal(x.reason,'DURABLE_JOURNAL_UNVERIFIED')});
test('invalid plan rejected',()=>{const x=reconcile({...plan(),race_number:20},evidence(),[]);
  assert.equal(x.reason,'INVALID_PLAN')});
test('ticket ordering does not affect offline comparison',()=>{const e=evidence();e.lines.reverse();
  assert.equal(check(e).matched_lines,2)});
test('untrusted receipt does not echo sensitive data',()=>{const e=evidence();e.lines[0].combination='my-password';
  assert.equal(JSON.stringify(check(e)).includes('my-password'),false)});
