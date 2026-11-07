// Offline CLI. Workflow separately downloads one historical day from the same
// date feed already used for schedule/results; this script never fetches it.
import { readFileSync } from 'node:fs';
import { decodeModelAHistoryAsset } from '../src/model-a-history-codec.mjs';
import { compareHistoryGapForResearch } from '../src/history-gap-diagnostic.mjs';

const [date, feedPath, historyPath, mode] = process.argv.slice(2);
if (!date || !feedPath || !historyPath || !['--json', '--markdown'].includes(mode)) {
  throw new Error('Usage: node history_gap_diagnostic.mjs YYYY-MM-DD feed.json history.bin --json|--markdown');
}
const feed = JSON.parse(readFileSync(feedPath, 'utf8'));
const history = decodeModelAHistoryAsset(readFileSync(historyPath));
const report = compareHistoryGapForResearch(feed, date, history, Date.now());
if (mode === '--json') {
  process.stdout.write(`${JSON.stringify(report, null, 2)}\n`);
} else {
  process.stdout.write([
    '## Model A candidate vs published result diagnostic (research only)',
    '',
    `- JST day: ${report.date}`,
    `- Published program rows: ${report.published_program_rows} (parsed: ${report.scheduled_rows_parsed})`,
    `- Published trifecta settled: ${report.settled}`,
    `- All-six final order shape available: ${report.full_six}`,
    `- Candidate BAH1 updates: ${report.candidate_history_races}`,
    `- Settled minus candidate: **${report.settled_minus_candidate}**`,
    `- Six-finish shape minus candidate: **${report.verified_six_minus_candidate}**`,
    `- Missing six-finish reasons: ${JSON.stringify(report.full_six_unavailable)}`,
    `- Candidate player-count deficient/surplus appearances: ${report.deficient_player_appearances}/${report.surplus_player_appearances}`,
    '',
    '**Not national coverage certification or proof of specific missing race IDs.**',
    'No post-close data was added to historical Model A features; no D1 history was activated.',
    '',
  ].join('\n'));
}
