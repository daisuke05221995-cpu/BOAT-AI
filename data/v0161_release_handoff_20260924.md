# BOAT AI v0.16.1 release handoff

Date: 2026-09-24

## Release

- Version: `0.16.1`
- versionCode: `36`
- Release target: `1a0296af334431081fa70d7f7a637b49d634fad1`
- Standard Build Run: `36012800871` SUCCESS
- Signed Release Run: `36012801217` SUCCESS
- Release ID: `395773668`
- APK: `BOAT-AI-v0.16.1.apk`
- APK SHA-256: `f855a888b8c8e89c532e60ab54cca3f695093942d9b39c5ee5be4478e6c7f695`

## Rolling retrospective Model A results

v0.16.1 adds a separate retrospective Model A virtual-results feed. It does not enter live purchase recommendations or the live PredictionHistoryStore performance profile.

Rules:
- Forecast model: frozen market-free v0.16 Model A.
- Historical prediction state: strictly through the previous calendar day.
- Same-day results are applied only after that day's pre-race feature snapshots/predictions are generated.
- Display window: rolling 30 days only.
- Picks: Model A top 4 trifecta combinations.
- Virtual stake: 300 yen per pick / 1,200 yen per race.
- Settlement: official settled trifecta payout after the race.
- `preCloseOddsClaim=false`: this is not evidence that the same price was available before betting close.
- Automatic BUY remains OFF.

Initial generated window `2026-08-25` through `2026-09-23`:
- races: 4,333
- hits: 1,284
- stake: 5,199,600 yen
- payout: 4,046,100 yen
- profit: -1,153,500 yen
- ROI: 77.8152%

Generator:
- `scripts/v016_recent_virtual.py`
- daily workflow `.github/workflows/v016-recent-virtual.yml`
- scheduled 07:30 JST to refresh through the previous day.
- rolling state: `data/model_a_recent_history.bin`
- feed: `data/model_a_recent_virtual_results.json`
- summary: `data/model_a_recent_virtual_summary.json`

## Android behavior

- Historical browsing is limited to approximately one month.
- Selecting an ended historical race immediately uses its stored retrospective Model A top-4 forecast; it does not recompute the past race with the current history state.
- The race detail then obtains official ended-race odds for those same top-4 combinations and labels them as post-race official odds.
- Results list shows Model A virtual stake/payout/profit where available.
- Profit/Loss screen has a dedicated `Model A 過去仮想損益（確定払戻）` card.
- Retrospective records are isolated from live forecast learning and purchase recommendation state.

## Safety / interpretation

The historical odds archive still has verdict `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`; therefore v0.16.1 does not promote any automatic purchase policy. The retrospective P/L is a forecast-quality reference settled with official post-race payout, not a realizable pre-close ROI claim.
