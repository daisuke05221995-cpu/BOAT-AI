// Offline, research-only interactive manual-purchase checklist. No wagering-app automation.
// This page can be opened on a phone after receiving the existing transfer JSON.
import { receiveManualPurchaseCard } from './manual_purchase_receiver_card.mjs';
const escapeHtml = v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function renderInteractiveManualPurchasePage(transferText) {
  const card = receiveManualPurchaseCard(transferText);
  const expected = JSON.stringify({id:card.transferId,lines:card.rows.map(x=>({combination:x.combination,amountYen:x.amountYen})),totalYen:card.totalYen}).replace(/</g,'\\u003c');
  const rows = card.rows.map((row,i)=>`<tr><td>${escapeHtml(row.combination)}</td><td>${row.amountYen.toLocaleString('ja-JP')}円</td><td><input aria-label="${escapeHtml(row.combination)} 受付買い目" placeholder="例 1-2-3" inputmode="text" data-combination="${i}"><input aria-label="${escapeHtml(row.combination)} 受付金額" placeholder="円" inputmode="numeric" type="number" min="100" step="100" data-line="${i}"></td></tr>`).join('');
  return `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>BOAT AI 手動購入チェック</title><style>body{font:16px system-ui,sans-serif;max-width:650px;margin:auto;padding:16px;line-height:1.5}table{width:100%;border-collapse:collapse}td,th{padding:9px 3px;border-bottom:1px solid #bbb}input{max-width:120px;font-size:16px}button{padding:12px;margin:6px 0;font-size:16px}.notice{background:#fff1d0;padding:12px}#result{font-weight:bold}</style></head><body><h1>手動購入チェック</h1><p>${escapeHtml(card.race)}</p><p class="notice">受信済み・購入未確認。この画面では舟券を購入できません。</p><table><thead><tr><th>3連単</th><th>予定金額</th><th>受付履歴の買い目・金額（本人入力）</th></tr></thead><tbody>${rows}</tbody></table><p><strong>予定合計 ${card.totalYen.toLocaleString('ja-JP')}円</strong></p><p>転送ID: ${escapeHtml(card.transferId)}</p><button id="copy" type="button">買い目をコピー</button><p>本人が公式アプリでレース・買い目・金額を確認して購入し、公式受付履歴を開いてから下記を入力してください。購入前には照合ボタンを押さないでください。</p><label>公式受付番号（本人入力） <input id="receipt" autocomplete="off"></label><p><button id="check" type="button">受付履歴と照合</button></p><p id="result" role="status" aria-live="polite">未購入・受付未照合</p><script type="application/json" id="expected">${expected}</script><script>
const expected=JSON.parse(document.getElementById('expected').textContent);
const result=document.getElementById('result');
document.getElementById('copy').addEventListener('click',async()=>{
 const lines=expected.lines.map(x=>x.combination+' '+x.amountYen+'円');
 const text=[${JSON.stringify(card.race)},...lines,'合計 '+expected.totalYen+'円','転送ID '+expected.id,'未購入・本人による手動購入用'].join('\\n');
 try{await navigator.clipboard.writeText(text);result.textContent='買い目をコピーしました（未購入）';}
 catch{result.textContent='コピー不可。画面の買い目を確認してください（未購入）';}
});
document.getElementById('check').addEventListener('click',()=>{
 const receipt=document.getElementById('receipt').value.trim();
 const inputs=[...document.querySelectorAll('[data-line]')];
 if(!/^[A-Za-z0-9-]{4,64}$/.test(receipt)){result.textContent='受付番号を確認してください。購入済みとは判定しません。';return;}
 const amounts=inputs.map(x=>x.value.trim()===''?NaN:Number(x.value));
 const combos=[...document.querySelectorAll('[data-combination]')].map(x=>x.value.trim());
 const matched=amounts.every((v,i)=>Number.isSafeInteger(v)&&v===expected.lines[i].amountYen&&combos[i]===expected.lines[i].combination);
 const total=amounts.reduce((a,b)=>a+b,0);
 result.textContent=matched&&total===expected.totalYen
  ?'本人が転記した受付買い目・金額と一致（公式受付履歴の真正性は未検証）。受付番号 '+receipt
  :'受付内容が不一致です。再購入せず公式履歴を確認してください。';
});
</script></body></html>`;
}
