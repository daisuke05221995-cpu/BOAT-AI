# BOAT AI v0.18.11 — Purchase Rationale / Bet Label Handoff

Date: 2026-10-11

## Release
- versionName: 0.18.11
- versionCode: 57
- release target: `dd898c4dace6d2063a942906381cbbdb14ba22be`
- Debug validation Run: `38106368995` SUCCESS
- Signed Release Run: `38106369003` SUCCESS
- GitHub Release ID: `409358399`
- APK: `BOAT-AI-v0.18.11.apk`
- APK SHA-256: `2b95f372937600925016fdf0a020189566656a380dbaab19f60965c2653054af`

## Bet label rule

User-facing labels are standardized:
- `本命`: first-ranked selected pick when odds are <= 100.0x
- `対抗`: other selected picks when odds are <= 100.0x
- `穴`: odds > 100.0x and <= 200.0x
- `大穴`: odds > 200.0x

This corresponds to 100-yen gross payout:
- 穴: over 10,000 yen through 20,000 yen
- 大穴: over 20,000 yen

Boundary behavior is tested:
- 100.0x remains 本命/対抗
- 100.1x is 穴
- 200.0x is 穴
- 200.1x is 大穴

## Purchase rationale display

Each current live pick can now carry:
- `aiProbability`
- `expectedReturnRate`

For current Model A live recommendations:
- AI probability = Model A trifecta probability for the combination
- expected return rate = `aiProbability × liveOdds × 100`

The race-detail prediction UI now shows, per pick:
- label + combination + recommended stake
- AI probability
- live odds
- estimated expected return rate
- allocation reason
- estimated gross payout if hit

Example layout:
- 本命 1-2-3 1,800円
- AI確率 12.4% / オッズ 9.8倍 / 推定期待値 122%
- 主力配分
- 的中時想定払戻 17,640円

## Allocation explanation rule

Within one race:
- maximum stake = `主力配分`
- stake >= 50% of maximum but below maximum = `厚め配分`
- stake < 50% of maximum = `抑え配分`

Example for 1,800 / 900 / 200 / 100:
- 1,800 = 主力配分
- 900 = 厚め配分
- 200 = 抑え配分
- 100 = 抑え配分

This describes the generated stake concentration; it does not replace the underlying expected-log-utility allocation algorithm.

## Pending purchase persistence

Pending purchase tickets now preserve, when available:
- odds
- 本命/対抗/穴/大穴 tier
- AI probability
- expected return rate

Legacy pending tickets without these optional fields still load.

The pending purchase card shows the same rationale before launching the official betting surface.

## Tests

Added/extended:
- `BetLabelRuleTest`
- `PickExplanationRuleTest`
- `PendingPurchaseTicketTest`

CI:
- Unit tests SUCCESS
- Android lint SUCCESS
- Debug APK SUCCESS
- signed Release APK SUCCESS
- APK signature verification SUCCESS
- GitHub Release publication SUCCESS

## Research boundary

No Model A probability model, BUY/SKIP threshold, live-money frozen audit rule, 360-BUY formal gate, or expected-log-utility stake optimizer was changed by this UI/explanation release.

## Work
- Workへの指示: なし
