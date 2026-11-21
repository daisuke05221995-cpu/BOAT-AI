// Research-only offline export: turn a received first-phone transfer JSON into a phone-openable HTML checklist.
// Usage: node scripts/manual_purchase_export_html.mjs received-transfer.json purchase-check.html
// Never accesses official wagering sites or submits bets.
import { readFile, writeFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';
import { renderInteractiveManualPurchasePage } from './manual_purchase_interactive_page.mjs';

export async function exportManualPurchaseHtml(inputPath, outputPath) {
  if (!inputPath || !outputPath || inputPath === outputPath) throw Error('INPUT_AND_OUTPUT_REQUIRED');
  const transfer = await readFile(inputPath, 'utf8');
  const html = renderInteractiveManualPurchasePage(transfer);
  await writeFile(outputPath, html, { flag: 'wx', mode: 0o600 });
  return { outputPath, bytes: Buffer.byteLength(html), status: 'AWAITING_MANUAL_PURCHASE' };
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  exportManualPurchaseHtml(process.argv[2], process.argv[3])
    .then(x => console.log(JSON.stringify(x)))
    .catch(e => { console.error('EXPORT_FAILED:', e.message); process.exitCode = 1; });
}
