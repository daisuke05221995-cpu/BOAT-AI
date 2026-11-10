import test from 'node:test';
import assert from 'node:assert/strict';
import { fingerprintPurchasePlan, inspectPurchaseReplay } from './purchase_replay_guard.mjs';
const p = () => ({ race_date: '2026-11-08', stadium_number: 1,
  race_number: 7, tickets: [
    { combination: '1-2-3', yen: 500 },
    { combination: '2-3-4', yen: 1000 },
  ] });
test('fingerprint is stable across ticket ordering', () => {
  const a = p(), b = p(); b.tickets.reverse();
  assert.equal(fingerprintPurchasePlan(a), fingerprintPurchasePlan(b));
});
test('fingerprint changes when race or stake changes', () => {
  const a = p(), b = p(); b.tickets[0].yen += 100;
  assert.notEqual(fingerprintPurchasePlan(a), fingerprintPurchasePlan(b));
  b.tickets[0].yen -= 100; b.race_number++;
  assert.notEqual(fingerprintPurchasePlan(a), fingerprintPurchasePlan(b));
});
test('no durable journal means no dry run or live submission', () => {
  const x = inspectPurchaseReplay(p());
  assert.equal(x.reason, 'DURABLE_JOURNAL_REQUIRED');
  assert.equal(x.allowed_for_live_submission, false);
});
test('new plan can only be inspected offline', () => {
  const x = inspectPurchaseReplay(p(), []);
  assert.equal(x.allowed_for_offline_dry_run, true);
  assert.equal(x.allowed_for_live_submission, false);
  assert.match(x.fingerprint, /^[a-f0-9]{64}$/);
});
for (const state of ['PREPARED', 'SUBMITTING', 'UNKNOWN', 'CONFIRMED', 'REJECTED']) {
  test('previous ' + state + ' attempt blocks automatic replay', () => {
    const x = inspectPurchaseReplay(p(), [{ fingerprint: fingerprintPurchasePlan(p()), state }]);
    assert.equal(x.reason, 'DUPLICATE_OR_UNCERTAIN_SUBMISSION');
  });
}
test('invalid journal fails closed, including malformed unrelated records', () => {
  const x = inspectPurchaseReplay(p(), [{ fingerprint: 'oops', state: 'CONFIRMED' }]);
  assert.equal(x.reason, 'INVALID_JOURNAL_ENTRY');
});
test('unrelated valid journal entry does not block offline preflight', () => {
  const other = p(); other.race_number = 8;
  const x = inspectPurchaseReplay(p(), [{ fingerprint: fingerprintPurchasePlan(other), state: 'UNKNOWN' }]);
  assert.equal(x.allowed_for_offline_dry_run, true);
  assert.equal(x.allowed_for_live_submission, false);
});
test('duplicate combinations are rejected rather than silently summed', () => {
  const x = p(); x.tickets.push({ combination: '1-2-3', yen: 100 });
  assert.equal(inspectPurchaseReplay(x, []).reason, 'INVALID_PURCHASE_PLAN');
});
test('invalid tickets and amounts fail closed', () => {
  for (const row of [
    { combination: '1-1-2', yen: 100 }, { combination: '1-2-3', yen: 0 },
    { combination: '1-2-3', yen: 150 }, { combination: '1-2-3', yen: -100 },
    { combination: '1-2-3', yen: 1_000_100 }, { combination: '1-2-3', yen: '100' },
  ]) {
    const x = p(); x.tickets = [row];
    assert.equal(inspectPurchaseReplay(x, []).reason, 'INVALID_PURCHASE_PLAN');
  }
});
test('invalid date, venue, race fail closed', () => {
  for (const change of [{race_date:'2026-02-30'}, {stadium_number:25},
    {race_number:0}, {race_date:'2026-13-01'}]) {
    assert.equal(inspectPurchaseReplay({...p(), ...change}, []).reason, 'INVALID_PURCHASE_PLAN');
  }
});
test('journal capacity fails closed', () => {
  const journal = Array.from({length:10001}, () => ({
    fingerprint:'0'.repeat(64), state:'REJECTED',
  }));
  assert.equal(inspectPurchaseReplay(p(), journal).reason, 'JOURNAL_TOO_LARGE');
});
