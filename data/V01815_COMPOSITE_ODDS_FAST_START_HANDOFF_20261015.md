# BOAT AI v0.18.15 — Composite Odds Gate / Fast Repeat Startup

Date: 2026-10-15

## Release

- versionName: 0.18.15
- versionCode: 61
- release target: `1d1e8a8bb58605e2e423aee55ddda037d936ce59`
- Debug validation Run: `38696267139` SUCCESS
- Signed Release Run: `38696267380` SUCCESS
- GitHub Release ID: `413509305`
- APK: `BOAT-AI-v0.18.15.apk`
- APK SHA-256: `7e64ae53a2e6985a7af85bb95ee56272b4ad0b2423b26dcf70f361954a3f1615`

## Production BUY change

A new post-formal-evaluation purchase gate is active.

Composite odds:
`1 / sum(1 / selectedOdds)`

Rule:
- composite odds <= 3.00x: SKIP
- composite odds > 3.00x: may continue through the existing expected-log-utility / expected-return BUY logic

Exactly 3.00x is SKIP.

The gate is evaluated after Model A selects the candidate combinations and before stake allocation is accepted.

BUY/SKIP reason text now includes composite odds.

## Historical rationale — post-hoc only

Applying the gate retrospectively to the frozen 343-audited-BUY dataset:

| cohort | races | hits | hit rate | stake | payout | profit | ROI |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| all frozen audited BUYs | 343 | 101 | 29.45% | 764,700 | 593,480 | -171,220 | 77.61% |
| composite odds > 3.00x | 173 | 46 | 26.59% | 433,400 | 438,080 | +4,680 | 101.08% |
| composite odds <= 3.00x | 170 | 55 | 32.35% | 331,300 | 155,400 | -175,900 | 46.91% |

This is NOT prospective proof because the threshold was chosen after inspecting the 343-race dataset.

The 343-race formal ledger remains frozen and is not rewritten.
v0.18.15+ must be evaluated prospectively and separated by `sourceAppVersion`.

## Fast repeat startup

Goal:
- first launch of a JST day may perform the full fetch;
- second and later launches on the same day should show usable data quickly.

Implementation:
1. Successful program/date JSON is persisted under app-private `daily-program-cache`.
2. On startup, a same-day cached race list is parsed and shown first.
3. Current-version saved Model A BUY/SKIP decisions are restored immediately from PredictionHistoryStore.
4. Only records whose `sourceAppVersion == BuildConfig.VERSION_NAME` are restored into the live Model A decision cache.
5. After the instant display, a full network refresh runs in the background.
6. Background refresh forcibly re-evaluates purchasable races so restored odds/decisions do not remain stale.
7. Manual Refresh also forces the live value refresh.
8. Old-version decisions are never restored into the current Model A cache.

Therefore:
- app-open latency is decoupled from full network/result/odds refresh after the first successful load;
- cached values are not treated as permanently current;
- v0.18.14 BUY decisions cannot bypass the new v0.18.15 composite-odds gate.

## Tests / CI

Added tests:
- composite odds formula boundary
- exactly 3.00x -> SKIP
- above 3.00x can proceed to BUY when the existing value logic also passes

CI:
- live race API schema SUCCESS
- unit tests SUCCESS
- Android lint SUCCESS
- Debug APK SUCCESS
- signed Release build SUCCESS
- APK signature verification SUCCESS
- GitHub Release publication SUCCESS

## Evidence policy

The user explicitly chose this rule after the 343-BUY early formal evaluation.

Therefore v0.18.15 is a NEW prospective operating regime.
Do not claim the retrospective 101.08% is expected future ROI.
Report v0.18.15+ separately from the frozen 343-race ledger.

## Work

Workへの指示: なし
