# Overnight BOAT AI checkpoint — 2026-09-25 02:00 JST

## State verified
- main at start: `3f106bf8ceab76177cc1e93d452152f53476ac71`.
- Flexible retrospective allocator source is broadened to **4–8 points** with higher conditional coverage targets for 2nd/3rd-place patterns.
- Previous generated 30-day feed is still the older 3–8 point output: 4,333 races, ROI 80.13%, average 4.56 points, average stake 1,423 yen.
- Build Run `36016932548` for the broader coverage source change completed SUCCESS.
- Automatic BUY remains OFF. Retrospective odds are post-race allocation inputs only; no pre-close odds claim is made.

## Important finding
The source was broadened after the last feed generation, so `data/model_a_recent_virtual_summary.json` is stale relative to `scripts/v016_recent_virtual_v2.py`. The next v016 recent-virtual run must regenerate the feed before any ROI/point-distribution conclusion is accepted.

## Safety / correctness
- Forecast probabilities remain market-free.
- Race result is not used for bet selection.
- Stake allocation remains 1,000–3,000 yen in 100-yen units.
- Do not promote automatic BUY until auditable pre-close odds exist.

## Next action
1. Trigger/observe `v016-recent-virtual.yml` regeneration from current main.
2. Compare new 4–8 point distribution, hit rate, ROI, and stake distribution against the stale 80.13% feed.
3. Only keep the broader policy if it improves useful coverage without unacceptable ROI degradation.
4. Continue user-facing Results/Profit usability work after the regenerated feed is internally consistent.
