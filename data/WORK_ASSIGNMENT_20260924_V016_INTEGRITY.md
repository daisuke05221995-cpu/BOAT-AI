# BOAT AI v0.16 Work Assignment — Data Integrity / Forecast Promotion Readiness

Date: 2026-09-24
Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`

## Purpose

The previous OOF market-difference study is complete and REJECTED for purchase promotion. Do not rescue its thresholds.

The next task is NOT another purchase-policy search. First establish whether the historical odds/accounting used by v0.16 are suitable for a realizable pre-race ROI study, and separately package the market-free Model A as a forecast-only candidate pending an independent holdout.

## Mandatory first reads

Read these before doing anything:

- `WORK_HANDOFF.md`
- `PROJECT_STATUS.md`
- `NEXT_WEEK_HANDOFF.md`
- `data/v016_r4_report.md`
- `data/v016_oof_protocol.json`
- `data/v016_oof_report.md`
- `data/v016_oof_result.json`
- `data/v016_oof_frozen_candidate.json`
- latest `main`
- latest/in-progress v016 Actions runs

## Hard boundaries

1. DO NOT open, fetch, evaluate, or infer results for 2025-09-01 onward.
2. 2025-10-01..2025-12-31 Q4 final holdout remains sealed.
3. Do not retune r1-r4 thresholds.
4. Do not retune the OOF candidates `raw_ratio`, `log_residual_half`, or `logistic_residual`.
5. Do not create a new purchase selector in this assignment.
6. Do not modify `app/**`, Android production logic, versionCode/versionName, Release workflow, or release assets.
7. Do not promote anything to production.
8. Use only already-opened periods and pinned/reproducible sources. Heavy processing goes to GitHub Actions.

## Track A — Historical odds integrity audit

Audit the exact odds source used by r4/OOF.

### A1. Provenance / timestamp semantics

Trace the source repository, docs, scraper/workflow/code, commits and file-generation process for the historical trifecta odds used in the cache.

Determine with evidence, not assumption:

- whether each race has one odds snapshot or multiple snapshots;
- whether the stored odds are final odds, latest available odds, a scheduled pre-close snapshot, or an unknown-time snapshot;
- whether data can have been collected after betting close or after race start;
- whether a timestamp is persisted per snapshot/race;
- whether the archive can prove a fixed pre-close horizon such as T-5 minutes.

Save exact source commits/paths and evidence excerpts/metadata in the audit output.

### A2. Payout consistency test using ALREADY OPENED July-August 2025 only

On the existing 2025-07-01..2025-08-31 population, compare the archived odds for the actual winning trifecta against official payout per 100 yen.

Compute at minimum:

- eligible races;
- exact matches after the archive's odds rounding convention;
- within 0.1 odds point;
- within 0.5 odds point;
- within 1%, 3%, 5% relative difference;
- distribution of signed and absolute difference;
- per-month and per-venue summaries;
- examples of largest mismatches with race key only (no new source access beyond permitted period).

Interpretation must be cautious: close agreement can indicate near-final odds but does not by itself prove collection before close.

### A3. Population / settlement audit

Quantify what the current backtests exclude or simplify:

- cancelled/aborted/non-six-boat races;
- missing odds races;
- refund/return cases if represented by the sources;
- dead heat or multiple trifecta payout cases if present;
- races excluded by requiring all 120 odds positive and finite;
- difference between source race population, settled population, pre-race-feature-usable population, odds-usable population and joint population.

State whether current ROI accounting could be biased by these exclusions, and in what direction if it can be established. Do not guess direction where evidence is insufficient.

### A4. Decision for purchase research

Use one of these explicit outcomes:

- `ODDS_PRE_CLOSE_VERIFIED`
- `ODDS_PRE_CLOSE_NOT_VERIFIED`
- `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`

Do not classify as verified without direct timestamp/process evidence.

If not verified/suitable, recommend suspending ROI-based purchase-model promotion on this historical odds archive until a verifiably pre-close odds source is available. Do NOT try to compensate by changing EV thresholds.

## Track B — Forecast-only Model A promotion readiness

This track must NOT use odds as model inputs and must NOT open September/Q4.

Freeze the existing market-free OOF/r4 Model A as a forecast candidate only. It is not a purchase candidate.

Reference metrics already produced on the fixed July-August development population:

- Model A: logloss ~3.79622, Brier ~0.96019, first-place Top1 ~56.09%, first-place Top2 ~75.81%, trifecta Top1 ~9.72%, Top4 ~29.34%, Top8 ~45.42%.
- Current Android v0.15.16 pure AI audit on the same development window: first-place Top1 45.33%, Top2 66.94%, trifecta Top1 5.61%, Top4 19.20%, Top8 32.95%.

Verify these from repository artifacts rather than trusting this assignment text.

### B1. Freeze manifest

Create a forecast-only candidate manifest containing at minimum:

- exact model artifact/run ID and SHA256;
- protocol SHA and feature-schema SHA;
- model architecture/hyperparameters/temperature;
- explicit `marketInputs=false`;
- training/validation date maxima;
- history seed source;
- status `PENDING_INDEPENDENT_HOLDOUT`;
- `productionPromotion=false`.

Do not call this release-qualified.

### B2. Android deployability audit WITHOUT editing Android

Determine what would be required to run Model A for live Android predictions:

- exact required pre-race fields;
- player/course history state required at inference time;
- how history must be updated without same-day leakage;
- model asset files and approximate sizes;
- whether LightGBM must be reimplemented, exported, converted, or run via a compatible inference format;
- expected number of conditional model evaluations per race;
- missing-data handling;
- fallback behavior if player history is insufficient;
- reproducibility/hash checks needed on-device or during build.

If practical, create export/manifest artifacts under research paths only. Do not touch `app/**`.

### B3. Forecast promotion readiness decision

Allowed outcomes:

- `FORECAST_READY_FOR_INTEGRATION_DESIGN_PENDING_HOLDOUT`
- `FORECAST_NOT_DEPLOYABLE_YET`
- `FORECAST_REJECTED_ON_EXISTING_EVIDENCE`

This is NOT permission to open September or Q4 and NOT permission to integrate into Android.

## Required files

Use new dedicated names, preferably:

- `scripts/v016_integrity_audit.py`
- `scripts/v016_integrity_test.py`
- `.github/workflows/v016-integrity-audit.yml`
- `data/v016_integrity_protocol.json` (preregister before analysis)
- `data/v016_integrity_result.json`
- `data/v016_integrity_report.md`
- `data/v016_forecast_candidate.json`
- `data/v016_forecast_deployability.md`

Do not overwrite r4/OOF result files.

## Tests / guards

Add guards proving:

- no date >= 2025-09-01 is read or requested;
- Q4 cannot be opened by a CLI option;
- app/ and release files are untouched by the workflow;
- result race keys are unique;
- payout/odds comparison uses only existing permitted source/cache data;
- forecast candidate has `marketInputs=false` and `productionPromotion=false`;
- candidate artifact/model hashes match the referenced r4/OOF artifact.

## End-of-task handoff

Update `WORK_HANDOFF.md` with:

- current main commit;
- Actions Run ID(s);
- artifact IDs;
- Track A odds decision;
- Track B forecast decision;
- exact metrics/evidence;
- confirmation that September/Q4 remained unopened;
- confirmation that Android/app/Release were untouched;
- next concrete action for normal chat.

If Work limits/timeouts are near, save current commit, Run ID and next action to GitHub before returning control to normal chat.
