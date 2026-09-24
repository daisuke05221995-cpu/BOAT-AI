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
- synthetic unit testの期待値ミスを2段階で修正。推論器本体の分岐ロジック変更ではない。
- 最終修正commit `533f426e82365ab731f5ca089af048ad21b4f956`。
- prototype検証Run `35995823959`: live API schema / Unit test / Android lint / Debug APK build / artifact upload **全SUCCESS**。
- 研究用の実Model A確認ではPython LightGBM raw scoreとKotlin prototypeのsample出力が一致しているが、実モデル大量sampleのCI parity testはまだ未実装。
- まだ `PredictionEngine` へModel Aを接続しない。

次のgate:
1. 実Model A 3段の大量sample Python/Kotlin raw-score parityをCIで固定する。
2. 3段conditional softmaxと120通り確率chainをAndroid側に実装し、確率和=1・1着周辺確率和=1・Python予測一致を確認する。
3. 約46.9MBの研究用history stateをAndroid向けにどう保持/圧縮するか決め、player/course履歴と30/60/90/180日窓を再現する。
4. 当日全レースの予想snapshot生成後にのみ当日結果をまとめて履歴へ反映し、同日結果混入を防ぐ。
5. 端末速度/メモリ/起動時間を計測する。
6. parity・性能・欠損処理が合格した後にのみv0.16 forecast統合・Release判断。
7. 自動BUYはOFFのまま。締切前時刻が監査可能なオッズ基盤ができるまで購入AI昇格を再開しない。

## 封印

**2025年10〜12月Q4は未取得・未開封。**

9月を見た後のModel A再学習、temperature変更、特徴量追加、救済調整は禁止。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、`data/v016_sept_forecast_decision.json`、`data/v016_forecast_candidate.json`、最新main、最新/進行中Actionsを確認する。
