# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-23

## 最初に確認

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 安定公開版: `v0.14.1`
- `PROJECT_STATUS.md`
- `NEXT_WEEK_HANDOFF.md`
- `WORK_HANDOFF.md` ← Work/通常チャット間の中断復帰ルールと最新作業地点
- `data/strategy_search_2026.json`
- `data/multiyear_validation.json`（独立検証完了後に生成）

## Work利用時の中断ルール

Workで作業を続ける場合、上限・タイムアウト・コンテキスト不足・ツール制限などで完成まで継続できなくなりそうなら、黙って終了しない。
必ず `WORK_HANDOFF.md` のルールに従い、GitHubへ途中状態を保存し、Run ID・現在位置・次の具体的な1手を記録したうえで、ユーザーへ通常チャットへ戻るよう案内する。

通常チャットへ戻す際の文:

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`

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

現在は、既に5年学習で実績がある**BOAT RACE公式B/Kファイル**から漏洩のない前年末スナップショットと対象年の予測用特徴を再構成する方式へ変更済み。

最新のRun IDと作業状態は `WORK_HANDOFF.md` を優先して確認すること。

Workflow構成:
1. Kファイル学習パーツを4ジョブ並列生成
   - 2021-09-22〜2021-12-31
   - 2022-01-01〜2022-12-31
   - 2023-01-01〜2023-12-31
   - 2024-01-01〜2024-12-31
2. 2023検証は2022-12-31までの学習パーツだけを合成
3. 2024検証は2023-12-31までだけを合成
4. 2025検証は2024-12-31までだけを合成
5. 対象年の事前情報はBファイルから全国/当地勝率・モーター/ボート率を取得
6. Kファイルの展示タイムと結果を利用し、実進入・実ST・結果時風波は同レース予測へ入れない
7. 平均STは前年末まで＋対象年の過去確定レースのみから更新
8. 各対象年1〜9月をwalk-forward処理
9. 月次モデルは対象月より前の結果だけで学習
10. 5〜9月の設定はその月より前の月だけで決定
11. v12ガード閾値は固定。2023〜2025の結果に合わせて変更しない
12. 3年結果を `data/multiyear_validation.json` へ自動集約・commit

関連:
- `scripts/build_kfile_validation_records.py`
- `scripts/validate_multiyear_strategy.py`
- `scripts/merge_validation_learning.py`
- `.github/workflows/multiyear-validation.yml`

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

## Android側の現状

`ValueStrategyModel.kt` は実装済みで、120通り確率・市場確率とのblend・EV判定・1〜10点・資金配分に対応。
asset `value_strategy_model.json` はまだ未生成なので、安定版ではValue Strategyは有効化されない。

Android統合は進行中。最新の実装状況・Build Runは `WORK_HANDOFF.md` を優先して確認すること。

Release前に必ず満たす:
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

`GitHubの daisuke05221995-cpu/BOAT-AI、PROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.md を確認して、進行中Runも確認して、妥協せず続きから進めて。`
