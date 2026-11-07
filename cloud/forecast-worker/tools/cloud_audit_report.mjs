#!/usr/bin/env node
// Convert two read-only public audit snapshots into a GitHub Actions artifact
// and human-readable summary; no writes to Cloudflare or GitHub repository.
import { readFileSync, appendFileSync } from 'node:fs';
import { buildOperationalReport, operationalMarkdown } from '../src/operational-report.mjs';
import { decodeModelAHistoryAsset } from '../src/model-a-history-codec.mjs';

const [previousFile, todayFile, candidateFile] = process.argv.slice(2);
if (!previousFile || !todayFile || !candidateFile || process.argv.length !== 5) {
  throw new Error('Usage: node tools/cloud_audit_report.mjs <yesterday-audit.json> <today-audit.json> <unverified-research-history.bin>');
}
const report = buildOperationalReport(JSON.parse(readFileSync(previousFile, 'utf8')),
  JSON.parse(readFileSync(todayFile, 'utf8')),
  decodeModelAHistoryAsset(readFileSync(candidateFile)));
if (process.env.GITHUB_STEP_SUMMARY) {
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, operationalMarkdown(report));
}
process.stdout.write(JSON.stringify(report, null, 2) + '\n');
