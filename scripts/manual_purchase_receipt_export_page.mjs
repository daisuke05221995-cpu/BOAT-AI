// Research-only: portable receipt-review export after manual comparison. No network or betting.
import { renderInteractiveManualPurchasePage } from './manual_purchase_interactive_page.mjs';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
export function renderReceiptExportPage(transferText) {
  const base = renderInteractiveManualPurchasePage(transferText);
  const addon = `<button id="save-review" type="button" disabled>照合結果を保存（JSON）</button>
<p id="save-help">受付内容が一致した場合だけ保存できます。公式受付の真正性は未検証です。</p>
<script>
(() => {
 const button=document.getElementById('save-review');
 const check=document.getElementById('check');
 const result=document.getElementById('result');
 const expected=JSON.parse(document.getElementById('expected').textContent);
 const receipt=document.getElementById('receipt');
 const inputs=[...document.querySelectorAll('[data-line]')];
 const combos=[...document.querySelectorAll('[data-combination]')];
 let reviewed=null;
 const invalidate=()=>{reviewed=null;button.disabled=true;};
 [receipt,...inputs,...combos].forEach(el=>el.addEventListener('input',invalidate));
 check.addEventListener('click',()=>{
   invalidate();
   const number=receipt.value.trim();
   const amounts=inputs.map(el=>Number(el.value));
   const values=combos.map(el=>el.value.trim());
   const valid=/^[A-Za-z0-9-]{4,64}$/.test(number)
     &&inputs.every(el=>el.value.trim()!=='')
     &&amounts.every((v,i)=>Number.isSafeInteger(v)&&v===expected.lines[i].amountYen)
     &&values.every((v,i)=>v===expected.lines[i].combination)
     &&amounts.reduce((a,b)=>a+b,0)===expected.totalYen;
   if(!valid)return;
   reviewed={schema:'BOAT_AI_MANUAL_RECEIPT_REVIEW',version:1,handoffId:expected.id,
     receiptNumber:number,confirmedLines:expected.lines,totalYen:expected.totalYen,
     status:'MANUALLY_RECONCILED_UNVERIFIED',reviewedAt:new Date().toISOString(),
     note:'User-transcribed values only; not proof of official acceptance'};
   button.disabled=false;
 });
 button.addEventListener('click',()=>{
   if(!reviewed)return;
   const blob=new Blob([JSON.stringify(reviewed,null,2)+'\\n'],{type:'application/json'});
   const url=URL.createObjectURL(blob);
   const a=document.createElement('a');a.href=url;a.download='boat-ai-manual-review-'+expected.id+'.json';
   document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
   result.textContent='本人入力の照合記録を保存しました（公式受付の真正性は未検証）';
 });
})();
</script>`;
  if (!base.includes('</body>')) throw Error('HTML_BODY_MISSING');
  return base.replace('</body>',addon+'</body>');
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href && process.argv.includes('--self-test')) {
 const { prepareManualPurchase } = await import('./manual_purchase_handoff.mjs');
 const { exportPurchaseTransfer } = await import('./manual_purchase_transfer.mjs');
 const handoff=prepareManualPurchase({raceDate:'2026-11-09',venueCode:'01',raceNumber:1,picks:[{combination:'1-2-3',amountYen:200}]});
 const html=renderReceiptExportPage(exportPurchaseTransfer(handoff));
 assert.match(html,/save-review/);assert.match(html,/MANUALLY_RECONCILED_UNVERIFIED/);
 assert.match(html,/1-2-3/);assert.match(html,/200円/);
 assert.match(html,/button.disabled=true/);assert.match(html,/URL.revokeObjectURL/);
 console.log('5 receipt export smoke assertions passed');
}
