# BOAT AI Current Status

Updated: 2026-09-27

## Product goal

BOAT AI is not primarily an explanation app. The main goal is to answer two practical questions:

1. If the user follows the AI purchase recommendations, does the money increase or decrease?
2. What is the cumulative performance so far?

Detailed model explanations, feature importance, and race-theory commentary are secondary. They may be used internally for research and model improvement, but they are not a top UI priority.

## Current release

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- Current public version: **v0.16.7**
- versionCode: **42**
- Release target: `d5ad64d59305d2da71d9f60900c8036f4bcb2429`
- Signed Release Run: `36290599312` SUCCESS
- GitHub Release ID: `397490360`
- APK: `BOAT-AI-v0.16.7.apk`
- APK SHA-256: `db536a83fbd72b4d6a9cda66e054dda1ac7934ce56d2896b2f27593e64ce4698`
- Detailed handoff: `data/V0167_ACCOUNTING_RELIABILITY_HANDOFF_20260927.md`

## Development priority

### Priority 1: Money and cumulative performance

The most important information in the app is:

- total stake
- total payout
- total profit/loss
- ROI
- number of BUY races
- hit count / hit rate
- average stake
- cumulative results for today / 7 days / 30 days / month / year / all time

The Profit screen should make these figures easy to understand at a glance.

### Priority 2: Keep three accounting series separate

Never mix these three:

1. **AI live virtual performance**: what would have happened if every valid live AI BUY had been purchased.
2. **Actual user purchase performance**: money the user actually purchased and received.
3. **Retrospective/research performance**: historical backtests and post-race diagnostic simulations.

The user should be able to compare AI-live and actual-purchase cumulative performance easily. Research/backtest numbers must remain clearly separate.

### Priority 3: Reliability of live accounting

Before major new prediction models, keep live records trustworthy:

- complete official trifecta odds snapshot
- source and fetch timestamp persisted
- selected-pick odds persisted
- no duplicate race accounting
- stable persistence through app/background lifecycle
- automatic settle after race results
- live audited totals match Result-screen records
- incomplete audit records expose the reason instead of silently disappearing
- cumulative ledgers recover from malformed local JSON
- backup export/restore uses the same recovery path

### Priority 4: Simple purchase decision UI

Prediction should prioritize:

- BUY / SKIP
- recommended combinations
- stake for each combination
- total stake
- purchase deadline / availability

Detailed model data may remain available but should not dominate the main flow.

### Priority 5: Model improvement stays mostly behind the scenes

Model A remains the production forecast baseline.

Future Model B / Model C / LONGSHOT research should be evaluated mainly by realizable audited cumulative money performance, adequate sample size, out-of-sample evidence, drawdown, and concentration risk. Do not promote from retrospective final-like odds alone.

## Latest implementation progress — v0.16.7

Completed and released:

- v0.16.6 money-first Profit UI remains the base: **Actual purchase cumulative first**, **AI live cumulative second**, default **All time**.
- `BoatViewModel.syncStoredAccounting()` reloads durable accounting when the app resumes and when Purchase / Results / Profit is opened.
- background settlement no longer requires an Activity/process restart before the newest cumulative totals appear.
- `BetStore` now keeps the previous valid actual-purchase ledger and automatically recovers/heals the primary payload if malformed.
- `PredictionHistoryStore` now provides the same previous-known-good recovery for audited AI history.
- Backup export now reads through the recovering stores instead of raw primary JSON.
- Restore seeds both primary and recovery copies with the validated imported payload, preventing rollback to stale pre-import data.
- Signed v0.16.7 Release pipeline passed release unit tests, release lint, signed APK build, APK signature verification, and GitHub Release publication.

Validation / commits:

- Accounting resume sync: Run `36289522137` SUCCESS, commit `01477e14def5928e55ee5b8f160f93cbaea279ba`.
- Ledger backup recovery: Run `36289769011` SUCCESS, commit `8c5347b16427f724bede82a836c5f1fe3fa63de1`.
- Backup export/restore alignment: Run `36290107958` SUCCESS, commit `911a9abb3fa9ff9af2f491982f038d2f5719e3fb`.
- Signed v0.16.7 Release: Run `36290599312` SUCCESS.

Release repair note:

- Two earlier v0.16.7 release attempts failed safely before publication after the version bump accidentally replaced parts of the known-good Gradle dependency set.
- The exact v0.16.6 dependency set was restored while retaining versionCode 42 / versionName 0.16.7.
- No broken APK was published.

## Work research status

Work is research-only and must not edit production Android / release files.

Completed:

- PR #9 added the audited live-money evaluator for existing `BOAT-AI-backup.json` and was merged to main at `ccd29d173e0dd1933a839fa37213625683eda328`.
- Main research validation Run `36290527263` SUCCESS.
- Evaluator separates `bets` actual purchases from `predictions` AI-live records.
- It supports stake, payout, profit, ROI, hit rate, cumulative profit curve, maximum drawdown, audit completeness, and Today / 7d / 30d / Month / Year / All time.
- It does not fabricate profitability when no real device export is supplied.

Compatibility correction:

- Android stores trifecta combinations as `1-2-3` style, while the first evaluator fixture expected `123`.
- Corrected and validated by Run `36290668041` SUCCESS.
- Main correction commit: `f2b8332479ada5af4313285e1e305b6c9b36b7ca`.

Current Work assignment:

- `data/WORK_ASSIGNMENT_20260927_V0167_BACKUP_PARITY_AUDIT.md`
- Perform field-by-field parity audit between Android serializers and Python evaluator.
- Add a golden Android backup fixture and contract tests.
- Eliminate remaining field/null/default/alias mismatches before evaluating real device data.

## Real-device update rule

Install `BOAT-AI-v0.16.7.apk` over the existing app.

**Do not uninstall BOAT AI and do not clear app data before updating.**
The actual-purchase and audited prediction ledgers are local app data.

## Still requires real-device/live-race evidence

- overwrite install v0.16.7 while preserving existing data
- existing actual-purchase totals remain intact after update
- background settlement updates Profit/Results correctly in real use
- Result-screen audit rows match Profit-screen audited counts
- real BUY/SKIP + live official odds accumulate normally
- app Backup produces a real `BOAT-AI-backup.json` that passes the Work evaluator
- enough audited live BUY records exist to make a meaningful cumulative profit/ROI judgment

There is currently **no new factual claim that the live strategy is profitable**, because no real-device backup has yet been evaluated through the completed evaluator.

## Planned phases

### Phase 1 — Stabilize v0.16.7 real operation
- overwrite update only; preserve app data
- verify live BUY/SKIP persistence
- verify automatic/background settlement
- verify actual and AI-live cumulative accounting
- verify backup/export/restore reliability

### Phase 2 — Complete evaluator parity
- Work completes Android backup/evaluator contract audit
- add golden fixture and cross-language parity tests
- keep actual and AI-live accounting strictly separate

### Phase 3 — Accumulate real live evidence
- collect audited live BUY records
- export existing `BOAT-AI-backup.json`
- evaluate cumulative stake / payout / profit / ROI / hit rate / drawdown
- diagnose where money is gained or lost only after sufficient sample exists

### Phase 4 — Simplify purchase workflow further
- bulk selection
- individual purchase selection
- editable stake where appropriate
- total planned stake
- official purchase-screen handoff
- actual-purchase recording

### Phase 5 — Model B/C research
- test new models without destabilizing Model A
- promote only candidates that improve robust out-of-sample and audited live-accounting performance

### Phase 6 — LONGSHOT
- separate LONGSHOT BUY from normal BUY
- maintain independent and combined cumulative results

## Source-of-truth order

When documents disagree, use this order:

1. latest GitHub Release / latest `main` / current GitHub Actions
2. `CURRENT_STATUS.md`
3. `PROJECT_STATUS.md`
4. latest version-specific handoff under `data/`
5. `NEXT_WEEK_HANDOFF.md`
6. `WORK_HANDOFF.md` historical notes

Old notes such as v0.15.x state, v0.16.6 being current, or "Q4 unopened" must not override newer verified status.

## User-facing design principle

The user should be able to open BOAT AI and quickly understand:

- What should I buy?
- How much should I buy?
- How much have I put in?
- How much has come back?
- Am I up or down overall?

Everything else is secondary to those questions.
