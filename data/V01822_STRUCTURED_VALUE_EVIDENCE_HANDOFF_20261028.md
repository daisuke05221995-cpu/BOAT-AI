# v0.18.22: Structured pre-race value evidence (2026-10-28)

## Why

Private Android backup diagnostics revealed a large gap between the AI's
textual expected ROI and realized simulated ROI under the prospective policy.
The display text is rounded and not a structured probability snapshot, so it
cannot support formal model calibration.

This document contains aggregate figures only. Never commit the private backup,
individual predictions, proprietary account records, or its exact raw ledger.

## Added in v0.18.22

- For BUY recommendations with consistent selected picks, stakes and live odds,
  save `livePickAiProbabilities` in the exact order of `combinations`.
- Save `liveExpectedRoiPercent` calculated as
  `100 * sum(pickProbability * liveOdds * stake) / sum(stakes)`.
- Save `decisionCapturedAt` separately from the original `createdAt` and
  pre-existing `liveOddsFetchedAt`. SKIP records can have the decision
  timestamp but no selected-pick probabilities.
- A numeric snapshot is omitted, not fabricated, if any prerequisite is absent
  or invalid. The legacy backup format remains backwards-compatible.
- The research-only ROI diagnostic validates numerical snapshots and reports
  selected-pick predicted/observed hit rates and predicted/realized ROI.

## Explicit constraints

1. No change to Model A, BUY/SKIP gates, selected combinations, or stakes.
2. No retroactive filling of historical records from outcome or display text.
3. No use of the previously sealed 2025-10 to 2025-12 Q4 holdout.
4. The original frozen 343-BUY comparison remains unchanged.
5. A retrospective slice or same-sample odds/ROI threshold is not sufficient
   to promote a new live purchase strategy.
6. Selected-pick probability mass is **not** a full 120-way forecast
   calibration. Evaluate only forward evidence from this instrumented release.

## Next research step after enough forward BUY decisions

Compare saved selected-pick model probability mass with actual selected-pick
hit frequency, and stake-weighted expected return with realized return.
Pre-register any proposed calibration transform before forward testing, and
retain a separate untouched evaluation period. Do not optimize on this first
instrumented sample.
