# BOAT AI 引継ぎメモ

更新日: 2026-09-24

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: **v0.16.0**
- versionCode: **35** / versionName: **0.16.0**
- Release target commit: `ef87c862a79bce0fbb68e5399798b215e5914ae7`
- Final pre-version Debug gate Run: `36006480052` SUCCESS
- v0.16.0 Build Run: `36006839510` SUCCESS
- Signed Release Run: `36006839426` SUCCESS
- Release ID: `395728675`
- Published: `2026-09-24T13:38:22Z`
- Release asset: `BOAT-AI-v0.16.0.apk` (13,662,586 bytes)
- APK SHA-256: `78da792f0f577a67ed0c8610f08fbc61c4fc838f9d418e2c79618b7de83e5a10`
- 復旧モード / `CrashRecoveryStore` は維持。ユーザーデータ削除・アンインストールは禁止。

## Android v0.16.0

市場非入力のforecast-only **Model A** を本番予想へ統合。

- 3段 conditional grouped-softmax LightGBM、temperature 1.0。
- 予想はオッズを入力に使わない。
- 120通り3連単確率から上位4点を表示。
- Android起動時に固定Model Aとcompact player-history assetをロード。
- 履歴assetは2026-09-23まで構築済み。以降は前日分までを日次catch-upし、同日結果を予想へ混入させない。
- 履歴が欠損・不完全・古い場合はfail-closedし、安定したv0.15.16純AIforecastへフォールバック。
- 手動購入導線は利用可能。
- **自動BUY推奨はOFFのまま。**

## Model A検証

固定Model A:
- train through 2025-05-31。
- validation / early stopping / temperature through 2025-06-30。
- Model Run `35940833546` / Artifact `10784912368`。
- model artifact digest `sha256:58b845fa8d07efe258b08a23ac6caafab2e4854ce4b84618fb4af6ae3f3687fe`。

### 2025年9月 独立holdout

Run `35993900879` SUCCESS、3,956レース、coverage 99.9242%。

Model A vs v0.15.16純AI:
- 1着Top1 55.308% vs 44.085%。
- 1着Top2 75.126% vs 66.785%。
- 3連単Top4 27.856% vs 18.579%。
- Top8 43.453% vs 30.713%。
- LogLoss 3.844202 vs 4.225358。
- Brier 0.963136 vs 0.978731。
- LogLoss差95% CI `[-0.404683,-0.357090]`。
- Decision: `PASS_FORECAST_HOLDOUT`。

### 2025年10〜12月 Q4 final holdout

Q4初回アクセス前にProtocol commit `3a56378244dd1f3621f862ac89cea3db8ccea6af` を固定。
Final Run `36004272796` SUCCESS。

同一11,896レース、coverage 99.9412%、同日結果リーク0、重複0。

Model A vs v0.15.16純AI:
- 1着Top1 **57.8093% vs 46.1500%**。
- 1着Top2 **76.5467% vs 67.6278%**。
- 3連単Top1 **10.6254% vs 5.9011%**。
- Top4 **30.6153% vs 19.3763%**。
- Top8 **46.7384% vs 31.9519%**。
- LogLoss **3.761125 vs 4.181624**。
- Brier **0.957727 vs 0.976797**。
- Paired day-block LogLoss差95% CI **[-0.440041,-0.402842]**。
- Decision: **`PASS_Q4_FINAL_FORECAST`**。
- 10月・11月・12月すべて月別でもModel Aが主要予想指標を改善。

## Android parity / 性能

Dedicated parity Run `36001980730` SUCCESS。

- Python LightGBM 4.6.0 vs Kotlin raw score: 3,072 rowsで一致gate PASS。
- 実pre-race 64レース × 120通り確率chain parity PASS。
- player/course history parity PASS。
- compact history byte parity PASS。
- JVM smoke: model parse 167.988ms、history decode 76.181ms、1レースforecast median 6.212ms / P95 7.806ms。

## 本番履歴asset

Deployment Run `36005654248` SUCCESS / Artifact `10810058921`。

- history through: 2026-09-23。
- updateRaces: 141,542。
- registered players: 1,726。
- compact history: 4,222,646 bytes。
- history SHA-256: `a180aa722ad0520b5d86705bac742ff588309e72a49bed373eabf102f257acc3`。
- 2026履歴sourceはcommit固定し、docs/v2をfrozen r4 schemaへ正規化。
- モデル再学習なし、オッズ/払戻入力なし。

## 購入AI

本番昇格禁止を継続。

- 歴史オッズ監査: `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`。
- 締切前/T-5の取得時刻を証明できず、払戻/100とほぼ一致するため、過去ROIを実現可能な購入成績として扱わない。
- r1〜r4購入policy / OOF市場差候補は不採用。
- v0.16.0のModel A合格は**予想品質のみ**で、購入ROI合格を意味しない。
- 自動BUYはOFF。新しい監査可能な締切前オッズ基盤ができるまで再開しない。

## Release検証

Release target `ef87c862a79bce0fbb68e5399798b215e5914ae7`。

- Final pre-version gate `36006480052`: live API schema / Unit test / lint / Debug APK / artifact upload 全SUCCESS。
- v0.16.0 Build `36006839510`: 同工程 全SUCCESS。
- Signed Release `36006839426`: release test / lint / signed APK / signature verify / GitHub Release publish 全SUCCESS。

## 次の作業

1. v0.16.0実機で上書き更新し、当日Model A予想表示・手動購入・結果・損益・アプリ内更新を確認する。
2. 実運用forecast結果を蓄積し、予測精度・欠損fallback・履歴catch-up失敗を監視する。
3. 購入AIは、取得時刻を監査可能な締切前オッズデータ基盤を新設してから別研究として再開する。
4. Model Aを9月/Q4結果へ合わせて再学習・temperature変更・救済調整しない。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`data/v016_q4_forecast_decision.json`、`data/v016_release_readiness.md`、最新main、最新Actions、v0.16.0 Releaseを確認する。
