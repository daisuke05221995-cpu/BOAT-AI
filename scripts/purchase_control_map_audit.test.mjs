import test from 'node:test';
import assert from 'node:assert/strict';
import { auditPurchaseControlMap } from './purchase_control_map_audit.mjs';
const tag = id => ({ id });
function fixture() {
  const lanes = {};
  for (let position = 1; position <= 3; position++) {
    lanes[position] = {};
    for (let boat = 1; boat <= 6; boat++) lanes[position][boat] = tag('lane-' + position + '-' + boat);
  }
  const profile = {
    venues: { '1': tag('venue-1') }, races: { '5': tag('race-5') },
    trifecta: tag('trifecta'), lanes, amount: tag('amount'), add: tag('add'),
    review: tag('review'),
    finalization: {
      next: tag('next'), confirmAmount: tag('confirmAmount'), title: tag('reviewTitle'),
      submit: tag('submit'),
      rowId: 'row-id', totalId: 'total-id', rowPattern: 'sample-review', totalPattern: 'sample-total',
    },
    receipt: {
      title: tag('receiptTitle'), contractId: 'contract-id', rowId: 'receipt-row',
      totalId: 'receipt-total', contractPattern: 'sample-contract',
      rowPattern: 'sample-receipt', totalPattern: 'sample-total',
    },
  };
  const samples = {};
  function add(screen, id, input = false) {
    (samples[screen] ??= []).push({ resourceId: id, visible: true,
      clickable: !input, editable: input, password: false });
  }
  add('venue', 'venue-1'); add('race', 'race-5'); add('trifecta', 'trifecta');
  add('lane1', 'lane-1-1'); add('lane2', 'lane-2-2'); add('lane3', 'lane-3-3');
  add('amount', 'amount', true); add('add', 'add'); add('review', 'review');
  add('review', 'next'); add('confirmation', 'confirmAmount', true);
  add('confirmation', 'reviewTitle'); add('confirmation', 'submit'); add('receipt', 'receiptTitle');
  return { profile, samples, selection: { stadiumNumber: 1, raceNumber: 5, combination: '1-2-3' } };
}
test('complete static mapping can only authorize offline dry-run, never real purchase', () => {
  const x = auditPurchaseControlMap(fixture());
  assert.deepEqual(x.issues, []);
  assert.equal(x.ready_for_offline_dry_run, true);
  assert.equal(x.ready_for_live_submission, false);
  assert.equal(x.requires_on_device_final_amount_and_receipt_parsing, true);
});
test('missing profile never succeeds', () => {
  assert.equal(auditPurchaseControlMap(null).ready_for_offline_dry_run, false);
});
test('wrong selected race identifier is rejected', () => {
  const f = fixture(); f.selection.raceNumber = 13;
  assert.ok(auditPurchaseControlMap(f).issues.includes('INVALID_SELECTION'));
});
test('invalid combination or repeated boat is rejected', () => {
  const f = fixture(); f.selection.combination = '1-1-2';
  assert.ok(auditPurchaseControlMap(f).issues.includes('INVALID_SELECTION'));
});
test('missing selectors fail rather than guessing screen coordinates', () => {
  const f = fixture(); delete f.profile.races['5'];
  assert.ok(auditPurchaseControlMap(f).issues.includes('UNMAPPED_race'));
});
test('duplicate visible matching selectors are ambiguous', () => {
  const f = fixture(); f.samples.venue.push({ ...f.samples.venue[0] });
  assert.ok(auditPurchaseControlMap(f).issues.includes('AMBIGUOUS_venue'));
});
test('hidden controls are not actionable', () => {
  const f = fixture(); f.samples.review[0].visible = false;
  assert.ok(auditPurchaseControlMap(f).issues.includes('MISSING_review'));
});
test('password fields cannot be used for purchase amount', () => {
  const f = fixture(); f.samples.amount[0].password = true;
  assert.ok(auditPurchaseControlMap(f).issues.includes('MISSING_amount'));
});
test('non-editable amount input fails', () => {
  const f = fixture(); f.samples.amount[0].editable = false;
  assert.ok(auditPurchaseControlMap(f).issues.includes('MISSING_amount'));
});
test('not all six selector rows mapped: dry-run remains blocked', () => {
  const f = fixture(); delete f.profile.lanes['3']['6'];
  assert.ok(auditPurchaseControlMap(f).issues.includes('INCOMPLETE_LANE_SELECTOR_MAP'));
});
test('review parser mapping absent: fail closed', () => {
  const f = fixture(); f.profile.finalization.rowPattern = '';
  assert.ok(auditPurchaseControlMap(f).issues.includes('INCOMPLETE_FINAL_REVIEW_PARSER'));
});
test('receipt parser mapping absent: fail closed', () => {
  const f = fixture(); delete f.profile.receipt.contractPattern;
  assert.ok(auditPurchaseControlMap(f).issues.includes('INCOMPLETE_RECEIPT_PARSER'));
});
test('missing confirmation or receipt stage is reported', () => {
  const f = fixture(); delete f.samples.receipt;
  assert.ok(auditPurchaseControlMap(f).issues.includes('MISSING_receiptTitle'));
});
test('missing final review profile blocks readiness', () => {
  const f = fixture(); delete f.profile.finalization;
  assert.ok(auditPurchaseControlMap(f).issues.includes('FINAL_REVIEW_PROFILE_MISSING'));
});
