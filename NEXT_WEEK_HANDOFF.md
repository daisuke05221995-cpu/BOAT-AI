# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-24

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.16` / versionCode 34
- Release target: `11338ffc426662f60e02803bf5ceb333bb048f61`
- Debug Run `35974408635`: SUCCESS
- Signed Release Run `35974408547`: SUCCESS
- APK: `BOAT-AI-v0.15.16.apk`
- APK SHA-256: `642fb50c605364a7c84f87b7dcd31419fe8aed6eff42613699c506e7d1cd5a98`

## Android v0.15.16

- 純AI着順予想は有効。
- 自動BUY推奨は停止中。
- 予想順はオッズを使わない。
- 上位4点表示と手動購入導線は利用可能。
- v0.15.15購入診断がBUY率99.5%、ROI68.5%で不合格だったため購入と予想を分離した。

## 購入AI

現時点で本番昇格しない。

- r1〜r4購入policy不採用。
- OOF市場差候補もREJECT。
- 歴史オッズ監査: `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`。
- レース別締切前取得時刻を証明できず、払戻/100とほぼ一致するため、このアーカイブによるROI昇格を停止。
- 自動BUYはOFF継続。

## forecast-only Model A

市場入力なしModel Aは2025年9月独立holdoutで **PASS_FORECAST_HOLDOUT**。

固定候補:
- 3段 conditional grouped-softmax LightGBM。
- train through 2025-05-31。
- validation/temperature through 2025-06-30。
- temperature 1.0。
- Run `35940833546` / Artifact `10784912368`。

9月Protocol commit: `2fbf3239f8ac68e4d45775b353aa03217d9a517f`。
Holdout Run: `35993900879` SUCCESS。

同一3,956レース:
- Model A logloss 3.844202 / baseline 4.225358。
- Brier 0.963136 / 0.978731。
- 1着Top1 55.308% / 44.085%。
- 1着Top2 75.126% / 66.785%。
- 3連単Top1 8.948% / 5.789%。
- Top4 27.856% / 18.579%。
- Top8 43.453% / 30.713%。
- coverage 99.9242%。
- 同日結果リーク0、重複0。

30日block bootstrap 95% CI:
- logloss差 `[-0.404683,-0.357090]`。
- Brier差 `[-0.017337,-0.013903]`。

Model Aはforecast品質で独立holdoutを通過したが、まだ `productionPromotion=false`。

## Android統合準備

通常チャット側で開始済み。

- `LightGbmTextModel.kt` prototype追加。
- numeric/non-linear LightGBM v4 treeのthreshold、default missing、leaf走査をKotlinで評価。
- Python LightGBMとのraw score parity確認を進行中。
- 初回prototype Build `35993666586` はUnit test期待値の誤り1件でFAIL。推論器自体の分岐ではなくテスト期待値を修正済み。
- 修正commit `aa2caab3813017b1a603841c5c893eac45549a2f`。Build Run `35995595338` を確認する。
- まだ `PredictionEngine` へModel Aを接続しない。

次のgate:
1. Unit test/lint/Debug build全SUCCESS。
2. 実Model A 3段の大量sample Python parity。
3. 120通り確率chainと周辺確率の一致。
4. 約46.9MB history stateのAndroid運用設計と日次更新。
5. 同日結果混入防止。
6. 端末速度/メモリ/起動時間。
7. すべて合格後のみv0.16 forecast統合・Release判断。

## 封印

**2025年10〜12月Q4は未取得・未開封。**

9月を見た後のModel A再学習、temperature変更、特徴量追加、救済調整は禁止。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、`data/v016_sept_forecast_decision.json`、`data/v016_forecast_candidate.json`、最新main、最新/進行中Actionsを確認する。
