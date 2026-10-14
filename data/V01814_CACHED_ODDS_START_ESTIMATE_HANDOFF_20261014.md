# BOAT AI v0.18.14 — Cached Odds Fallback / Estimated Start-Time Odds

Date: 2026-10-14

## Release

- versionName: 0.18.14
- versionCode: 60
- release target: `736f605dcca238c1b8782821e54726580f37d3c8`
- Debug validation Run: `38505945034` SUCCESS
- Signed Release Run: `38505945004` SUCCESS
- GitHub Release ID: `412308936`
- APK: `BOAT-AI-v0.18.14.apk`
- APK SHA-256: `f526eef08e90b4a054cc48b46503c8cc9d11a9333b68b5f9b6dba903b9a5af1d`

## Goal

Reduce purchase/forecast failures caused by fragile direct official odds acquisition without pretending stale cached odds are real-time.

## Odds acquisition order

1. BOAT RACE official PC odds page.
2. BOAT RACE official smartphone odds page.
3. If either official route does not return every requested combination, fall back to BoatraceCSV `od3` pre-close cache.
4. If no valid complete fallback row exists, fail safely instead of inventing odds.

A partial official parse is no longer treated as success. For Model A 120-way evaluation, all 120 requested odds must be present or the fallback is attempted.

## Cached source

Fallback source:
`https://raw.githubusercontent.com/BoatraceCSV/boatracecsv.github.io/main/data/previews/od3/YYYY/MM/DD.csv`

BoatraceCSV's realtime pipeline runs every five minutes and records one 120-way trifecta snapshot per race before close. The CSV includes:
- race code
- scheduled close
- fetch timestamp
- all 120 trifecta odds

The app uses the actual CSV fetch timestamp; it does not assume that every row is exactly five minutes old.

## Estimated start-time odds

Cached odds are adjusted only when the fallback source is used.

Provisional popularity-rank prior:
- rank 1: final/pre-close prior 0.92
- ranks 2-3: 0.86
- ranks 4-6: 0.87
- ranks 7-12: 0.88
- ranks 13+: 0.96

The prior is blended toward 1.0 based on remaining time:
- 8 minutes or more: full prior
- approaching close: progressively smaller correction
- around 1-3 minutes: only a small correction

Example:
- observed 10.0x, rank 1, 8+ min before close -> estimated 9.2x
- observed 10.0x, rank 1, 2 min before close -> estimated about 9.8x

This correction is intentionally conservative and should be treated as provisional.

## Why not hard-code "-1.5x for favorite"

A recent exploratory check matched 765 races from 2026-10-08 through 2026-10-12 using pre-close od3 and final winning-combination payout.

For the pre-close #1-popularity winning combination:
- median final/pre-close ratio was approximately 0.92
- median absolute movement was approximately -0.7x

That did not support a universal fixed -1.5x rule.

Important limitation: payout data exposes the final realized price only for the winning combination. It is a winner-selected sample, not a full final 120-way table. Production priors must therefore remain conservative until a broader calibration is available.

## UI

When direct official odds are used:
- display remains `オッズ xx.x倍`.

When cached odds are adjusted:
- display label becomes `出走時推定 xx.x倍`.

Model A expected return and stake allocation use the adjusted estimate in fallback mode so stale high odds do not inflate expected value.

## Tests / CI

New tests cover:
- rank-based start-odds adjustment;
- time-to-close blending;
- parsing a complete 120-way cached row;
- preserving the original cache fetch timestamp.

Run `38505945034`:
- live API schema SUCCESS
- unit tests SUCCESS
- Android lint SUCCESS
- Debug APK SUCCESS
- artifact upload SUCCESS

Run `38505945004`:
- test/lint/signed Release build SUCCESS
- APK signature verification SUCCESS
- GitHub Release publication SUCCESS

## Research boundary

This changes production odds handling for fallback cases and therefore new evidence should be separated by `sourceAppVersion` and `liveOddsSource` from older versions.

The frozen historic evaluation logic is not retroactively rewritten.

## Work

Workへの指示:
`data/WORK_ASSIGNMENT_20261014_ODDS_DRIFT_CALIBRATION.md`

Work should expand the pre-close-to-final drift analysis and recommend KEEP/UPDATE for the provisional factors. It must not edit production Android code or model thresholds.
