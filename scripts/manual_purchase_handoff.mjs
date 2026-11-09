// Research-only handoff contract: no official app control or network calls.
import { createHash } from 'node:crypto';
const pad = n => String(n).padStart(2, '0');
export function prepareManualPurchase({ raceDate, venueCode, raceNumber, picks }) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(raceDate) || !Number.isFinite(Date.parse(raceDate+'T00:00:00Z'))) throw Error('INVALID_DATE');
  if (!/^\d{2}$/.test(venueCode) || !Number.isInteger(raceNumber) || raceNumber < 1 || raceNumber > 12) throw Error('INVALID_RACE');
  if (!Array.isArray(picks) || picks.length < 1 || picks.length > 120) throw Error('INVALID_PICKS');
  const seen = new Set(); let totalYen = 0;
  const lines = picks.map(({ combination, amountYen }) => {
    if (typeof combination !== 'string' || !/^[1-6]-[1-6]-[1-6]$/.test(combination) || new Set(combination.split('-')).size !== 3 || seen.has(combination)) throw Error('INVALID_COMBINATION');
    if (!Number.isSafeInteger(amountYen) || amountYen < 100 || amountYen % 100) throw Error('INVALID_AMOUNT');
    seen.add(combination); totalYen += amountYen;
    if (!Number.isSafeInteger(totalYen)) throw Error('INVALID_TOTAL');
    return { combination, amountYen };
  });
  lines.sort((a,b)=>a.combination.localeCompare(b.combination));
  const canonical = JSON.stringify({ version: 1, raceDate, venueCode, raceNumber, lines });
  const handoffId = createHash('sha256').update(canonical).digest('hex').slice(0,24);
  return Object.freeze({ version: 1, handoffId, raceDate, venueCode, raceNumber, lines, totalYen, status: 'AWAITING_MANUAL_PURCHASE', instructions: '公式アプリで本人が買い目・金額を確認して手動購入してください。これは購入完了通知ではありません。' });
}
export function receiptReview(handoff, { receiptNumber, confirmedLines, confirmedTotalYen }) {
  if (!handoff || handoff.status !== 'AWAITING_MANUAL_PURCHASE') throw Error('INVALID_HANDOFF');
  if (typeof receiptNumber !== 'string' || !/^[A-Za-z0-9-]{4,64}$/.test(receiptNumber)) throw Error('INVALID_RECEIPT');
  if (!Array.isArray(confirmedLines)) throw Error('INVALID_RECEIPT_LINES');
  const expected = handoff.lines.map(x=>x.combination+':'+x.amountYen).sort();
  const actual = confirmedLines.map(x=>x.combination+':'+x.amountYen).sort();
  if (JSON.stringify(expected)!==JSON.stringify(actual) || confirmedTotalYen !== handoff.totalYen) return { status: 'RECEIPT_MISMATCH', handoffId: handoff.handoffId };
  return { status: 'MANUALLY_RECONCILED', handoffId: handoff.handoffId, receiptNumber, totalYen: handoff.totalYen };
}

// Read-only presentation model for the second device. Never implies a placed bet.
export function buildManualPurchaseDisplay(handoff) {
  if (!handoff || handoff.status !== 'AWAITING_MANUAL_PURCHASE') throw Error('INVALID_HANDOFF');
  const verified = prepareManualPurchase({raceDate:handoff.raceDate,venueCode:handoff.venueCode,raceNumber:handoff.raceNumber,picks:handoff.lines});
  if (verified.handoffId !== handoff.handoffId || verified.totalYen !== handoff.totalYen) throw Error('HANDOFF_MISMATCH');
  const rows = verified.lines.map(({combination,amountYen}) => ({combination,amountYen,display:combination+'  '+amountYen.toLocaleString('ja-JP')+'円'}));
  const header = verified.raceDate+'  場コード'+verified.venueCode+'  '+verified.raceNumber+'R';
  return {handoffId:verified.handoffId,header,rows,totalYen:verified.totalYen,
    copyText:[header,...rows.map(r=>r.display),'合計  '+verified.totalYen.toLocaleString('ja-JP')+'円'].join('\\n'),
    purchaseStatus:'NOT_PURCHASED',actionLabel:'公式アプリで本人が手動購入',receiptReviewLabel:'購入後に受付内容を照合'};
}
