# WORK ASSIGNMENT — 2026-10-11 — Operational continuity review

## Goal
Use production evidence to verify that BOAT AI now captures live predictions continuously enough for the 360-audited-BUY formal evaluation.

## Context
- Current public release before this patch: v0.18.4.
- First formal baseline: 223/360 audited BUYs; 137 remained at the 2026-10-10 review.
- A real-device screenshot on 2026-10-11 00:10 showed HTTP 404 for the daily program JSON.
- The upstream API documents 404 when a requested date has not been published yet.
- Normal chat is patching this as a WAITING state with today.json fallback and same-day bootstrap retries.

## Tasks
1. Read latest main, CURRENT_STATUS.md, data/REAL_LIVE_EVAL_20261010.md, and data/DEVELOPMENT_ROUTING.md.
2. Do not tune model thresholds from the inspected sample.
3. Define an operational-continuity checklist for the next private backup:
   - dates with any race data captured
   - dates with zero prediction records
   - live BUY candidate count
   - audited BUY count and completeness
   - audit-failure reasons
   - first/last captured race each day
   - whether any morning publication delay produced a missing full day
4. At the next backup, compare the post-patch period separately from the pre-patch period.
5. Keep the formal strategy decision frozen until the 360 audited-BUY target is reached.
6. Do not commit private BOAT-AI-backup.json.

## Output
Create a dated report under data/ with:
- continuity PASS/HOLD
- current audited BUY count / 360
- remaining audited BUY count
- missing-day table
- audit completeness
- whether production strategy evaluation is allowed yet
