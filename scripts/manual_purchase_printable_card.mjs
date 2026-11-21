// Research-only offline rendering for the second device. Does not submit a wager.
import { receiveManualPurchaseCard } from './manual_purchase_receiver_card.mjs';
const escapeHtml = value => String(value).replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
export function renderManualPurchaseHtml(transferText, receipt = null) {
  const card = receiveManualPurchaseCard(transferText, receipt);
  const rows = card.rows.map(row => `<tr><td>${escapeHtml(row.combination)}</td><td>${escapeHtml(row.amountYen.toLocaleString('ja-JP'))}円</td></tr>`).join('');
  const state = card.receiptMatched ? '本人入力の受付内容と一致（公式照合未実施）' : card.purchaseStatus === 'RECEIPT_MISMATCH' ? '受付内容が不一致・再購入せず確認' : '受信済み・購入未確認';
  return `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BOAT AI 手動購入確認</title><style>body{font:16px system-ui,sans-serif;max-width:640px;margin:24px auto;padding:0 16px;line-height:1.6}table{width:100%;border-collapse:collapse}td,th{border-bottom:1px solid #bbb;padding:10px;text-align:left}.total{font-size:1.5rem;font-weight:bold}.warning{background:#fff2cf;padding:12px;border-radius:8px}</style></head><body><h1>買い目確認（手動購入）</h1><p>${escapeHtml(card.race)}</p><p class="warning">${escapeHtml(state)}。この画面から舟券は購入されません。</p><table><thead><tr><th>3連単</th><th>金額</th></tr></thead><tbody>${rows}</tbody></table><p class="total">合計 ${escapeHtml(card.totalYen.toLocaleString('ja-JP'))}円</p><p>転送ID: <code>${escapeHtml(card.transferId)}</code></p><h2>次の操作</h2><p>公式BOAT RACEアプリを本人が開き、レース・買い目・金額を照合して手動購入してください。購入後は公式受付履歴を確認してください。受信確認は購入確認ではありません。</p><p>${escapeHtml(card.message)}</p></body></html>`;
}
