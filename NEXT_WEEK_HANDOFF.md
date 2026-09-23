# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-23

## 最初に確認する場所

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 安定公開版: `v0.14.1`
- `PROJECT_STATUS.md`
- `NEXT_WEEK_HANDOFF.md`（このファイル）
- `data/strategy_search_2026.json`
- `data/multiyear_validation.json`（独立検証完了後に生成）

## 2026開発結果: v12

v11の月次パラメータ切替が7月に過度に絞り込まれ、ROI 27.9%まで崩れたため、v12で設定変更ガードを追加した。

ガード:
- 過去期間の合計ROIが現行設定より最低+5pt改善
- 最悪月ROIの悪化が3pt以内
- 購入サンプル数を60%以上維持
- プラス月数を減らさない

v12 2026年5〜9月:
- 5月: ROI 144.7%, +325,680円
- 6月: ROI 94.7%, -30,840円
- 7月: ROI 108.5%, +51,060円
- 8月: ROI 104.2%, +24,600円
- 9月: ROI 132.7%, +128,280円
- 合計: 2,407購入レース / 投資2,888,400円 / 払戻3,387,180円 / +498,780円 / ROI 117.3%
- プラス月: 4/5
- 最悪月ROI: 94.7%
- `historicalCriteriaMet=true`
- `qualifiedForRelease=false`
- `releaseDeferredForIndependentValidation=true`

2026は繰り返し研究に使用済みのため、これだけでReleaseしない。

## v12関連ファイル

- `scripts/search_2026_strategy_v12.py`
- `.github/workflows/strategy-search.yml`
- `data/strategy_search_2026.json`
- `scripts/export_value_strategy_model.py`

Exporterには独立検証完了前のモデル生成を拒否する安全ロックを入れてある。

## 独立複数年検証

2023・2024・2025を独立検証に使用する。
2022は使用しているv3過去オッズアーカイブで同形式データを確認できなかったため、現時点の独立オッズ検証から除外。

重要:
- 2026用のpre-2026学習スナップショットを過去年へ流用しない（未来データ混入防止）
- 各対象年ごとに `2021-09-22〜前年12/31` の学習スナップショットを新規生成
- 対象年1〜9月のレースをwalk-forward処理
- 月次モデルは対象月より前の対象年データだけで学習
- 5〜9月の設定はその月より前の月だけで決める
- v12のガード閾値は固定し、2023〜2025の結果に合わせて変更しない

新規ファイル:
- `scripts/validate_multiyear_strategy.py`
- `.github/workflows/multiyear-validation.yml`

初回独立検証Run:
- GitHub Actions Run ID: `35809515870`
- 2023/2024/2025を3ジョブ並列で実行
- 各年の前年末学習スナップショット生成から開始
- 最後に `data/multiyear_validation.json` を自動生成・commitする

## 独立検証の厳格合格条件

2023・2024・2025の各年が全て以下を満たすこと:
- 5〜9月合計 ROI >= 105%
- 5か月中4か月以上がプラス
- 最悪月ROI >= 90%
- 各月50購入レース以上
- 合計500購入レース以上

さらに2026 v12の `historicalCriteriaMet=true` も必要。

3年全部を通過した場合のみ `releaseCandidate=true` とする。
条件は途中で緩めない。

## Android側の現状

Work側で `ValueStrategyModel.kt` は追加済み。
ただし現行 `BoatViewModel` はまだ旧 `PredictionEngine.withOdds()` を使っており、新モデルは本番フローへ未接続。

重要なRelease前残作業:
1. `ValueStrategyModel` を公式オッズ取得後の本番予想へ接続
2. 新モデルでは120通りの3連単オッズが必要なので、公式オッズ取得を全120通りへ対応させる
3. 予想一覧 / 個別レース / 購入推奨 / 見送り / 一括購入 / 予想履歴保存が同じ判定ロジックを使うよう統一
4. PythonバックテストとAndroid `ValueStrategyModel` の計算一致をテスト
5. 120通りオッズ取得、期待値フィルタ、最大点数、1200円配分、見送りのUnit testを追加
6. Debug/Release Unit test・lint・APKビルド・署名確認

中途半端に「選択画面だけ新モデル、一覧や履歴は旧モデル」という状態では公開しない。

## Release工程

独立検証とAndroid統合テストが通った場合のみ:
1. `data/multiyear_validation.json` の `releaseCandidate=true` を確認
2. Exporterの独立検証ロックを、検証JSON確認方式へ変更
3. Android用 `value_strategy_model.json` を生成してassetsへ追加
4. Android/Python parity test
5. `app/build.gradle.kts` を `versionCode=18`, `versionName="0.15.0"` へ更新
6. Build APK workflow成功確認
7. Release workflowで署名済みAPK生成
8. GitHub Release `v0.15.0` 公開
9. アプリ内自動更新確認
10. `PROJECT_STATUS.md` 更新

## 再開時の指示

新しいチャット/Workでは:

`GitHubの daisuke05221995-cpu/BOAT-AI、PROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、独立複数年検証Run 35809515870 を確認して、妥協せず続きから進めて。`

と依頼すればよい。
