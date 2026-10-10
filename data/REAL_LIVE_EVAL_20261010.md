# BOAT AI 実ライブ評価 — 2026-10-10

Input: private user-device `BOAT-AI-backup.json` exported 2026-10-10.
The raw backup was **not** committed to this public repository.

## Provenance

- backup schemaVersion: 1
- appVersion at export: 0.18.1
- exportedAt: 2026-10-10T14:31:25.970560Z
- predictions: 1,797 records
- actual purchase `bets`: 0 records
- prediction date range in the export: 2026-09-21 through 2026-10-08
- live value-v1 BUY candidate range: 2026-09-26 through 2026-10-08

Important: the backup stores appVersion only at the envelope level, not per prediction record.

## Frozen evaluator result

Using the pre-registered v016 live-money accounting/audit rules:

- settled/evaluationEligible/recommended/value-v1 BUY candidates: **457**
- fully audited BUYs: **223**
- audit completeness: **48.80%**
- incomplete BUYs: **234**
- every incomplete BUY is missing the same four audit elements:
  - FETCH_TIME: 234
  - SOURCE: 234
  - ODDS_COUNT: 234
  - PICK_ODDS: 234

Audited money result:

- BUY races: **223**
- hits: **74**
- hit rate: **33.18%**
- stake: **497,800 JPY**
- payout: **455,920 JPY**
- profit: **-41,880 JPY**
- ROI: **91.59%**
- average stake: **2,232 JPY**
- maximum drawdown: **75,820 JPY**

October-only audited result through the available records:

- BUYs: 160
- stake: 348,300 JPY
- profit: -1,320 JPY
- ROI: **99.62%**

Last 7 days relative to 2026-10-10 (records available only through 2026-10-08):

- audited BUYs: 80
- profit: -38,050 JPY
- ROI: **77.63%**

## Sensitivity only — NOT audited performance

The 234 excluded BUYs still contain combinations/stakes/results, but lack the frozen audit evidence. If mechanically accounted anyway:

- stake: 507,000 JPY
- payout: 476,250 JPY
- profit: -30,750 JPY
- ROI: 93.93%

All 457 BUY candidates mechanically combined:

- stake: 1,004,800 JPY
- payout: 932,170 JPY
- profit: -72,630 JPY
- ROI: 92.77%

These values are diagnostic only and must not replace the audited result.

## Exploratory slices — NOT promotion evidence

The protocol requires at least 360 audited BUYs before descriptive slice diagnostics are considered sufficiently populated. Current audited BUYs = 223, so all slices below are hypothesis generation only.

By selected point count:

| Points | Races | Hit rate | Stake | Payout | Profit | ROI |
|---:|---:|---:|---:|---:|---:|---:|
| 4 | 92 | 33.70% | 210,400 | 118,070 | -92,330 | 56.12% |
| 5 | 52 | 38.46% | 117,500 | 192,660 | +75,160 | 163.97% |
| 6 | 43 | 25.58% | 95,600 | 60,520 | -35,080 | 63.31% |
| 7 | 19 | 36.84% | 36,200 | 22,700 | -13,500 | 62.71% |
| 8 | 17 | 29.41% | 38,100 | 61,970 | +23,870 | 162.65% |

Concentration warning:
- removing the single largest audited payout reduces overall ROI from 91.59% to 83.87%
- removing the top 5 audited payouts reduces ROI to 63.90%
- top 5 payouts contribute 32.29% of total audited payout
- 8-point ROI is highly concentrated: the largest payout is 52.7% of all 8-point payout
- 7-point ROI is also concentrated: the largest payout is 54.6% of all 7-point payout

First-lane structure:
- firstLane=1: 204 races, ROI 97.81%, profit -10,060 JPY
- firstLane!=1: 19 races, ROI 17.35%, profit -31,820 JPY

This non-1 sample is too small for production gating but is a strong prospective hypothesis.

Expected-ROI text recorded by the live decision:
- estimated >=140%: 115 races, realized ROI 107.8%
- estimated >=160%: 75 races, realized ROI 117.2%
- estimated >=200%: 26 races, realized ROI 176.1%

These thresholds are post-hoc on the same sample. They must not be promoted without a new prospective window.

## Continuity issue

The backup was exported on 2026-10-10, but prediction records end on 2026-10-08. No prediction records exist for 2026-10-06, 2026-10-09, or 2026-10-10.

This may be due to device/app runtime conditions, but it means the tracker is not yet proven to capture every calendar day unattended.

## Root cause found for incomplete audit BUYs

Current code allowed an unsettled `value-v1` record to be written before the final near-close background evaluation. The background tracker then returned immediately when it saw any existing `value-v1` or `legacy-final-v1` record, even when the record had no durable live-odds audit snapshot.

That can permanently preserve a BUY with:
- combinations and stakes
- result/payout later settled
- but no fetch time/source/120-count/pick odds

## Fix on main

Patch commits:
- `1e30226e5caa4395f5d8a112758a24ce34d4ce6f` — allow near-close tracking to re-evaluate any unsettled provisional record; only settled records are immutable.
- `ddd89cfc66c43a060eb2adda0c7bf534de0f6a9e` — regression tests for unsettled value-v1, legacy, settled, and missing records.

Validation workflow:
- Run `38060290553` — Build and verify BOAT AI APK.

## Decision

Do **not** tune the production purchase threshold or promote a new model from this sample yet.

Immediate priority:
1. validate the audit-overwrite fix,
2. release/update,
3. accumulate enough newly audited BUYs to reach the pre-registered 360 threshold,
4. evaluate a fresh prospective window separately from this already-inspected sample,
5. then decide whether point-count, first-lane, or expected-ROI gates should change.

The current evidence says the live strategy is materially better than the old retrospective ~80% range, but it is **not yet proven profitable**.
