// Research-only end-to-end receiver view. No official app control, network or purchase submission.
import { importPurchaseTransfer, acknowledgePurchaseTransfer } from './manual_purchase_transfer.mjs';
import { buildManualPurchaseDisplay, receiptReview } from './manual_purchase_handoff.mjs';

export function receiveManualPurchaseCard(transferText, receipt = null) {
  const handoff = importPurchaseTransfer(transferText);
  const card = buildManualPurchaseDisplay(handoff);
  const ack = acknowledgePurchaseTransfer(handoff, handoff.handoffId);
  const review = receipt === null ? null : receiptReview(handoff, receipt);
  const status = review?.status ?? 'AWAITING_PERSON_PURCHASE';
  return {
    transferId: handoff.handoffId,
    acknowledgement: ack,
    race: card.header,
    rows: card.rows,
    totalYen: card.totalYen,
    copyText: [card.header, ...card.rows.map(row => row.display),
      '合計  ' + card.totalYen.toLocaleString('ja-JP') + '円',
      '転送ID ' + handoff.handoffId,
      '公式アプリで本人が手動購入してください（未購入）'].join('\n'),
    purchaseStatus: status,
    receiptMatched: status === 'MANUALLY_RECONCILED',
    message: review === null ? '受信済み・未購入。公式アプリで本人が確認して手動購入してください。'
      : status === 'MANUALLY_RECONCILED' ? '入力された受付情報が一致しました（公式履歴の真正性は未検証）。'
      : '受付内容が不一致です。公式履歴を確認し、再購入しないでください。'
  };
}
