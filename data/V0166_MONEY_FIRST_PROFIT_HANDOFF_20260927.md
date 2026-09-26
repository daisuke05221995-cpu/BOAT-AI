# BOAT AI v0.16.6 Money-First Profit Handoff

Date: 2026-09-27

## Release

- Version: `v0.16.6`
- versionCode: `41`
- Release target commit: `80f7800eaac984c549ccdd67dcf63b7f71158687`
- Build Run: `36257301807` — SUCCESS
- Signed Release Run: `36257301835` — SUCCESS
- Release ID: `397321639`
- APK: `BOAT-AI-v0.16.6.apk`
- APK size: `13,678,970` bytes
- APK SHA-256: `9abf8fcdedf175035a09698e9ee591a7a9f104f0b70df21c4fc50b4730dc78ec`

## Product direction fixed in this release

The user-facing priority is money and cumulative performance, not detailed model explanations.

The app should answer these questions first:

1. What should I buy and how much?
2. How much have I put in?
3. How much has come back?
4. Am I up or down overall?
5. If every valid live AI BUY had been purchased, what would the cumulative result be?

Detailed exhibition/motor/weather/model explanations remain useful internally for research, but they are secondary in the main UI.

## Implemented in v0.16.6

### Cumulative Profit periods

Added common period filters:

- Today
- 7 days
- 30 days
- Month
- Year
- All time

The Profit screen now defaults to **All time** because cumulative performance is the primary user need.

### Actual purchase cumulative card

The top card now emphasizes actual money performance:

- cumulative profit/loss
- total settled stake
- total payout
- ROI
- purchased race count
- hit race count
- hit rate
- pending stake

Multiple tickets in the same race are grouped as one race for race-count and hit-rate purposes.

### AI live cumulative card

The second main card emphasizes only audited live AI BUY records:

- cumulative profit/loss
- hits / races
- total stake
- payout
- ROI
- audited BUY count / all live BUY count
- audit completeness

Retrospective/backtest results are not mixed into this live accounting series.

### Live audit failure diagnosis

Incomplete live BUY records now expose explicit reasons rather than silently disappearing from cumulative live results:

- missing fetch timestamp
- missing odds source
- fewer than 120 official trifecta odds
- missing selected combinations
- invalid/mismatched stake allocation
- missing selected-pick live odds

The Profit screen aggregates these failure reasons when incomplete live BUY records exist.

### Research information de-emphasized

Retrospective Model A profit and point-count diagnostic cards were removed from the always-visible Profit flow. Research/diagnostic information remains available under the AI analysis/validation section.

## Reliability checks

Confirmed in code and CI:

- prediction-history refresh preserves original `createdAt`
- settled prediction records are not overwritten by later open-race snapshots
- newer unsettled live snapshots replace the same race record rather than append duplicate race history
- confirmed actual purchases reject duplicate date/venue/race/combination tickets
- 7d/30d/month/year/all-time period boundaries have unit tests
- live-audit failure classification/counts have unit tests

Validation:

- one-shot money-first UI validation: Unit test / lint / Debug APK SUCCESS
- cumulative all-time UI validation: Unit test / lint / Debug APK SUCCESS
- official v0.16.6 Build Run `36257301807`: live API schema / Unit tests / lint / Debug APK / artifact upload all SUCCESS
- Signed Release Run `36257301835`: release version / signing secrets / release Unit test / release lint / signed APK / signature verification / GitHub Release publication all SUCCESS

## Real-device/live verification still required

1. Install v0.16.6 over the existing app. Do not uninstall or clear app data.
2. Confirm Profit opens on All time and existing stored actual-purchase totals remain intact.
3. Confirm actual purchase race/hit counts look correct when multiple combinations exist in one race.
4. Accumulate real `value-v1` BUY/SKIP records with official live odds.
5. After results settle, compare Result-screen live audit rows with AI live cumulative counts.
6. Confirm background/process lifecycle does not lose pending prediction or purchase records.
7. Confirm automatic settlement updates cumulative money without duplicate accounting.

## Next development step

Continue Phase 1 reliability using actual live records, then finish Phase 2 cumulative-money UX. Do not prioritize verbose prediction explanations. The next development decisions should be driven primarily by whether the accounting is trustworthy and whether the cumulative money result is immediately understandable.
