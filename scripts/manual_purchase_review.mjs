// Research-only presentation model. No network calls or wagering app automation.
import {prepareManualPurchase, receiptReview} from './manual_purchase_handoff.mjs';
import {importPurchaseTransfer} from './manual_purchase_transfer.mjs';
export function buildManualPurchaseReview(transferText, receipt=null) {
  const received=importPurchaseTransfer(transferText);
  const expected=prepareManualPurchase({raceDate:received.raceDate,venueCode:received.venueCode,raceNumber:received.raceNumber,picks:received.lines});
  const review=receipt===null?null:receiptReview(expected,receipt);
  const status=review===null?'AWAITING_PERSON_PURCHASE':review.status;
  return {handoffId:expected.handoffId,raceLabel:`${expected.raceDate} 場コード${expected.venueCode} ${expected.raceNumber}R`,
    rows:expected.lines.map((line,i)=>({index:i+1,combination:line.combination,amountYen:line.amountYen,display:`${line.combination}　${line.amountYen.toLocaleString('ja-JP')}円`})),
    count:expected.lines.length,totalYen:expected.totalYen,status,receiptMatched:status==='MANUALLY_RECONCILED',
    purchaseConfirmed:status==='MANUALLY_RECONCILED',
    instructions:status==='AWAITING_PERSON_PURCHASE'?'公式アプリで本人が買い目と金額を照合し、手動購入後に受付内容を入力してください。受信だけでは購入済みになりません。':status==='RECEIPT_MISMATCH'?'受付内容と予定買い目・金額が一致しません。公式受付履歴を本人が再確認してください。':'入力された受付内容は一致しました。公式受付履歴の真正性は自動検証していません。'};
}