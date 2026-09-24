# BOAT AI 引継ぎメモ

更新日: 2026-09-24

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.16`
- versionCode: 34 / versionName: 0.15.16
- Release target commit: `11338ffc426662f60e02803bf5ceb333bb048f61`
- Debug validation Run: `35974408635` SUCCESS
- Signed Release Run: `35974408547` SUCCESS
- Release asset: `BOAT-AI-v0.15.16.apk`
- APK SHA-256: `642fb50c605364a7c84f87b7dcd31419fe8aed6eff42613699c506e7d1cd5a98`
- 復旧モード / `CrashRecoveryStore` は維持。ユーザーデータ削除・アンインストールは禁止。

## Android v0.15.16

予想と購入判定を分離した安定版。

- 純AIの着順予想はON。
- 自動BUY推奨はOFF。
- 予想順位はオッズを入力に使わない。
- 現行は上位4点を表示し、手動購入導線は利用可能。
- v0.15.15購入ロジックの2025年7〜8月診断はBUY率99.5%、ROI68.5%で不合格だったため自動購入を停止。
- 過去ROIはv0.15.16 forecastには適用しない。
- 既存の結果・損益・購入記録・更新・復旧機能は維持。

## v0.16購入研究

購入AIは現時点で本番昇格禁止。

- r1〜r4の購入policyは不採用。
- OOF市場差研究もREJECT。
- 歴史3連単オッズ監査の最終判定: `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`。
- 使用アーカイブはレース別の取得時刻/T-5分を証明できず、払戻/100とほぼ一致するため、締切前に実現可能なROI検証値として扱わない。
- このオッズを使ったROI、期待値、BUY/SKIP条件による本番昇格は停止。
- 自動BUY推奨は引き続きOFF。

## v0.16 forecast-only Model A

市場入力なしのModel Aは予想モデルとして独立検証まで通過。

固定候補:
- 3段 conditional grouped-softmax LightGBM。
- train through: 2025-05-31。
- early stopping / temperature選択: 2025-06-30まで。
- temperature=1.0。
- 市場オッズ入力なし。
- Model Artifact: Run `35940833546` / Artifact `10784912368`。
- model digest: `sha256:58b845fa8d07efe258b08a23ac6caafab2e4854ce4b84618fb4af6ae3f3687fe`。

### 2025年7〜8月 development

同9,583レースで:
- Model A 1着Top1 56.09%、Top2 75.81%。
- 3連単Top1 9.72%、Top4 29.34%、Top8 45.42%。
- logloss 3.796223、Brier 0.960191。
- 現行v0.15.16純AIは1着Top1 45.33%、Top2 66.94%、3連単Top4 19.20%、Top8 32.95%。

### 2025年9月 forecast-only独立holdout

Protocol commit `2fbf3239f8ac68e4d45775b353aa03217d9a517f` を9月初回アクセス前に固定。
Run `35993900879` SUCCESS。

- source races 4,272。
- 一意な6艇結果 3,959。
- Model A必須入力欠損 3。
- 同一比較集合 3,956レース、coverage 99.9242%。
- 重複0、同日結果リーク0。

Model A vs v0.15.16純AI:
- 3連単logloss `3.844202 vs 4.225358`。
- Brier `0.963136 vs 0.978731`。
- 1着Top1 `55.308% vs 44.085%`。
- 1着Top2 `75.126% vs 66.785%`。
- 3連単Top1 `8.948% vs 5.789%`。
- Top2 `16.102% vs 10.617%`。
- Top4 `27.856% vs 18.579%`。
- Top8 `43.453% vs 30.713%`。
- Top-choice ECEはModel A 0.012950、baseline 0.002876でModel Aの方が悪い点を記録。

暦日30日を単位に2,000回paired block bootstrap:
- logloss差 Model A-baseline = -0.381156、95% CI `[-0.404683,-0.357090]`。
- Brier差 = -0.015595、95% CI `[-0.017337,-0.013903]`。

最終判定: **`PASS_FORECAST_HOLDOUT`**。
ただし `productionPromotion=false`。購入収益の合格を意味しない。

## Android Model A統合準備

- `LightGbmTextModel` のKotlin prototypeを追加。
- 実Model AのLightGBM v4 numeric/non-linear treeをAndroid側で再現するための最小パーサ/推論器。
- 実モデルの欠損分岐、threshold、leaf走査をLightGBM仕様に合わせる。
- 研究用確認ではPython LightGBM raw scoreとKotlin prototypeのサンプル出力が一致。
- まだ本番 `PredictionEngine` へModel Aを接続していない。
- モデルasset、履歴state、日次履歴更新、120通り確率chain、端末速度/メモリ、Python parityは今後の統合gate。
- 約46.9MBの研究用history stateをそのままasset採用するかは未決定。

## 封印範囲

**2025-10-01〜2025-12-31 Q4 final holdoutは未取得・未開封のまま維持。**

9月結果を見た後にModel Aの再学習、temperature変更、特徴量追加、係数救済をしない。

## 次の作業

1. Kotlin LightGBM prototypeのUnit test / lint / Debug buildを全SUCCESSにする。
2. Python固定Model AとAndroid側で、同一feature rowsのraw scoreを大量sampleでparity検証する。
3. 3段conditional softmaxと120通り3連単確率をAndroid側に実装し、確率和=1とPython予測一致を確認する。
4. player/course履歴stateと日次更新方式をAndroid向けに設計する。同日結果は当日全予想後にまとめて反映する。
5. 端末メモリ/推論速度/起動時間を計測する。
6. parity・性能・欠損処理が合格した後にのみ、v0.16 forecastとしてProduction統合/Releaseを判断する。
7. 自動BUYはOFFのまま。締切前時刻が監査可能なオッズ基盤ができるまで購入AI昇格を再開しない。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、`data/v016_sept_forecast_decision.json`、`data/v016_forecast_candidate.json`、最新main、進行中Actionsを確認する。
