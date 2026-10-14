# BOAT AI — USER-APPROVED EARLY FORMAL LIVE EVALUATION

Date: 2026-10-14
Private backup evaluated locally only. Raw backup is NOT committed.

## Evaluation status

The pre-registered protocol target is 360 fully audited value-v1 BUY races.
The user explicitly approved an early formal operational decision before that target.

This backup contains:
- appVersion: 0.18.14
- exportedAt: 2026-10-14T06:16:40.013259Z
- settled/evaluationEligible/recommended/value-v1 BUY candidates: 577
- fully audited BUYs: 343
- protocol target progress: 343/360 = 95.28%
- remaining to original pre-registered threshold: 17

This report is therefore:
- a USER-APPROVED EARLY FORMAL OPERATIONAL EVALUATION;
- NOT a claim that the original 360-BUY pre-registered threshold was satisfied.

Frozen cohort/audit/accounting semantics were not changed.

## Primary result — 343 fully audited BUYs

- races: 343
- hits: 101
- hit rate: 29.45%
- stake: 764,700 JPY
- payout: 593,480 JPY
- profit: -171,220 JPY
- ROI: 77.61%
- max drawdown: 205,260 JPY
- active JST race dates: 15
- date range: 2026-09-27 through 2026-10-14

Operational verdict:
**FAIL as evidence of a profitable live-money strategy.**

The data does not support claiming current value-v1 has positive live expected value.

A race-level bootstrap sensitivity check (20,000 resamples; descriptive, not part of the frozen protocol) produced:
- ROI 95% interval approximately 55.8% to 101.5%
- hit-rate 95% interval approximately 24.8% to 34.1%
- only about 3.2% of resamples exceeded 100% ROI

This does not replace the frozen protocol, but reinforces that the observed deficit is material rather than a tiny accounting difference.

## Exact continuity with the prior 223-race baseline

Legacy/unversioned audited rows reproduce the previous formal baseline exactly:

| Cohort | BUYs | Hits | Hit rate | Stake | Payout | Profit | ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| legacy/unversioned | 223 | 74 | 33.18% | 497,800 | 455,920 | -41,880 | 91.59% |
| newly versioned evidence | 120 | 27 | 22.50% | 266,900 | 137,560 | -129,340 | 51.54% |
| all audited | 343 | 101 | 29.45% | 764,700 | 593,480 | -171,220 | 77.61% |

The 120 newly versioned BUYs span 2026-10-11 through 2026-10-14.
Their max drawdown is 144,380 JPY.

Therefore the decline from the old 223-race baseline is not caused by recomputing old rows differently. It comes from the newly accumulated live evidence.

## Audit completeness

All 234 incomplete BUY candidates are legacy/unversioned rows and miss the same evidence:
- liveOddsFetchedAt
- liveOddsSource
- liveOddsCount
- livePickOdds

Versioned evidence:

| sourceAppVersion | candidates | audited | completeness |
| --- | ---: | ---: | ---: |
| 0.18.8 | 3 | 3 | 100% |
| 0.18.9 | 7 | 7 | 100% |
| 0.18.11 | 106 | 106 | 100% |
| 0.18.14 | 4 | 4 | 100% |
| post-version total | 120 | 120 | 100% |

This is a strong operational improvement: audit evidence loss has effectively disappeared in the observed post-version BUY cohort.

## Per-version money metrics

| version | BUYs | hits | hit rate | stake | payout | profit | ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| legacy/unversioned | 223 | 74 | 33.18% | 497,800 | 455,920 | -41,880 | 91.59% |
| 0.18.8 | 3 | 2 | 66.67% | 7,200 | 5,560 | -1,640 | 77.22% |
| 0.18.9 | 7 | 1 | 14.29% | 11,300 | 1,200 | -10,100 | 10.62% |
| 0.18.11 | 106 | 23 | 21.70% | 236,400 | 117,220 | -119,180 | 49.59% |
| 0.18.14 | 4 | 1 | 25.00% | 12,000 | 13,580 | +1,580 | 113.17% |

Do NOT interpret v0.18.14 as profitable from four races.

All 343 audited BUYs in this backup use liveOddsSource = official PC.
The new cached-odds/start-time-estimate fallback therefore has no audited live-money sample yet in this evaluation.

## Period metrics, as-of 2026-10-14 JST

| period | BUYs | hit rate | stake | payout | profit | ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| today | 17 | 29.41% | 44,600 | 32,400 | -12,200 | 72.65% |
| 7d | 139 | 22.30% | 310,300 | 152,600 | -157,700 | 49.18% |
| October | 280 | 30.71% | 615,200 | 484,540 | -130,660 | 78.76% |
| all | 343 | 29.45% | 764,700 | 593,480 | -171,220 | 77.61% |

The recent deterioration is substantial.

## Point-count diagnostics — descriptive / post-hoc

| selected points | BUYs | hits | hit rate | stake | profit | ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 4 | 137 | 39 | 28.47% | 312,700 | -167,390 | 46.47% |
| 5 | 79 | 27 | 34.18% | 179,000 | +59,860 | 133.44% |
| 6 | 65 | 17 | 26.15% | 146,900 | -68,620 | 53.29% |
| 7 | 31 | 8 | 25.81% | 60,400 | -27,250 | 54.88% |
| 8 | 31 | 10 | 32.26% | 65,700 | +32,180 | 148.98% |

Combined 5- and 8-point rows:
- n=110
- hit rate=33.64%
- stake=244,700
- payout=336,740
- profit=+92,040
- ROI=137.61%

This is NOT a production rule.
The formal protocol requires at least 20 active days for slice promotion diagnostics; the entire audited dataset has only 15 active dates.
The pattern is nevertheless important for next-candidate research because 4/6/7-point rows are consistently poor, while 8-point rows remained positive in both the old and newly added periods.

Concentration warning:
- 5-point ROI falls from 133.44% to about 112.47% after removing its largest payout, and below 100% after removing its top three payouts.
- 8-point ROI falls from 148.98% to about 103.56% after removing its largest payout, and sharply below 100% after removing its top three payouts.

## First-lane diagnostic

| firstLane | BUYs | hit rate | profit | ROI |
| --- | ---: | ---: | ---: | ---: |
| 1 | 314 | 30.57% | -132,650 | 81.25% |
| not 1 | 29 | 17.24% | -38,570 | 32.69% |

The non-1 sample remains small and cannot be promoted into a new production gate from this same dataset.

## Estimated-return diagnostic

Recommendation text expected-return bands:

| estimated return | BUYs | hit rate | profit | realized ROI |
| --- | ---: | ---: | ---: | ---: |
| 105-119% | 50 | 26.00% | -52,070 | 22.28% |
| 120-139% | 107 | 35.51% | -56,140 | 72.21% |
| 140-159% | 70 | 28.57% | -7,000 | 95.79% |
| 160-199% | 68 | 25.00% | -66,030 | 64.67% |
| 200%+ | 48 | 27.08% | +10,020 | 107.03% |

Across individual audited BUY races, the Spearman correlation between displayed estimated-return percentage and realized race ROI is approximately -0.027 (essentially no monotonic relationship in this sample).

This is one of the strongest next-development signals: the live expected-return estimate is not currently calibrated well enough to function as a trustworthy profit ranking.

## Stake-allocation diagnostic

Current expected-log-utility stake allocation:
- ROI 77.61%

Same selections with same race budgets distributed approximately equally:
- ROI 75.64%

100 JPY on every selected combination:
- ROI 76.94%

Therefore stake weighting is not the primary source of the loss. Current weighting improves the result slightly. The larger issue is BUY selection / probability-value calibration.

## First-pick-only diagnostic

If only the first AI combination had been purchased:

| rule | hits | hit rate | stake | payout | profit | ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| first pick, original recommended amount | 27 | 7.87% | 262,700 | 183,890 | -78,810 | 70.00% |
| first pick, fixed 100 JPY | 27 | 7.87% | 34,300 | 25,900 | -8,400 | 75.51% |
| full race budget concentrated on first pick | 27 | 7.87% | 764,700 | 558,520 | -206,180 | 73.04% |

The data does not support switching to first-pick-only betting.

## Payout concentration

Largest single payout contribution: 40,920 JPY.

Sensitivity:
- remove largest payout: ROI 72.54%
- remove top 3 payouts: ROI 64.84%
- remove top 5 payouts: ROI 58.47%
- remove top 10 payouts: ROI 47.88%
- top 5 payouts are 26.11% of all payout

The overall result is not being rescued by one giant win; it is already negative and becomes materially worse when large wins are removed.

## Actual user purchases

The backup contains 12 settled BetRecord tickets across 2 actual purchased races:
- settled stake: 4,500 JPY
- settled payout: 0 JPY
- profit: -4,500 JPY
- ROI: 0%

This actual-purchase ledger remains separate from AI-live virtual accounting.

## Decision

### Current value-v1

**REJECT as a demonstrated profitable live-money strategy.**

Operational/audit infrastructure is now good enough to trust the post-version evidence, and that evidence is materially worse than the original 223-race result.

Do not attribute the loss primarily to stake allocation.
Do not attribute it to the new v0.18.14 cached-odds fallback either: no audited BUY in this export used that fallback source.

The next research target should be:
1. BUY gate / value calibration;
2. Model A probability calibration;
3. point-count behavior, especially repeated weakness in 4/6/7-point recommendations;
4. firstLane != 1 as a prospective hypothesis only;
5. expected-return calibration so displayed expected return ranks realized value monotonically.

Any new gate/threshold derived after viewing these 343 races must be treated as a NEW candidate and validated prospectively. Do not rewrite this 343-race ledger.

## Protocol integrity note

Original pre-registered minimum: 360 audited BUYs.
Observed here: 343.
User explicitly elected to make an early formal operational decision.
The report therefore preserves the fact that 17 BUYs remain to the original protocol gate rather than falsely claiming the 360 condition was met.
