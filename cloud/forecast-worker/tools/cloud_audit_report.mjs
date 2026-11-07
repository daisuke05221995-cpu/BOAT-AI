#!/usr/bin/env node
// Convert two read-only public audit snapshots into a GitHub Actions artifact
// and human-readable summary; no writes to Cloudflare or GitHub repository.
import { readFileSync, appendFileSync } from 'node:fs';
import { buildOperationalReport, operationalMarkdown } from '../src/operational-report.mjs';

const [previousFile, todayFile] = process.argv.slice(2);
if (!previousFile || !todayFile || process.argv.length !== 4) {
  throw new Error('Usage: node tools/cloud_audit_report.mjs <yesterday-audit.json> <today-audit.json>');
}
const report = buildOperationalReport(JSON.parse(readFileSync(previousFile, 'utf8')),
  JSON.parse(readFileSync(todayFile, 'utf8')));
if (process.env.GITHUB_STEP_SUMMARY) {
  appendFileSync(process.env.GITHUB_STEP_SUMMARY, operationalMarkdown(report));
}
process.stdout.write(JSON.stringify(report, null, 2) + '\n');
