// Read-only and side-effect-free helper for offline calibration of a redacted
// official-app accessibility control map. No network, credentials or UI events.
import { readFileSync } from 'node:fs';

const only = value => value && typeof value === 'object' && !Array.isArray(value);
const selectorValid = v => only(v) && (typeof v.id === 'string' && v.id.trim() ||
  typeof v.label === 'string' && v.label.trim());
const visibleMatch = (nodes, selector, input = false) => {
  if (!Array.isArray(nodes)) return 0;
  return nodes.filter(node => only(node) && node.visible === true && node.password !== true &&
    (input ? node.editable === true : node.clickable === true) &&
    (typeof selector.id !== 'string' || !selector.id || node.resourceId === selector.id) &&
    (typeof selector.label !== 'string' || !selector.label ||
      node.text === selector.label || node.description === selector.label)).length;
};

/**
 * Validate static map uniqueness on supplied sanitized probes only.
 * Never declares a transaction ready: final amounts, live text and receipt
 * details deliberately cannot be exported through this tool.
 */
export function auditPurchaseControlMap(input) {
  const issues = [];
  if (!only(input) || !only(input.profile) || !only(input.samples) ||
      !only(input.selection)) return {
    ready_for_offline_dry_run: false, ready_for_live_submission: false,
    issues: ['MISSING_PROFILE_PROBES_OR_SELECTION'],
  };
  const { profile: p, samples: s, selection: sel } = input;
  const picks = typeof sel.combination === 'string' ? sel.combination.split('-').map(Number) : [];
  if (!Number.isInteger(sel.stadiumNumber) || sel.stadiumNumber < 1 ||
      sel.stadiumNumber > 24 || !Number.isInteger(sel.raceNumber) ||
      sel.raceNumber < 1 || sel.raceNumber > 12 ||
      picks.length !== 3 || picks.some(n => !Number.isInteger(n) || n < 1 || n > 6) ||
      new Set(picks).size !== 3)
    issues.push('INVALID_SELECTION');
  if (!only(p.finalization)) issues.push('FINAL_REVIEW_PROFILE_MISSING');
  if (!only(p.receipt)) issues.push('RECEIPT_PROFILE_MISSING');
  const controls = [
    ['venue', p.venues?.[sel.stadiumNumber], 'venue', false],
    ['race', p.races?.[sel.raceNumber], 'race', false],
    ['trifecta', p.trifecta, 'trifecta', false],
    ['lane1', p.lanes?.['1']?.[picks[0]], 'lane1', false],
    ['lane2', p.lanes?.['2']?.[picks[1]], 'lane2', false],
    ['lane3', p.lanes?.['3']?.[picks[2]], 'lane3', false],
    ['amount', p.amount, 'amount', true],
    ['add', p.add, 'add', false],
    ['review', p.review, 'review', false],
    ['nextToConfirmation', p.finalization?.next, 'review', false],
    ['confirmationTotalInput', p.finalization?.confirmAmount, 'confirmation', true],
    ['reviewTitle', p.finalization?.title, 'confirmation', false],
    ['submit', p.finalization?.submit, 'confirmation', false],
    ['receiptTitle', p.receipt?.title, 'receipt', false],
  ];
  for (const [field, selector, screen, inputField] of controls) {
    if (!selectorValid(selector)) { issues.push('UNMAPPED_' + field); continue; }
    const count = visibleMatch(s[screen], selector, inputField);
    if (count !== 1) issues.push((count === 0 ? 'MISSING_' : 'AMBIGUOUS_') + field);
  }
  // Redacted probe snapshots cannot establish transaction amounts, matched
  // ticket rows, signed receipts or provider's permission to automate.
  return {
    ready_for_offline_dry_run: issues.length === 0,
    ready_for_live_submission: false,
    evidence_classification: 'STATIC_CONTROL_MAP_ONLY',
    requires_on_device_final_amount_and_receipt_parsing: true,
    issues,
  };
}
if (process.argv[1] && import.meta.url === new URL('file://' + process.argv[1]).href) {
  const path = process.argv[2];
  if (!path) { console.error('Usage: node scripts/purchase_control_map_audit.mjs sanitized-input.json'); process.exit(2); }
  const result = auditPurchaseControlMap(JSON.parse(readFileSync(path, 'utf8')));
  // Diagnostic only. Never echo raw profile contents, account data or probe text.
  console.log(JSON.stringify(result, null, 2));
  process.exitCode = result.ready_for_offline_dry_run ? 0 : 1;
}
