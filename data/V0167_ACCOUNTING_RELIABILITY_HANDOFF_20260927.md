# BOAT AI v0.16.7 Accounting Reliability Handoff

Date: 2026-09-27
Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`
Public release baseline: `v0.16.6` (versionCode 41)

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

## Work research assignment

Current Work instruction:
`data/WORK_ASSIGNMENT_20260927_V0166_LIVE_MONEY_RESEARCH.md`

Work remains research-only and must not edit Android production/release files.

Requested research foundation:
- audited live BUY evaluator
- stake / payout / profit / ROI / hit rate
- cumulative profit curve
- max drawdown
- audit completeness
- day / 7d / 30d / month / year / all-time
- slice diagnostics with minimum sample gates
- no fabricated live results when device records are unavailable

## Next priorities

1. Accumulate real-device `value-v1` live BUY/SKIP + official odds + settlement data.
2. Verify actual and AI-live cumulative values after real background settlements on device.
3. Add a clean way to export/share audited live accounting records for research evaluation if current backup/export tooling does not expose the required fields.
4. Once sufficient real live records exist, use Work evaluator to diagnose where profit/loss is coming from; do not tune thresholds from tiny samples.
5. Consider migration from SharedPreferences JSON to a transactional local database only if real-device reliability data shows the remaining risk justifies it.

## Release note

These reliability changes are validated on `main` but have not been given a new public version in this handoff. Do not claim v0.16.7 is released until version/release workflow is deliberately executed and signed release succeeds.
