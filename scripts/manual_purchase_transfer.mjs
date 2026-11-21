// Offline research-only two-device transfer. Never controls a wagering application.
import { prepareManualPurchase } from './manual_purchase_handoff.mjs';
export function exportPurchaseTransfer(handoff) {
  if (!handoff || handoff.status !== 'AWAITING_MANUAL_PURCHASE') throw Error('INVALID_HANDOFF');
  const {raceDate,venueCode,raceNumber,lines,totalYen,handoffId}=handoff;
  const checked=prepareManualPurchase({raceDate,venueCode,raceNumber,picks:lines});
  if(checked.handoffId!==handoffId || checked.totalYen!==totalYen) throw Error('HANDOFF_MISMATCH');
  return JSON.stringify({kind:'BOAT_AI_MANUAL_TRANSFER',version:1,handoffId,raceDate,venueCode,raceNumber,lines,totalYen});
}
export function importPurchaseTransfer(text) {
  if(typeof text!=='string'||text.length>20000) throw Error('INVALID_TRANSFER');
  let payload;
  try {payload=JSON.parse(text)} catch {throw Error('INVALID_TRANSFER')}
  if(!payload || Array.isArray(payload)||payload.kind!=='BOAT_AI_MANUAL_TRANSFER'||payload.version!==1) throw Error('INVALID_TRANSFER');
  const allowed=['kind','version','handoffId','raceDate','venueCode','raceNumber','lines','totalYen'];
  if(Object.keys(payload).some(k=>!allowed.includes(k))) throw Error('UNEXPECTED_TRANSFER_FIELD');
  const checked=prepareManualPurchase({raceDate:payload.raceDate,venueCode:payload.venueCode,raceNumber:payload.raceNumber,picks:payload.lines});
  if(checked.handoffId!==payload.handoffId||checked.totalYen!==payload.totalYen) throw Error('TRANSFER_MISMATCH');
  return {...checked,transferStatus:'RECEIVED_UNCONFIRMED',message:'2台目で受信しました。公式アプリで本人が手動購入し、受付履歴を照合してください。'};
}
export function acknowledgePurchaseTransfer(received, handoffId) {
  if(received?.transferStatus!=='RECEIVED_UNCONFIRMED'||received.handoffId!==handoffId) throw Error('ACK_MISMATCH');
  return {handoffId,transferStatus:'RECEIVED_ACKNOWLEDGED',purchaseStatus:'NOT_CONFIRMED'};
}
