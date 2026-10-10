# WORK ASSIGNMENT — 2026-10-11 — Versioned live-evidence reporting

## Goal
Prepare research-side tooling so the next private BOAT-AI backup can separate newly captured prediction evidence by the Android app version that created/evaluated each record.

## Context
Production Android now writes optional `sourceAppVersion` on newly evaluated PredictionRecord rows starting with the v0.18.7/v0.18.8 line.
Legacy rows have no `sourceAppVersion`.

The frozen live-money evaluator and its accounting/audit rules must NOT be changed.

## Tasks
1. Read latest main, CURRENT_STATUS.md, data/DEVELOPMENT_ROUTING.md, data/OPERATION_REVIEW_20261011.md, and the frozen v016 live-money evaluator/protocol.
2. Add a sidecar research/report helper under scripts/ or data/ that can summarize a backup by:
   - sourceAppVersion
   - legacy/unversioned rows
   - prediction count
   - live value-v1 BUY candidate count
   - fully audited BUY count
   - audit completeness
   - settled/audited stake, payout, profit, ROI
   - first and last JST race date represented
3. Keep the frozen evaluator's cohort, audit, accounting, and 360-BUY gate unchanged.
4. Do not treat missing sourceAppVersion as v0.18.8.
5. Do not infer record version from the backup envelope appVersion.
6. Add synthetic tests proving:
   - legacy rows stay in a separate unversioned bucket;
   - sourceAppVersion survives grouping;
   - totals across version buckets reconcile with the all-record total;
   - version grouping does not alter audited eligibility/accounting.
7. Do not use or commit a private user backup.
8. Do not modify app/, versionCode/versionName, release workflows, model thresholds, BUY/SKIP rules, or stakes.

## Output
Create a dated handoff under data/ with:
- new helper path
- test command/result
- exact grouping semantics
- instructions for using it on the next private BOAT-AI-backup.json

## Purpose
At the next real-device review, normal chat should be able to compare:
- legacy/unversioned evidence
- v0.18.8+ evidence
without guessing the record's source version from export time.
