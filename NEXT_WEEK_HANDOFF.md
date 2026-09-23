# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-23

## 最初に確認

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 安定公開版: `v0.14.1`
- `PROJECT_STATUS.md`
- `NEXT_WEEK_HANDOFF.md`
- `data/strategy_search_2026.json`
- `data/multiyear_validation.json`（独立検証完了後に生成）
- 独立検証Run: **35809928215**

## 2026 v12 開発結果

v11で7月ROIが27.9%まで崩れたため、月次設定の急変を防ぐv12ガードを実装。

ガード条件:
- 新設定の過去期間合計ROIが現行設定より最低+5pt改善
- 最悪月ROIの悪化が3pt以内
- 購入サンプル数60%以上維持
- プラス月数を減らさない

2026年5〜9月:
- 5月 ROI 144.7% / +325,680円
- 6月 ROI 94.7% / -30,840円
- 7月 ROI 108.5% / +51,060円
- 8月 ROI 104.2% / +24,600円
- 9月 ROI 132.7% / +128,280円
- 合計 2,407購入レース
- 投資 2,888,400円
- 払戻 3,387,180円
- 損益 +498,780円
- ROI 117.3%
- プラス月 4/5
- 最悪月ROI 94.7%
- `historicalCriteriaMet=true`
- `qualifiedForRelease=false`
- `releaseDeferredForIndependentValidation=true`

2026は繰り返し開発へ使用済みなので、これ単独ではReleaseしない。

## 独立複数年検証

対象: **2023 / 2024 / 2025**。
2022は使用中のv3過去オッズアーカイブが同形式で取得できないため、オッズ付き独立検証から除外。

最初は公開JSONで前年学習スナップショットを作ろうとしたが、2021〜2022が404だったため中止。
現在は、既に5年学習で実績がある**BOAT RACE公式Kファイル**から漏洩のない前年末スナップショットを生成する方式へ変更済み。

現行Run: **35809928215**

Workflow構成:
1. Kファイル学習パーツを4ジョブ並列生成
   - 2021-09-22〜2021-12-31
   - 2022-01-01〜2022-12-31
   - 2023-01-01〜2023-12-31
   - 2024-01-01〜2024-12-31
2. 2023検証は2022-12-31までの学習パーツだけを合成
3. 2024検証は2023-12-31までだけを合成
4. 2025検証は2024-12-31までだけを合成
5. 各対象年1〜9月をwalk-forward処理
6. 月次モデルは対象月より前の結果だけで学習
7. 5〜9月の設定はその月より前の月だけで決定
8. v12ガード閾値は固定。2023〜2025の結果に合わせて変更しない
9. 3年結果を `data/multiyear_validation.json` へ自動集約・commit

関連:
- `scripts/validate_multiyear_strategy.py`
- `scripts/merge_validation_learning.py`
- `.github/workflows/multiyear-validation.yml`

このメモ更新時点で2021学習パートはSUCCESS。2022/2023/2024は生成中。

## 独立検証の厳格条件

**2023・2024・2025の各年が全て**以下を満たす必要がある:
- 5〜9月合計 ROI >= 105%
- 5か月中4か月以上プラス
- 最悪月 ROI >= 90%
- 各月50購入レース以上
- 年合計500購入レース以上

さらに2026 v12 `historicalCriteriaMet=true` が必要。
全部通った場合だけ `releaseCandidate=true`。
途中で条件を緩めない。

## Exporter安全ロック

`scripts/export_value_strategy_model.py` を更新済み。
Android用モデル生成には必ず `--validation data/multiyear_validation.json` が必要。
以下を全て要求する:
- strategy schema >= 12
- 2026 `historicalCriteriaMet=true`
- validationYears == [2023, 2024, 2025]
- 3年すべて `historicalCriteriaMet=true`
- `independentValidationPassed=true`
- `releaseCandidate=true`

したがって、独立検証が不合格ならAndroid用モデルは生成できない。

## Android側の現状と重要な未接続箇所

`ValueStrategyModel.kt` 自体は実装済みで、120通り確率・市場確率とのblend・EV判定・1〜10点・資金配分に対応。
ただしasset `value_strategy_model.json` はまだ未生成で、本番フローも未接続。

現行 `BoatViewModel` / `PredictionHistoryStore` / `BetStore` は旧 `PredictionEngine` を直接使用している。
具体的に:
- 選択レースのオッズ取得は旧買い目数点のみ
- 一括購入推奨判定は旧 `PredictionEngine.isRecommended`
- 一括購入買い目は `BetStore.addRacePicks()` 内で旧予想を再計算
- 予想履歴も旧予想/旧BUY-SKIPを保存

よってRelease前に必ず統一する:
1. 公式3連単オッズを120通り取得
2. `ValueStrategyModel` でBUY/SKIPと買い目を確定
3. 予想一覧・個別・一括選択・一括購入・個別購入・予想履歴を同じ確定結果へ統一
4. BUY/SKIP履歴は展示＋公式オッズ取得後に固定
5. 購入記録で予想を再計算せず、確定した買い目を渡す
6. PythonバックテストとAndroid計算のparity test
7. 120通り、EV条件、点数上限、1200円配分、見送りのUnit test
8. Debug/Release Unit test・lint・APK・署名確認

中途半端に一部画面だけ新モデルへ変更した状態では公開しない。

## Release工程

独立3年検証が全部合格した場合のみ:
1. `data/multiyear_validation.json` の `releaseCandidate=true` 確認
2. Android統合を完成
3. `value_strategy_model.json` を安全Exporterで生成
4. Python/Android parity test
5. `app/build.gradle.kts`: versionCode 18 / versionName 0.15.0
6. Build APK成功
7. signed Release APK・署名検証成功
8. GitHub Release `v0.15.0`
9. アプリ内自動更新確認
10. `PROJECT_STATUS.md` 最終更新

## 再開指示

`GitHubの daisuke05221995-cpu/BOAT-AI、PROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、独立複数年検証Run 35809928215 を確認して、妥協せず続きから進めて。`
