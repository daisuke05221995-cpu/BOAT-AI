// Offline-only adapter for the exact redacted clipboard shape currently exported
// by BoatPurchaseAccessibilityService.diagnosticControlMap() in Android v0.18.31.
// No Android service, scraping, credential storage, network or purchase actions.
import { readFileSync } from 'node:fs';

const SCREEN_STAGES = new Set([
  'venue', 'race', 'trifecta', 'lane1', 'lane2', 'lane3', 'amount',
  'add', 'review', 'confirmation', 'receipt',
]);
const HEADER = 'BOAT AI 公式アプリ操作検証（認証情報・入力値なし）';
const LINE = /^(\d+) id=(\S+) click=(true|false) edit=(true|false) label=(.*)$/;
const STATIC_LABEL = /(投票|艇番|買い目|ベット|レース|金額|確認|次へ|戻る|ログイン|3連単|３連単|受付|成立|不成立|契約番号|合計)/;
const fail = reason => ({
  accepted: false, classification: 'UNAVAILABLE', reason,
  ready_for_offline_dry_run: false, ready_for_live_submission: false,
  nodes: [],
});

/**
 * Each exported view must be manually labeled by the operator with its
 * currently visible screen stage; the Android text does not contain a
 * trustworthy stage name. The source app only copies visible nodes.
 *
 * Even a completely parsed sample cannot attest to a successful UI click,
 * correct wager, official receipt or permission to automate.
 */
export function parseOfficialControlMapExport(raw, stage) {
  if (!SCREEN_STAGES.has(stage)) return fail('UNKNOWN_SCREEN_STAGE');
  if (typeof raw !== 'string' || raw.length > 35_000) return fail('INVALID_OR_OVERSIZE_EXPORT');
  const lines = raw.replace(/\r\n/g, '\n').trimEnd().split('\n');
  if (lines[0] !== HEADER || !/^controls=\d+$/.test(lines[1] ?? ''))
    return fail('EXPORT_HEADER_NOT_RECOGNIZED');
  const count = Number(lines[1].slice('controls='.length));
  if (!Number.isSafeInteger(count) || count < 0 || count > 250 ||
      lines.length !== count + 2) return fail('EXPORT_COUNT_MISMATCH');
  const nodes = [];
  for (let i = 0; i < count; i++) {
    const m = LINE.exec(lines[i + 2]);
    if (!m || Number(m[1]) !== i) return fail('MALFORMED_CONTROL_LINE');
    const id = m[2] === '-' ? null : m[2];
    if (id && (!/^[a-zA-Z0-9._:/-]{1,100}$/.test(id) ||
      /(?:password|account|secret|token|auth|credential|pin|otp)/i.test(id)))
      return fail('UNSAFE_RESOURCE_ID');
    // The Android exporter already redacts all nonstatic labels. Filter
    // again before test inputs are retained or written to JSON.
    const label = m[5] === '-' ? null : m[5];
    if (label && (label.length > 30 || !STATIC_LABEL.test(label) ||
      label.includes('@') || /\d{4,}/.test(label) ||
      /(?:password|passcode|暗証|認証番号|口座番号|生年月日)/i.test(label)))
      return fail('UNSAFE_OR_UNEXPECTED_LABEL');
    nodes.push({
      resourceId: id, text: label, description: null,
      clickable: m[3] === 'true', editable: m[4] === 'true',
      visible: true, password: false,
    });
  }
  return {
    accepted: true, classification: 'STATIC_CONTROL_PROBE_ONLY',
    stage, count: nodes.length, nodes, ready_for_offline_dry_run: false,
    ready_for_live_submission: false,
  };
}

export function mergeOfficialControlMapExports(stageAndRaw) {
  if (!stageAndRaw || typeof stageAndRaw !== 'object' ||
      Array.isArray(stageAndRaw) || Object.keys(stageAndRaw).some(s => !SCREEN_STAGES.has(s)))
    return fail('INVALID_STAGE_EXPORT_MAP');
  const samples = {};
  for (const [stage, raw] of Object.entries(stageAndRaw)) {
    const result = parseOfficialControlMapExport(raw, stage);
    if (!result.accepted) return fail(`${stage}:${result.reason}`);
    samples[stage] = result.nodes;
  }
  return {
    accepted: true, classification: 'STATIC_CONTROL_PROBES_ONLY',
    samples, present_stages: Object.keys(samples).sort(),
    ready_for_offline_dry_run: false, ready_for_live_submission: false,
  };
}

if (process.argv[1] && import.meta.url === new URL('file://' + process.argv[1]).href) {
  const path = process.argv[2];
  if (!path) {
    console.error('Usage: node scripts/official_control_export_adapter.mjs local-stage-export-map.json');
    process.exit(2);
  }
  // JSON object: {"venue":"BOAT AI ...\\ncontrols=...\\n...", ...}.
  // Do not print raw clipboard contents or unrelated device data.
  const result = mergeOfficialControlMapExports(JSON.parse(readFileSync(path, 'utf8')));
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = result.accepted ? 0 : 1;
}
