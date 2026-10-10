# WORK ASSIGNMENT — 2026-10-10 — Live evidence & background reliability audit

## Boundary
Research/documentation only. Do not edit production Android files, versionCode, release workflow, or publish releases.

## Context
- Current production line is v0.18.2+.
- First private real-device evaluation found 223 fully audited BUYs out of 457 candidates.
- Frozen formal-evaluation sample target: 360 audited BUYs.
- Current app now displays remaining audited BUYs.
- Android client fix under normal chat/Codex work aims to improve background capture and audit completeness.

## Tasks
1. Review `data/REAL_LIVE_EVAL_20261010.md`, `data/v016_live_money_protocol.json`, and latest `CURRENT_STATUS.md`.
2. Define the next prospective evaluation window without reusing post-hoc gates from the inspected 2026-10-10 sample.
3. Specify what must be checked at 360 audited BUYs:
   - ROI / profit / drawdown
   - audit completeness
   - top-payout concentration sensitivity
   - point-count slices
   - first-lane vs non-first-lane
   - expected-ROI text bands
4. Keep every slice descriptive until minimum support is met.
5. Produce a handoff report under `data/` stating PASS / HOLD / REJECT criteria for the next formal review.
6. Do not commit any private BOAT-AI-backup.json.

## Completion
A research handoff that normal chat can use without reopening or retuning the already-inspected sample.
