# v0.16.x flexible retrospective Android handoff — 2026-09-25

Latest implementation before checkpoint: `767dda17c3fbd48eb20a01d6ecaabf5992fa49a7`.

- Flexible feed: schema v2, `model-a-retro-flex-v2`, 4–8 points, 1,000–3,000 yen, 100-yen units.
- Automatic BUY OFF. Forecast market inputs=false, resultUsedForSelection=false, post-race odds allocation only; no realizable pre-close ROI claim.
- Feed Run `36074256945` SUCCESS; Build `36074256955` SUCCESS.
- Android commit `881ec280...` Build Run `36074929360` failed only on stale strategy-ID unit test. Fixed in `176b896c...`.
- Repository parser now validates flexible safety invariants and parses overall/per-point summary.
- BoatUiState exposes retrospective window and summary.
- Profit UI now states flexible semantics and displays 4/5/6/7/8-point 30-day diagnostics.

Current 30-day data through 2026-09-24: 4,189 races, 1,389 hits, ROI 82.80%, profit -1,084,540 yen. 4pt ROI 78.50%; 5pt 93.49%; 6pt 90.99%; 7pt 61.01%; 8pt 83.24%. Diagnostic only; never outcome-select point count.

Next: inspect/fix Build triggered by latest UI commit until tests/lint/APK all SUCCESS; do not release until gates pass.
