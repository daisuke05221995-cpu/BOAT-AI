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
- Current public version: **v0.16.5**
- versionCode: **40**
- Release target: `a401530f1e697c0ae86adac95dcc5b320cdf4ce1`
- Build Run: `36238671361` SUCCESS
- Signed Release Run: `36238671351` SUCCESS
- Release ID: `397209702`
- APK: `BOAT-AI-v0.16.5.apk`

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

### Priority 3: Simple purchase decision UI

The Prediction screen should prioritize:

- BUY / SKIP
- recommended combinations
- stake for each combination
- total stake
- race purchase deadline / purchase availability

Do not make detailed prediction explanations a primary requirement. Model probability, odds details, exhibition data, wind, motor information, etc. can remain available where useful, but they should not dominate the main flow.

### Priority 4: Reliability of live accounting

Before adding major new prediction models, make sure live records are trustworthy:

- complete official trifecta odds snapshot
- source and fetch timestamp persisted
- selected-pick odds persisted
- no duplicate race accounting
- stable persistence through app/background lifecycle
- unsettled-record updates preserve the original creation time
- automatic settle after race results
- live audited totals match the Result screen records
- incomplete audit records expose the reason instead of silently disappearing

### Priority 5: Model improvement stays mostly behind the scenes

Model A remains the current production forecast baseline.

Future Model B / Model C / LONGSHOT research should be evaluated mainly by whether it improves realizable cumulative money performance while maintaining enough sample size and audit quality. The app does not need to explain every model feature to the user.

## Planned phases

### Phase 1 — Stabilize v0.16.5 live operation
- real-device overwrite update only; do not clear app data
- verify live BUY/SKIP persistence
- verify live audited Profit totals
- improve audit-failure diagnosis
- verify lifecycle/background reliability

### Phase 2 — Make cumulative profit the center of the app
- strengthen Profit screen
- today / 7d / 30d / month / year / all-time switching
- prominently show stake / payout / profit / ROI
- compare AI-live vs actual-user cumulative performance

### Phase 3 — Simplify purchase workflow
- improve bulk selection
- individual purchase selection
- editable stake where appropriate
- total planned stake
- official purchase-screen handoff
- actual-purchase recording

### Phase 4 — Accumulate real live evidence
- collect audited live BUY records
- evaluate cumulative live performance
- break down only when needed to find where money is gained or lost

### Phase 5 — Model B/C research
- test new models without destabilizing Model A
- promote only candidates that improve robust out-of-sample performance and live-accounting usefulness

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

Old notes such as v0.15.x state or "Q4 unopened" must not override newer verified status.

## User-facing design principle

The user should be able to open BOAT AI and quickly understand:

- What should I buy?
- How much should I buy?
- How much have I put in?
- How much has come back?
- Am I up or down overall?

Everything else is secondary to those questions.
