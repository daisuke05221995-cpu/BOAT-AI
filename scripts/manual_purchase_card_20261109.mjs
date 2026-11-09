/** Research-only manual purchase handoff card: no network, no purchase automation. */
export function makeManualPurchaseCard({race,transferId,picks}) {
  if (!race || !/^\d{4}-\d{2}-\d{2}$/.test(race.date) || !Number.isInteger(race.venue) || race.venue<1 || race.venue>24 || !Number.isInteger(race.number) || race.number<1 || race.number>12) throw Error('invalid race');
  if (!/^[A-Za-z0-9_-]{8,80}$/.test(transferId||'')) throw Error('invalid transfer ID');
  if (!Array.isArray(picks)||!picks.length||picks.length>120) throw Error('invalid picks');
  const seen=new Set();let totalYen=0;
  const rows=picks.map(({combination,yen})=>{
    if (!/^[1-6]-[1-6]-[1-6]$/.test(combination)||new Set(combination.split('-')).size!==3||seen.has(combination)||!Number.isSafeInteger(yen)||yen<100||yen%100) throw Error('invalid or duplicate stake');
    seen.add(combination);totalYen+=yen;
    if (!Number.isSafeInteger(totalYen)) throw Error('stake overflow');
    return {combination,yen};
  });
  const raceText=`${race.date} / 場コード${String(race.venue).padStart(2,'0')} / ${race.number}R`;
  const copyText=['【手動購入用・未購入】',raceText,...rows.map(r=>`${r.combination}  ${r.yen}円`),`合計 ${totalYen}円`,`転送ID ${transferId}`,'公式アプリで本人が確認して購入してください。受信＝購入完了ではありません。'].join('\n');
  const html=`<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><h1>手動購入用（未購入）</h1><p>${raceText}</p><table><tr><th>3連単</th><th>金額</th></tr>${rows.map(r=>`<tr><td>${r.combination}</td><td>${r.yen}円</td></tr>`).join('')}</table><strong>合計 ${totalYen}円</strong><p>転送ID ${transferId}</p><p>公式アプリで本人が確認して購入してください。受信＝購入完了ではありません。</p></html>`;
  return {status:'AWAITING_MANUAL_PURCHASE',race,transferId,picks:rows,totalYen,copyText,html};
}
