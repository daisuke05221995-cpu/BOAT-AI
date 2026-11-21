import test from 'node:test';
import assert from 'node:assert/strict';
import { parseOfficialControlMapExport, mergeOfficialControlMapExports }
  from './official_control_export_adapter.mjs';

const HEADER = 'BOAT AI 公式アプリ操作検証（認証情報・入力値なし）';
const row = (n, id, click, edit, label) =>
  `${n} id=${id} click=${click} edit=${edit} label=${label}`;
const report = (...rows) => [HEADER, `controls=${rows.length}`, ...rows].join('\n');
const basic = () => report(
  row(0, 'jp.boatrace.android.boatraceapp:id/btn_next', 'true', 'false', '次へ'),
  row(1, 'jp.boatrace.android.boatraceapp:id/amount', 'false', 'true', '-')
);
test('parses precisely the static clipboard produced by Android v0.18.31', () => {
  const result = parseOfficialControlMapExport(basic(), 'confirmation');
  assert.equal(result.accepted, true);
  assert.equal(result.stage, 'confirmation');
  assert.equal(result.count, 2);
  assert.equal(result.nodes[0].text, '次へ');
  assert.equal(result.nodes[0].clickable, true);
  assert.equal(result.nodes[1].editable, true);
  assert.equal(result.nodes[1].text, null);
  assert.equal(result.ready_for_live_submission, false);
});
test('stage map can be fed as samples to the existing offline calibration auditor', () => {
  const merged = mergeOfficialControlMapExports({ review: basic(), confirmation: basic() });
  assert.equal(merged.accepted, true);
  assert.deepEqual(merged.present_stages, ['confirmation', 'review']);
  assert.equal(merged.samples.review.length, 2);
  assert.equal(merged.ready_for_offline_dry_run, false);
});
test('never guesses the screen stage when absent', () => {
  assert.equal(parseOfficialControlMapExport(basic()).reason, 'UNKNOWN_SCREEN_STAGE');
});
test('unknown stage is rejected', () => {
  assert.equal(parseOfficialControlMapExport(basic(), 'purchase').reason, 'UNKNOWN_SCREEN_STAGE');
});
test('rejects non-Android or spoofed export headers', () => {
  assert.equal(parseOfficialControlMapExport('controls=2\n' + basic(), 'review').reason, 'EXPORT_HEADER_NOT_RECOGNIZED');
});
test('missing and excess rows rejected', () => {
  const r = basic().replace('controls=2', 'controls=3');
  assert.equal(parseOfficialControlMapExport(r, 'review').reason, 'EXPORT_COUNT_MISMATCH');
  assert.equal(parseOfficialControlMapExport(basic() + '\nextra', 'review').reason, 'EXPORT_COUNT_MISMATCH');
});
test('out of order or repeated row indices rejected', () => {
  const r = basic().replace('1 id=', '0 id=');
  assert.equal(parseOfficialControlMapExport(r, 'review').reason, 'MALFORMED_CONTROL_LINE');
});
test('rejects unbounded or non-text exports', () => {
  assert.equal(parseOfficialControlMapExport(null, 'review').reason, 'INVALID_OR_OVERSIZE_EXPORT');
  assert.equal(parseOfficialControlMapExport('x'.repeat(35_001), 'review').reason, 'INVALID_OR_OVERSIZE_EXPORT');
});
test('unsafe arbitrary label text never escapes into parsed samples', () => {
  const privateLabel = report(row(0, 'app:id/button', 'true', 'false', '暗証123456確認'));
  const result = parseOfficialControlMapExport(privateLabel, 'review');
  assert.equal(result.reason, 'UNSAFE_OR_UNEXPECTED_LABEL');
  assert.equal(JSON.stringify(result).includes('123456'), false);
});
test('rejects probable credential-related resource names', () => {
  const secret = report(row(0, 'app:id/account_password', 'false', 'true', '-'));
  assert.equal(parseOfficialControlMapExport(secret, 'review').reason, 'UNSAFE_RESOURCE_ID');
});
test('malformed booleans fail closed', () => {
  const msg = report('0 id=app:id/next click=1 edit=false label=次へ');
  assert.equal(parseOfficialControlMapExport(msg, 'review').reason, 'MALFORMED_CONTROL_LINE');
});
test('all missing static labels remain null while IDs persist', () => {
  const msg = report(row(0, 'app:id/bet', 'true', 'false', '-'));
  const x = parseOfficialControlMapExport(msg, 'add');
  assert.equal(x.accepted, true);
  assert.equal(x.nodes[0].text, null);
});
test('a zero-control WebView is parsed but never marked as ready', () => {
  const msg = report();
  const x = parseOfficialControlMapExport(msg, 'trifecta');
  assert.equal(x.accepted, true);
  assert.equal(x.count, 0);
  assert.equal(x.ready_for_offline_dry_run, false);
});
test('unknown map keys are rejected, preventing guessed screen names', () => {
  assert.equal(mergeOfficialControlMapExports({ login_values: basic() }).reason, 'INVALID_STAGE_EXPORT_MAP');
});
test('bad stage input cannot partially pass', () => {
  const x = mergeOfficialControlMapExports({ review: basic(), receipt: 'not-an-export' });
  assert.equal(x.accepted, false);
  assert.deepEqual(x.nodes, []);
  assert.equal(x.ready_for_live_submission, false);
});
test('readable Japanese static labels with 3連単 retained only as non-transaction controls', () => {
  const msg = report(row(0, 'app:id/odds', 'true', 'false', '3連単'));
  const x = parseOfficialControlMapExport(msg, 'trifecta');
  assert.equal(x.accepted, true);
  assert.equal(x.ready_for_live_submission, false);
});
