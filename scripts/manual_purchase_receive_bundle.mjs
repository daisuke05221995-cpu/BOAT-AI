// Research-only receiver bridge: one command converts first-device transfer to a phone-readable
// checklist AND an acknowledgement for the sender. No networking, official-app automation or bets.
// node scripts/manual_purchase_receive_bundle.mjs transfer.json output-directory
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';
import { receiveManualPurchaseCard } from './manual_purchase_receiver_card.mjs';
import { renderReceiptExportPage } from './manual_purchase_receipt_export_page.mjs';

export function buildReceiverBundle(transferText) {
  const card = receiveManualPurchaseCard(transferText);
  return {
    html: renderReceiptExportPage(transferText),
    acknowledgement: card.acknowledgement,
    summary: {
      transferId: card.transferId,
      race: card.race,
      lines: card.rows.map(({ combination, amountYen }) => ({ combination, amountYen })),
      totalYen: card.totalYen,
      purchaseStatus: 'NOT_CONFIRMED',
      notice: '受信確認は購入確認ではありません。本人が公式アプリで手動購入してください。'
    }
  };
}
export async function receiveBundle(inputPath, outputDirectory) {
  if (!inputPath || !outputDirectory) throw Error('INPUT_AND_OUTPUT_REQUIRED');
  const text = await readFile(inputPath, 'utf8');
  const bundle = buildReceiverBundle(text); // Validate before writing anything.
  await mkdir(outputDirectory, { recursive: true });
  // Stable filenames allow the sender to locate ACK without confusing it with a receipt.
  // Exclusive writes prevent silently replacing a previously received order.
  await writeFile(join(outputDirectory, 'manual-purchase.html'), bundle.html, { flag: 'wx', mode: 0o600 });
  await writeFile(join(outputDirectory, 'received-ack.json'), JSON.stringify(bundle.acknowledgement, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  await writeFile(join(outputDirectory, 'purchase-summary.json'), JSON.stringify(bundle.summary, null, 2) + '\n', { flag: 'wx', mode: 0o600 });
  return { outputDirectory, transferId: bundle.summary.transferId, purchaseStatus: 'NOT_CONFIRMED' };
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  receiveBundle(process.argv[2], process.argv[3])
    .then(x => console.log(JSON.stringify(x)))
    .catch(e => { console.error('RECEIVE_BUNDLE_FAILED:', e.message); process.exitCode = 1; });
}
