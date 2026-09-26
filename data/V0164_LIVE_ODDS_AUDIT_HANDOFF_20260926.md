# BOAT AI v0.16.4 Live Odds Audit Handoff

Date: 2026-09-26

## Release

- Version: `v0.16.4`
- versionCode: `39`
- Release target commit: `17386012674a1b9599b22cb3b0f0eda973c4596f`
- Build Run: `36238128370` — SUCCESS
- Signed Release Run: `36238128333` — release publication and APK signature verification SUCCESS
- GitHub Release ID: `397207054`
- APK: `BOAT-AI-v0.16.4.apk`
- APK size: `13,678,970` bytes
- APK SHA-256: `28458d842de798dfd2132f4c92fa62db8d45204132687c703bc508f315613f64`

## Implemented

Production live BUY/SKIP decisions now persist an auditable odds snapshot into `PredictionRecord`:

- official-odds fetch timestamp (`liveOddsFetchedAt`)
- successful source (`liveOddsSource`)
- number of positive odds entries (`liveOddsCount`)
- odds for the combinations that were actually selected (`livePickOdds`)

`BoatRaceRepository` records each successful odds fetch in `LiveOddsAuditRegistry`, and `PredictionHistoryStore` transfers the newest snapshot into the durable pre-race prediction record. The original `createdAt` is preserved when a newer pre-close snapshot replaces an unsettled record.

A `value-v1` SKIP is persisted as an actual SKIP with zero stake and no fabricated legacy combinations. It is no longer represented by old four-point fallback picks.

The result screen now shows, when available:

- `AI見送り` and its reason for an empty-combination SKIP
- live decision time in JST
- odds source
- retrieved odds count
- selected-combination odds

The bulk-selection explanation was also updated to match the current v0.16.x behavior: market-free Model A forecast plus a separate current-official-odds decision layer; no external automatic wagering execution.

## Verification completed

- one-shot persistence patch Run `36237664831`: SUCCESS
- full build after persistence commit Run `36237784390`: SUCCESS
- UI patch Run `36237958852`: SUCCESS (`testDebugUnitTest`, `lintDebug`, `assembleDebug`)
- v0.16.4 Build Run `36238128370`: SUCCESS (live API schema, unit tests, lint, Debug APK, upload)
- v0.16.4 signed release: release unit tests/lint/build, signing-secret validation, APK signature verification, and GitHub Release publication succeeded

Temporary one-shot patch workflows/helpers used to apply the large source edits were removed from main before the v0.16.4 release.

## Real-device/live-race verification still required

1. Install `v0.16.4` over the existing app. Do **not** uninstall or clear app data.
2. On a purchasable race after exhibition/entry data is ready, confirm the full official trifecta market is fetched and BUY/SKIP is produced.
3. After the race settles, open Results and confirm the live decision line contains time/source/count and the actual selected-combination odds for BUY records.
4. Confirm a newer live snapshot before cutoff can replace the unsettled record without changing the original record creation time.
5. Confirm value-strategy SKIP results show `AI見送り` instead of legacy/fabricated picks.

## Next development step

Accumulate and aggregate **live audited BUY decisions only** as a separate performance series. Do not mix these results with retrospective/final-like odds ROI. Add coverage for audit completeness (timestamp/source/120-way count/pick odds), live hit rate, stake, payout, profit and ROI only from records that prove a real pre-close live snapshot.
