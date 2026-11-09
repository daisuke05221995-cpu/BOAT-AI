import test from 'node:test';
import assert from 'node:assert/strict';
import {prepareManualPurchase} from './manual_purchase_handoff.mjs';
import {exportPurchaseTransfer} from './manual_purchase_transfer.mjs';
import {receiveManualPurchaseCard} from './manual_purchase_receiver_card.mjs';
const handoff=prepareManualPurchase({raceDate:'2026-11-09',venueCode:'01',raceNumber:5,picks:[{combination:'1-2-3',amountYen:300},{combination:'2-1-3',amountYen:500}]});
const wire=exportPurchaseTransfer(handoff);
test('received transfer produces readable amounts, total and ACK without purchase',()=>{
 const card=receiveManualPurchaseCard(wire);
 assert.equal(card.totalYen,800);
 assert.equal(card.rows.length,2);
 assert.match(card.copyText,/1-2-3/);
 assert.match(card.copyText,/合計  800円/);
 assert.ok(card.copyText.includes('\n'));
 assert.equal(card.acknowledgement.transferStatus,'RECEIVED_ACKNOWLEDGED');
 assert.equal(card.receiptMatched,false);
 assert.equal(card.purchaseStatus,'AWAITING_PERSON_PURCHASE');
});
test('manual receipt comparison remains separate from official verification',()=>{
 const receipt={receiptNumber:'ABCD1234',confirmedLines:handoff.lines,confirmedTotalYen:800};
 const card=receiveManualPurchaseCard(wire,receipt);
 assert.equal(card.purchaseStatus,'MANUALLY_RECONCILED');
 assert.equal(card.receiptMatched,true);
 assert.match(card.message,/未検証/);
});
test('mismatched receipt never confirms purchase',()=>{
 const card=receiveManualPurchaseCard(wire,{receiptNumber:'ABCD1234',confirmedLines:handoff.lines,confirmedTotalYen:900});
 assert.equal(card.purchaseStatus,'RECEIPT_MISMATCH');
 assert.equal(card.receiptMatched,false);
});
test('tampered transfer rejected before rendering',()=>{
 const tampered=JSON.parse(wire);tampered.totalYen=900;
 assert.throws(()=>receiveManualPurchaseCard(JSON.stringify(tampered)),/MISMATCH/);
});
