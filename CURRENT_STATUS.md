# BOAT AI Current Status

Updated: 2026-10-11

## SUPERCEDING STATUS — v0.18.8

- Current public version: **v0.18.8**
- versionCode: **54**
- Release target: `1aee55cdb35c9138e41971789401b10158e8bd0a`
- Debug validation Run: `38066405772` SUCCESS
- Signed Release Run: `38066405759` SUCCESS
- GitHub Release ID: `409055038`
- APK: `BOAT-AI-v0.18.8.apk`
- APK SHA-256: `c97bf6310fd9cb30d939500410d53d956c658439aaafa79a3df0ae1963714867`
- Detailed handoff: `data/V0188_QUIET_UI_VERSIONED_EVIDENCE_HANDOFF_20261011.md`

### v0.18.8 changes

- Healthy normal UI stays quiet.
- Up-to-date app-update card is hidden; it appears only for a real update/download/check error.
- Missing exact-alarm access is surfaced only when active races exist and user action is relevant.
- New/updated PredictionRecord rows store `sourceAppVersion` so future private backups can separate v0.18.8+ evidence from legacy/unversioned rows.
- Legacy records remain null/unversioned; envelope appVersion is not used to guess row provenance.
- Frozen live-money accounting/audit rules and the 360 audited-BUY gate are unchanged.
- Codex is suspended from the normal workflow; normal chat handles implementation and Work handles research/evidence.

### Formal evaluation

Last measured private baseline remains **223/360 fully audited value-v1 BUYs; 137 remaining** until the next private backup is evaluated.
Starting with v0.18.8, newly evaluated rows can be isolated by `sourceAppVersion`.

### Work

- Workへの指示: `data/WORK_ASSIGNMENT_20261011_VERSIONED_EVIDENCE_REPORT.md`
- Purpose: prepare version-bucket reporting without changing the frozen evaluator.

---

## Historical status below (superseded where inconsistent)


Updated: 2026-10-11

## SUPERCEDING STATUS — v0.18.6

- Current public version: **v0.18.6**
- versionCode: **52**
- Release target: `e3c4db8e1659333b9e2bbf19874b636c0d416d30`
- Debug validation Run: `38064026654` SUCCESS
- Signed Release Run: `38064026632` SUCCESS
- GitHub Release ID: `409036258`
- APK: `BOAT-AI-v0.18.6.apk`
- APK SHA-256: `977d29afad170937da21738ec0c88fc7af76b35e88ab38838794b59d38a24fa5`
- Detailed handoff: `data/V0186_MINIMAL_BACKGROUND_UI_HANDOFF_20261011.md`

### v0.18.6 UX policy

- Background prediction/retry/recovery internals stay hidden during normal operation.
- Settings exposes only user choices: purchase recommendation notifications, AI purchase preparation, and backup/data controls.
- The stale recovery-mode/background-processing card was removed.
- Successful OK-only diagnostics render no card.
- WAITING/WARNING/ERROR produce one compact actionable card with automatic-retry guidance and an immediate retry button.
- Duplicate red acquisition-error cards were removed.
- Hidden background capture/retry/settlement behavior remains active.

### Operational evidence

Work completed `data/OPERATION_REVIEW_20261011.md` and kept continuity at HOLD until the next private post-v0.18.5/v0.18.6 backup.
The frozen formal-evaluation baseline remains **223/360 audited BUYs; 137 remaining** until a new private backup is measured.

### Parallel follow-up

- Work: no new assignment for this UI-only change; use the existing operation review on the next backup.
- Codex: `data/CODEX_FOLLOWUP_20261011_MINIMAL_BACKGROUND_UI.md`

---

## Historical status below (superseded where inconsistent)


Updated: 2026-10-11

## SUPERCEDING STATUS — v0.18.5

- Current public version: **v0.18.5**
- versionCode: **51**
- Release target: `d828efb649da2147c206ad43e30cf0afc5adc69a`
- Debug validation Run: `38063285208` SUCCESS
- Signed Release Run: `38063285199` SUCCESS
- GitHub Release ID: `409029816`
- APK: `BOAT-AI-v0.18.5.apk`
- APK SHA-256: `340e08dcf41c18675ea6db69ec248eb3f29ebfebae9ebf4270a5543c1926e18c`
- Detailed handoff: `data/V0185_DEADLINE_DATA_WAIT_HANDOFF_20261011.md`

### v0.18.5 changes

- Removed the large Prediction-screen bulk target menu.
- Recommendation-only is the normal bulk-purchase path; the UI no longer offers bulk inclusion of AI-SKIP races.
- "締切順" is now a one-race-per-row nationwide list ordered by each race's closing time.
- Today's source HTTP 404 is treated as publication WAITING rather than a fatal red error.
- Today's dated endpoint falls back to `/api/v1/today.json`, with a requested-date guard preventing stale prior-day records.
- While today's data is unpublished, venue tiles are hidden instead of falsely displaying 24 "開催なし" states.
- The foreground ViewModel retries unpublished data after 15 minutes while alive.
- Background prediction bootstrap retries every 15 minutes until 10:30 JST if the morning daily data is still unavailable.
- No prediction threshold, stake rule, or formal evaluation rule changed.

### Formal evaluation target

The frozen target remains **360 fully audited value-v1 BUYs**.
The last reviewed private backup had **223**, so the reviewed baseline remaining count is **137**. The app calculates the live remaining count from current durable data.

### Parallel work

- Work assignment: `data/WORK_ASSIGNMENT_20261011_OPERATION_REVIEW.md`
- Codex assignment: `data/CODEX_ASSIGNMENT_20261011_UI_BACKGROUND_REVIEW.md`

---

## Historical status below (superseded where inconsistent)


Updated: 2026-10-10

## SUPERCEDING STATUS — v0.18.4

- Current public version: **v0.18.4**
- versionCode: **50**
- Release target: `611541d8901afd9b9a1f3c6ffcfd341a21b63236`
- Debug validation Run: `38062106818` SUCCESS
- Signed Release Run: `38062106863` SUCCESS
- GitHub Release ID: `409020260`
- APK: `BOAT-AI-v0.18.4.apk`
- APK SHA-256: `9d23f52891d602bbfc167cdbbdfb194aefc1abbf2843502364074c166c330e87`
- Detailed handoff: `data/V0184_BACKGROUND_AUTOMATION_HANDOFF_20261010.md`

### v0.18.4 changes

- Fresh installs default to normal mode; recovery mode remains for actual crashes.
- Normal process startup self-heals background prediction tracking.
- Tracking reschedules after reboot, package replacement, date/time/timezone changes.
- Prediction tracking remains active even when BUY notifications are OFF.
- Notification settings now use an explicit ON/OFF switch.
- Notification-side live evaluation persists full official odds audit evidence.
- Optional AI purchase preparation automatically creates/appends a local pending-purchase draft from BUY decisions.
- Automatic purchase preparation never submits an external wager; final official submission remains user-confirmed.
- Profit screen now shows formal-evaluation progress against the frozen 360 audited-BUY target.
- First real evaluation baseline: 223/360 audited BUYs, so the starting remaining count is **137**.
- Work/Codex routing is defined in `data/DEVELOPMENT_ROUTING.md`.

### Android background limitation

A brand-new Android install still requires one initial user launch before reliable background execution is possible. Android Force stop also blocks alarms/background starts until the next user launch. v0.18.4 removes the extra recovery-mode gate and restores scheduling automatically after normal reboot/update/time changes, but does not falsely claim to bypass Android's stopped-package rules.

---

## Historical status below (superseded where inconsistent)


Updated: 2026-10-10

## SUPERCEDING STATUS — v0.18.2

- Current public version: **v0.18.2**
- versionCode: **48**
- Release target: `1acabb4ccee9cc01e5f8149513fa80684fc447c0`
- Debug validation Run: `38060657559` SUCCESS
- Signed Release Run: `38060657553` release build/sign/publish SUCCESS
- GitHub Release ID: `409008690`
- APK: `BOAT-AI-v0.18.2.apk`
- APK SHA-256: `806f1d9cd1d267142fa3f3abea30abcd2585c25ed2d29d62c7b7c1773c488c62`

### First real-device live-money evaluation

Private device backup exported from appVersion 0.18.1 on 2026-10-10 was evaluated with the frozen live-money rules. The raw backup was not committed.

- predictions: 1,797
- live value-v1 BUY candidates: 457
- fully audited BUYs: 223 (48.80% completeness)
- audited hits: 74 / 223 = 33.18%
- audited stake: 497,800 JPY
- audited payout: 455,920 JPY
- audited profit: **-41,880 JPY**
- audited ROI: **91.59%**
- audited max drawdown: 75,820 JPY
- October audited ROI through available records: **99.62%** (-1,320 JPY)
- actual-purchase `bets` array in this export: empty, so actual user purchase ROI cannot be evaluated from this backup.
- protocol slice threshold is 360 audited BUYs; do not promote post-hoc point/odds/confidence gates from the current 223.

Detailed aggregate report: `data/REAL_LIVE_EVAL_20261010.md`.

### v0.18.2 audit-completeness fix

The real backup exposed a tracking bug: provisional unsettled `value-v1` records could be saved without durable live-odds audit fields, then the near-close background evaluator returned early merely because a strategyId already existed.

Fix:
- near-close tracking now re-evaluates provisional unsettled records regardless of existing `value-v1` / `legacy-final-v1` strategyId;
- only settled records block re-evaluation;
- regression tests cover unsettled value, unsettled legacy, settled, and missing record cases.

Commits:
- `1e30226e5caa4395f5d8a112758a24ce34d4ce6f`
- `ddd89cfc66c43a060eb2adda0c7bf534de0f6a9e`
- release bump `1acabb4ccee9cc01e5f8149513fa80684fc447c0`

### Next evidence target

Install v0.18.2 **over the existing app without uninstalling or clearing data**. Treat all already-inspected data as historical evidence. For the next prospective decision, accumulate new v0.18.2 audited BUYs and re-run the same frozen evaluator. Also investigate daily continuity because the 2026-10-10 export contained no prediction records for 2026-10-06, 2026-10-09, or 2026-10-10.

---

## Historical status below (superseded where inconsistent)


Updated: 2026-09-27

## Product goal

BOAT AI is not primarily an explanation app. The main goal is to answer two practical questions:

1. If the user follows the AI purchase recommendations, does the money increase or decrease?
2. What is the cumulative performance so far?

Detailed model explanations, feature importance, and race-theory commentary are secondary. They may be used internally for research and model improvement, but they are not a top UI priority.

## Current release

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- Current public version: **v0.16.9**
- versionCode: **44**
- Release target: `446d84f1a57c4e9a489492fdf3ed2edbf9dff84b`
- Signed Release Run: `36318605815` SUCCESS
- Debug validation Run: `36318605810` SUCCESS
- Pre-release backup-export validation Run: `36318440533` SUCCESS
- GitHub Release ID: `397639019`
- APK: `BOAT-AI-v0.16.9.apk`
- APK SHA-256: `c701984ab8410e696e3e3d39d34491fb47722fbcc78d9fc66da5822422ab3426`
- Detailed handoff: `data/V0169_DIRECT_BACKUP_HANDOFF_20260927.md`
- Research-only work does **not** change the published APK/version unless explicitly promoted through Android release work.

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

## Latest implementation progress — v0.16.9

Completed and released:

- v0.16.8 purchase-safety improvements remain intact: selected purchase totals, zero-selection guard, Select all / Clear all, unresolved pending-session overwrite prevention, and pending-purchase card on the Prediction screen.
- Settings > Data management now has a primary **direct file save** action for `BOAT-AI-backup.json` using Android's document-save UI.
- The user can choose a device/document-provider location directly instead of first routing through a share target.
- The previous backup-share action remains available separately.
- Backup JSON schema is unchanged, so the frozen live-money evaluator remains compatible.
- The Settings card explicitly warns that the backup contains actual purchase history and should not be uploaded to a public location.
- Debug and Release CI no longer regenerate a Gradle Wrapper on every run. Both use the fixed Gradle 8.10.2 installation provisioned by `gradle/actions/setup-gradle`, removing the wrapper-URL validation failure point seen in Run `36318317657`.
- Signed v0.16.9 Release passed release unit tests, release lint, signed APK build, APK signature verification, and GitHub Release publication.
- v0.16.9 Debug validation passed live API verification, unit tests, lint, Debug APK build, and artifact upload.

Validation / commits:

- Direct backup writer: commit `3ad7b830a8ef7b4c8b1d04213561b98fec641ea5`.
- Explicit backup UI: commit `252092779c33d4ba78ca0ab76128b73d890f981a`.
- Debug CI hardening: commit `c30b894aed9628ee600f7aef80c142e3a6ded707`.
- Release CI hardening: commit `fa296005b35c0a1c541ae870ebc41fb3adadba1a`.
- Direct backup source validation: Run `36318440533` SUCCESS.
- v0.16.9 release commit: `446d84f1a57c4e9a489492fdf3ed2edbf9dff84b`.
- Signed v0.16.9 Release: Run `36318605815` SUCCESS.
- v0.16.9 Debug validation: Run `36318605810` SUCCESS.

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

- a real device `BOAT-AI-backup.json` exported from v0.16.9 or later.
- Do **not** commit the real backup to the public repository; it can contain actual purchase history and learning state.
- Run the frozen evaluator directly against that private backup and compare AI-live cumulative accounting with actual-purchase accounting.

## Real-device update rule

Install `BOAT-AI-v0.16.9.apk` over the existing app.

**Do not uninstall BOAT AI and do not clear app data before updating.**
The actual-purchase and audited prediction ledgers are local app data.

## Still requires real-device/live-race evidence

- overwrite install v0.16.9 while preserving existing data
- existing actual-purchase totals remain intact after update
- background settlement updates Profit/Results correctly in real use
- Result-screen audit rows match Profit-screen audited counts
- real BUY/SKIP + live official odds accumulate normally
- pending purchase survives the official-site round trip and can be confirmed without being overwritten
- direct Settings backup saves a real `BOAT-AI-backup.json` that passes the frozen evaluator
- enough audited live BUY records exist to make a meaningful cumulative profit/ROI judgment

There is currently **no factual claim that the live strategy is profitable**, because no real-device backup has yet been evaluated through the completed evaluator.

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
- export existing `BOAT-AI-backup.json` using the direct-save action added in v0.16.9
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

Old notes such as v0.15.x state, v0.16.8 being current, or "Q4 unopened" must not override newer verified status.

## User-facing design principle

The user should be able to open BOAT AI and quickly understand:

- What should I buy?
- How much should I buy?
- How much have I put in?
- How much has come back?
- Am I up or down overall?

Everything else is secondary to those questions.
