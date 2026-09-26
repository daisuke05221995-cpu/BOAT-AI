# BOAT AI v0.16.5 Audited Live Performance Handoff

Date: 2026-09-26

## Release

- Version: `v0.16.5`
- versionCode: `40`
- Release target commit: `a401530f1e697c0ae86adac95dcc5b320cdf4ce1`
- Build Run: `36238671361` — SUCCESS
- Signed Release Run: `36238671351` — SUCCESS
- Release ID: `397209702`
- APK: `BOAT-AI-v0.16.5.apk`
- APK size: `13,678,970` bytes
- APK SHA-256: `ca070f254f7a13ca423ac7ebe352dec1f604077a34e0079cf0345332121f1e46`

## Implemented after v0.16.4

A strict live-audit performance filter was added so real live BUY records are never mixed with retrospective/final-like-odds simulation results.

`LiveAuditedPerformance` accepts a record only when all of the following are true:

- result is settled
- `evaluationEligible=true`
- recommendation is BUY
- `strategyId=value-v1`
- a positive live fetch timestamp exists
- live odds source is recorded
- at least 120 positive official trifecta odds were fetched
- selected combinations are non-empty
- stake allocation exists for every selected combination and each stake is a valid 100-yen unit
- live odds exist for every selected combination and are positive finite values

The Profit screen now has a separate **ライブ監査済みAI購入推奨** card that shows only these records:

- hits / races
- stake
- payout
- profit
- ROI
- audited BUY count / all live BUY count
- audit completeness percentage
- count of live BUY records excluded because audit evidence was incomplete

The card explicitly states that these records are separate from historical retrospective virtual results.

## Tests and validation

- Strict live-audit filter tests added in `LiveAuditedPerformanceTest`.
- Complete record accepted.
- Missing timestamp/source, 119-way odds, missing selected-pick odds, invalid/mismatched stakes, wrong strategy, SKIP, unsettled, and non-evaluation records rejected.
- Audit coverage counting test added.
- Filter/test build Run `36238459254`: SUCCESS.
- UI one-shot validation Run `36238486804`: SUCCESS (`testDebugUnitTest`, `lintDebug`, `assembleDebug`).
- v0.16.5 Build Run `36238671361`: SUCCESS.
- v0.16.5 signed Release Run `36238671351`: SUCCESS, including release tests/lint/build, signing validation, APK signature verification, and GitHub Release publication.

## Important interpretation

The new live card is not a performance guarantee. It is a clean accounting series for only the BUY decisions that have durable evidence of the live official odds observed by the app during the purchasable period. Historical retrospective results remain a separate diagnostic series.

## Real-device verification still required

1. Install `v0.16.5` over the existing app. Do **not** uninstall or clear app data.
2. Allow real live races to produce `value-v1` BUY/SKIP records with complete official odds snapshots.
3. After results settle, confirm the Profit screen live-audited card increases only for complete live BUY records.
4. Confirm incomplete/legacy/retrospective records never enter the live-audited totals.
5. Compare the Result-screen live odds audit line with the Profit-screen aggregated record count.

## Next development step

Continue live reliability work around audit completeness and persistence across app/background lifecycle. In particular, verify that a newer pre-close snapshot can safely replace an unsettled record while preserving the original record creation time, and surface any live BUY that failed the 120-way/source/pick-odds audit so the cause can be diagnosed instead of silently disappearing from the live performance series.
