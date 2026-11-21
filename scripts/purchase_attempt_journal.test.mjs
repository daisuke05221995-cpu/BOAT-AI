import test from 'node:test';
import assert from 'node:assert/strict';
import { preparePurchaseAttempt, transitionPurchaseAttempt } from './purchase_attempt_journal.mjs';
const plan = () => ({ race_date:'2026-11-08', stadium_number:1, race_number:5,
  tickets:[{combination:'1-2-3',yen:500},{combination:'1-3-2',yen:200}] });
const prepared = () => preparePurchaseAttempt(plan(), []);
test('preparation requires durable journal', () => {
  assert.equal(preparePurchaseAttempt(plan(), undefined).reason,'DURABLE_JOURNAL_REQUIRED');
});
test('valid preparation never authorizes submission', () => {
  const x=prepared();
  assert.equal(x.accepted,true);
  assert.equal(x.ready_for_live_submission,false);
  assert.equal(x.journal[0].state,'PREPARED');
});
test('journal preparation does not mutate input', () => {
  const rows=[]; preparePurchaseAttempt(plan(),rows);
  assert.deepEqual(rows,[]);
});
test('same plan cannot be prepared twice', () => {
  const x=prepared();
  assert.equal(preparePurchaseAttempt(plan(),x.journal).reason,'PLAN_ALREADY_PREPARED_OR_ATTEMPTED');
});
test('corrupted journal is rejected', () => {
  assert.equal(preparePurchaseAttempt(plan(),[{fingerprint:'oops',state:'PREPARED',sequence:1}]).reason,'INVALID_DURABLE_JOURNAL');
});
test('duplicate fingerprint journal is rejected', () => {
  const x=prepared(); assert.equal(preparePurchaseAttempt({...plan(),race_number:6},[...x.journal,...x.journal]).reason,'DUPLICATE_JOURNAL_FINGERPRINT');
});
test('offline PREPARED -> SUBMITTING transition is allowed but never submits', () => {
  const x=prepared();
  const y=transitionPurchaseAttempt(x.journal,x.fingerprint,1,'SUBMITTING');
  assert.equal(y.accepted,true);
  assert.equal(y.ready_for_live_submission,false);
  assert.equal(y.journal[0].sequence,2);
  assert.equal(x.journal[0].state,'PREPARED');
});
test('cannot skip PREPARED directly to CONFIRMED', () => {
  const x=prepared();
  assert.equal(transitionPurchaseAttempt(x.journal,x.fingerprint,1,'CONFIRMED').reason,'ILLEGAL_OR_TERMINAL_TRANSITION');
});
test('UNKNOWN cannot be retried or reset even if clock advances', () => {
  const x=prepared(), y=transitionPurchaseAttempt(x.journal,x.fingerprint,1,'SUBMITTING');
  const z=transitionPurchaseAttempt(y.journal,x.fingerprint,2,'UNKNOWN');
  assert.equal(z.accepted,true);
  for(const state of ['PREPARED','SUBMITTING','CONFIRMED','REJECTED','UNKNOWN'])
    assert.equal(transitionPurchaseAttempt(z.journal,x.fingerprint,3,state).reason,'ILLEGAL_OR_TERMINAL_TRANSITION');
});
test('CONFIRMED and REJECTED are terminal', () => {
  for(const state of ['CONFIRMED','REJECTED']) {
    const x=prepared(),y=transitionPurchaseAttempt(x.journal,x.fingerprint,1,'SUBMITTING');
    const z=transitionPurchaseAttempt(y.journal,x.fingerprint,2,state);
    assert.equal(z.accepted,true);
    assert.equal(transitionPurchaseAttempt(z.journal,x.fingerprint,3,'SUBMITTING').reason,'ILLEGAL_OR_TERMINAL_TRANSITION');
  }
});
test('stale compare-and-swap sequence is rejected', () => {
  const x=prepared(),y=transitionPurchaseAttempt(x.journal,x.fingerprint,1,'SUBMITTING');
  assert.equal(transitionPurchaseAttempt(y.journal,x.fingerprint,1,'UNKNOWN').reason,'STALE_JOURNAL_SEQUENCE');
});
test('unknown fingerprint is rejected', () => {
  const x=prepared();
  assert.equal(transitionPurchaseAttempt(x.journal,'f'.repeat(64),1,'SUBMITTING').reason,'UNKNOWN_PLAN');
});
test('bad transition inputs fail closed', () => {
  const x=prepared();
  assert.equal(transitionPurchaseAttempt(x.journal,x.fingerprint,1,'SUBMIT').reason,'ILLEGAL_OR_TERMINAL_TRANSITION');
  assert.equal(transitionPurchaseAttempt(x.journal,'bad',1,'SUBMITTING').reason,'INVALID_TRANSITION_REQUEST');
});
test('invalid plans cannot be prepared', () => {
  assert.equal(preparePurchaseAttempt({...plan(),tickets:[{combination:'1-1-3',yen:500}]},[]).reason,'INVALID_PURCHASE_PLAN');
});
test('valid distinct plans retain monotonic sequences', () => {
  const x=prepared(),y=preparePurchaseAttempt({...plan(),race_number:6},x.journal);
  assert.equal(y.accepted,true);
  assert.deepEqual(y.journal.map(z=>z.sequence),[1,2]);
});
