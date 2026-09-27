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
- Current public version: **v0.16.8**
- versionCode: **43**
- Release target: `e58fd4393d9928949484b75092ca5690ece58de4`
- Signed Release Run: `36317879182` SUCCESS
- Debug validation Run: `36317879225` SUCCESS
- GitHub Release ID: `397634824`
- APK: `BOAT-AI-v0.16.8.apk`
- APK SHA-256: `c575743718eceb3f38539e1a69db6103d50507855585b1a6935a445f917a4ea3`
- Detailed handoff: `data/V0168_PURCHASE_SAFETY_HANDOFF_20260927.md`
- Research-only backup parity work does **not** change the published APK/version.

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

## Latest implementation progress — v0.16.8

Completed and released:

- v0.16.7 accounting reliability remains intact: resume-time durable accounting sync, recovery copies for actual and AI-live ledgers, and backup export/restore alignment.
- Pending purchase now shows both the full candidate total and the **currently selected** race count / ticket count / total stake.
- Official-purchase button shows the selected total, is disabled at zero selected races, and only selected races are copied.
- Pending purchase has **Select all** and **Clear all** controls.
- `OfficialBetLauncher` has a zero-selection guard.
- Unit tests verify selected-only clipboard output and the zero-selection case.
- A new purchase session can no longer silently overwrite an unresolved pending purchase session.
- The Prediction screen now shows the pending-purchase card, so after returning from the official purchase surface the user can immediately confirm the races actually purchased or discard the pending session.
- Existing bulk selection, individual purchase selection, editable planned budget, total planned stake, official purchase handoff, and actual-purchase recording remain available.
- Signed v0.16.8 Release pipeline passed release unit tests, release lint, signed APK build, APK signature verification, and GitHub Release publication.

Validation / commits:

- Selected-total / zero-selection safety: commit `1619f2db7f3249d510cb52ac5bb05851567b4ed1`, Run `36317240148` SUCCESS.
- Pending-session overwrite prevention: source commit `4ab0e85b4a7ea246e4eb597abf5b64a2ca6fb73a`; pre-commit Run `36317673303` passed patch verification, tests, lint and Debug APK build.
- v0.16.8 release commit: `e58fd4393d9928949484b75092ca5690ece58de4`.
- Signed v0.16.8 Release: Run `36317879182` SUCCESS.
- v0.16.8 Debug validation: Run `36317879225` SUCCESS.

## Work research status

Work is research-only and must not edit production Android / release files.

Completed:

- PR #9 added the audited live-money evaluator for existing `BOAT-AI-backup.json` and was merged to main at `ccd29d173e0dd1933a839fa37213625683eda328`.
- Main research validation Run `36290527263` SUCCESS.
- Evaluator separates `bets` actual purchases from `predictions` AI-live records.
- It supports stake, payout, profit, ROI, hit rate, cumulative profit curve, maximum drawdown, audit completeness, and Today / 7d / 30d / Month / Year / All time.
- It does not fabricate profitability when no real device export is supplied.
- Android trifecta combination format was corrected from compact `123` assumptions to the production `1-2-3` format; Run `36290668041` SUCCESS, commit `f2b8332479ada5af4313285e1e305b6c9b36b7ca`.
- v0.16.7 backup parity audit is complete: Android serializer-compatible golden backup fixture added, envelope/field names/defaults checked, legacy `recommended` default matched, and result-known/payout-zero records accepted consistently.
- Backup parity commit: `d12504ab2ca65b690044b6761a3a2ff773b6d357`.
- Backup parity research validation: Run `36310196169` SUCCESS with protocol JSON, golden backup JSON and 18 tests.
- Detailed research report: `data/v016_live_money_research_report.md`.

Next research input:

- a real device `BOAT-AI-backup.json` exported from v0.16.8 or later.
- Do **not** commit the real backup to the public repository; it can contain actual purchase history and learning state.
- Run the frozen evaluator directly against that backup and compare AI-live cumulative accounting with actual-purchase accounting.

## Real-device update rule

Install `BOAT-AI-v0.16.8.apk` over the existing app.

**Do not uninstall BOAT AI and do not clear app data before updating.**
The actual-purchase and audited prediction ledgers are local app data.

## Still requires real-device/live-race evidence

- overwrite install v0.16.8 while preserving existing data
- existing actual-purchase totals remain intact after update
- background settlement updates Profit/Results correctly in real use
- Result-screen audit rows match Profit-screen audited counts
- real BUY/SKIP + live official odds accumulate normally
- pending purchase survives the official-site round trip and can be confirmed without being overwritten
- app Backup produces a real `BOAT-AI-backup.json` that passes the frozen evaluator directly
- enough audited live BUY records exist to make a meaningful cumulative profit/ROI judgment

There is currently **no new factual claim that the live strategy is profitable**, because no real-device backup has yet been evaluated through the completed evaluator.

## Planned phases

### Phase 1 — Stabilize real operation
- overwrite update only; preserve app data
- verify live BUY/SKIP persistence
- verify automatic/background settlement
- verify actual and AI-live cumulative accounting
- verify backup/export/restore reliability

### Phase 2 — Complete evaluator parity — COMPLETED 2026-09-27
- Android backup/evaluator contract audit completed
- golden Android serializer-compatible fixture added
- cross-language behavior covered by contract tests
- actual and AI-live accounting remain strictly separate
- validation Run `36310196169` SUCCESS

### Phase 3 — Accumulate real live evidence — NEXT
- collect audited live BUY records
- export existing `BOAT-AI-backup.json`
- evaluate cumulative stake / payout / profit / ROI / hit rate / drawdown
- diagnose where money is gained or lost only after sufficient sample exists

### Phase 4 — Simplify purchase workflow — CORE FLOW COMPLETED IN v0.16.8
- bulk selection: implemented
- individual purchase selection: implemented
- editable planned budget/stake controls: implemented where currently supported
- total planned stake: implemented
- official purchase-screen handoff: implemented
- actual-purchase recording: implemented
- selected-total clarity and zero-selection guard: implemented
- unresolved pending-session overwrite protection: implemented
- further UX reduction can continue, but it is no longer the main blocker

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

Old notes such as v0.15.x state, v0.16.6/v0.16.7 being current, or "Q4 unopened" must not override newer verified status.

## User-facing design principle

The user should be able to open BOAT AI and quickly understand:

- What should I buy?
- How much should I buy?
- How much have I put in?
- How much has come back?
- Am I up or down overall?

Everything else is secondary to those questions.
