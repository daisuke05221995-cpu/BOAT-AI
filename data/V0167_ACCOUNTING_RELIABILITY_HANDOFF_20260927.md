# BOAT AI v0.16.7 Accounting Reliability Handoff

Date: 2026-09-27
Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`
Public release: `v0.16.7` (versionCode 42)

## Product priority

The primary user need remains money-first:

1. actual confirmed purchases: cumulative stake / payout / profit / ROI
2. audited live AI BUY: cumulative performance kept separate from retrospective/backtest numbers
3. accounting must recover automatically after background settlement, process lifecycle changes, or malformed local ledger payloads

Detailed model explanation is secondary.

## Implemented on main after v0.16.6

### 1. Refresh cumulative accounting on app resume / accounting tab entry

Commit: `01477e14def5928e55ee5b8f160f93cbaea279ba`
Validation Run: `36289522137` — SUCCESS

Changes:
- `BoatViewModel.syncStoredAccounting()` reloads durable actual-purchase records, prediction history, pending purchase, and recalculates the performance profile.
- entering Purchase / Results / Profit refreshes durable accounting rather than relying on ViewModel creation-time state.
- `MainActivity.onResume()` also refreshes accounting and schedules a near-term prediction tracking bootstrap.

Purpose:
- background settlement may update persistent stores while the UI process/ViewModel remains alive.
- Profit/Results must show the newest cumulative values without requiring an app process restart or manual race refresh.

Validation:
- Unit tests SUCCESS
- Android lint SUCCESS
- Debug APK build SUCCESS
- validated patch was committed to main only after CI passed

### 2. Backup recovery for cumulative ledgers

Commit: `8c5347b16427f724bede82a836c5f1fe3fa63de1`
Validation Run: `36289769011` — SUCCESS

Changes:
- `BetStore` keeps the previous valid JSON payload as `records_backup` before replacing the primary ledger.
- if the primary actual-purchase JSON is malformed, load falls back to the backup and heals the primary copy.
- clearing real purchase history removes both primary and backup intentionally.
- `PredictionHistoryStore` uses the same previous-known-good strategy with `prediction_records_backup`.

Purpose:
- cumulative money history must not silently appear empty only because one SharedPreferences JSON payload becomes malformed.
- audited AI history receives the same protection so live AI cumulative accounting remains auditable.

Validation:
- patch application SUCCESS
- Unit tests SUCCESS
- Android lint SUCCESS
- Debug APK build SUCCESS
- main commit/push SUCCESS

### 3. Align backup export/restore with ledger recovery

Commit: `911a9abb3fa9ff9af2f491982f038d2f5719e3fb`
Validation Run: `36290107958` — SUCCESS

Changes:
- `DataBackupManager.backupJson()` now reads through `BetStore` / `PredictionHistoryStore` rather than raw primary SharedPreferences payloads.
- if a primary ledger is malformed but its recovery copy is valid, export benefits from the same healing path before producing the backup file.
- restore validates all imported records first, then writes the imported actual-purchase payload to both `records` and `records_backup`.
- restore likewise writes imported prediction history to both `prediction_records` and `prediction_records_backup`.

Purpose:
- avoid a state where the app can recover its cumulative history but the Backup action fails on the damaged primary JSON.
- avoid resurrecting a stale pre-import recovery copy after a successful restore.

Validation:
- patch application SUCCESS
- Unit tests SUCCESS
- Android lint SUCCESS
- Debug APK build SUCCESS
- main commit/push SUCCESS

## Current Profit-screen behavior verified

The active screen is `CompactProfitScreen` (the legacy `ProfitScreen` function remains in source but is not used by navigation).

Current active behavior:
- defaults to All time
- actual cumulative money card is first
- audited AI live cumulative card is second
- actual confirmed P/L uses settled tickets only
- unsettled stake is shown separately as pending
- actual hit/race count groups multiple ticket combinations in the same race
- retrospective/model diagnostics stay behind AI analysis rather than dominating the main money view

## Work research status

### Live-money evaluator completed and merged

Original assignment:
`data/WORK_ASSIGNMENT_20260927_V0166_LIVE_MONEY_RESEARCH.md`

Work created PR #9 (`Add v0.16 live money evaluation for existing app backup`) and merged it to main at:
`ccd29d173e0dd1933a839fa37213625683eda328`

Main research validation Run:
`36290527263` — SUCCESS

Delivered:
- `data/v016_live_money_protocol.json`
- `scripts/v016_live_money_eval.py`
- `scripts/v016_live_money_eval_test.py`
- `data/v016_live_money_research_report.md`
- `.github/workflows/v016-live-money-research.yml`

Research foundation:
- parse existing Android `BOAT-AI-backup.json` directly
- keep `bets` (actual purchases) and `predictions` (AI live accounting) separate
- audited live BUY evaluator
- stake / payout / profit / ROI / hit rate
- cumulative profit curve
- max drawdown
- audit completeness
- day / 7d / 30d / month / year / all-time
- slice diagnostics with minimum sample gates
- no fabricated live results when device records are unavailable

### Android combination-format correction

Post-merge parity review found that Android serializes combinations as `1-2-3`, while the first Work evaluator fixture expected compact `123`.

Validation Run:
`36290668041` — SUCCESS

Validated main correction commit:
`f2b8332479ada5af4313285e1e305b6c9b36b7ca`

The evaluator now accepts the exact Android `N-N-N` combination format and its synthetic tests/protocol were updated to match.

### Next Work assignment

`data/WORK_ASSIGNMENT_20260927_V0167_BACKUP_PARITY_AUDIT.md`

Goal:
- field-by-field contract audit between Android `DataBackupManager` / `PredictionRecord` / `BetRecord` / `LiveAuditedPerformance` and the Python evaluator
- add a golden Android-backup fixture and contract tests
- eliminate serializer/null/default/alias mismatches before real device data is evaluated
- research-only; no production Android/Release edits

## v0.16.7 signed release

Version commit used for release:
`d5ad64d59305d2da71d9f60900c8036f4bcb2429`

Release Run:
`36290599312`

Validated release pipeline:
- version resolution SUCCESS
- signing secrets SUCCESS
- release key restore SUCCESS
- `testReleaseUnitTest` / `lintRelease` / `assembleRelease` SUCCESS
- APK signature verification SUCCESS
- Release APK preparation SUCCESS
- GitHub Release publication SUCCESS

Published GitHub Release:
- tag: `v0.16.7`
- name: `BOAT AI v0.16.7`
- published: 2026-09-27
- asset: `BOAT-AI-v0.16.7.apk`
- APK size: 13,678,970 bytes
- SHA-256: `db536a83fbd72b4d6a9cda66e054dda1ac7934ce56d2896b2f27593e64ce4698`

### Release failure / repair note

Two earlier v0.16.7 release attempts failed before publication because the initial version bump accidentally replaced parts of the existing Gradle dependency set:
- first failure exposed missing Jsoup dependency
- second exposed missing JVM `org.json` test dependency

No broken APK was published.
The exact known-good v0.16.6 dependency set was restored while retaining versionCode 42 / versionName 0.16.7, then the signed release pipeline passed.

## Real-device update rule

Install `BOAT-AI-v0.16.7.apk` over the existing BOAT AI installation.
Do **not** uninstall the existing app and do **not** clear app data before updating, because the cumulative actual-purchase and audited prediction ledgers are local app data.

## Next priorities

1. Install/update to signed v0.16.7 without uninstalling the prior app.
2. Accumulate real-device `value-v1` live BUY/SKIP + official odds + settlement data.
3. Verify actual and AI-live cumulative values after real background settlements on device.
4. Work completes the backup/evaluator parity audit and golden-fixture contract tests.
5. When enough real data exists, use the app Backup action to obtain `BOAT-AI-backup.json` and run the evaluator.
6. Diagnose where profit/loss comes from only after sufficient audited live sample exists; do not tune thresholds from tiny samples.
7. Consider migration from SharedPreferences JSON to a transactional local database only if real-device reliability evidence shows the remaining risk justifies it.

## Accuracy boundary

No real-device backup has been evaluated in this handoff, so there is currently **no new factual claim that the live strategy is profitable**. The system is now prepared to measure that from audited real-device data rather than retrospective/final-like assumptions.
