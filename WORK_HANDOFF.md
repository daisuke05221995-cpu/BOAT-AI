# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

このファイルは、ChatGPT Workと通常チャットを往復してもBOAT AI開発を同じ位置から再開するためのチェックポイントです。

## 作業開始時に必ず確認

1. Repository: `daisuke05221995-cpu/BOAT-AI`
2. Branch: `main`
3. `PROJECT_STATUS.md`
4. `NEXT_WEEK_HANDOFF.md`
5. `WORK_HANDOFF.md`
6. 最新commit
7. 進行中GitHub Actions
8. `data/strategy_search_2026.json`
9. `data/multiyear_validation.json` が存在すれば必ず確認

## Workでの基本ルール

- ユーザーへ細かい確認を繰り返さず、既存方針に沿って完成まで進める。
- 独立検証の合格条件は勝手に緩めない。
- `releaseCandidate=true` にならない限り新Value Strategyを正式Releaseしない。
- GitHub Actions失敗時はログを確認し、原因を直して再実行する。
- 中途半端な実装をReleaseしない。
- 長時間作業でも重要な節目ごとにcommitし、次回再開可能な状態を保つ。

## 上限・停止・タイムアウト対策（最重要）

Workの使用上限、時間上限、コンテキスト上限、ツール制限などで完成まで継続できなくなりそうな場合は、黙って終了しない。

終了前に必ず:
1. 有効な変更をGitHubへcommit/push。
2. `PROJECT_STATUS.md` とこのファイルへ現在位置を保存。
3. 進行中Run ID、status、失敗ならjob/stepを保存。
4. 次に実行すべき具体的な1手を保存。
5. ユーザーへ通常チャットへ戻るよう案内。

復帰案内:
> Workの上限に近づいたため、続きが消えないようGitHubへ状態を保存しました。通常のチャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて」と送ってください。

## 現在の作業地点

安定公開版: `v0.14.1`
次期候補: `v0.15.0`（未Release）

### 2026 v12

2026年5〜9月の開発結果:
- ROI 117.3%
- 損益 +498,780円
- 2,407購入推奨レース
- プラス月 4/5
- 最悪月ROI 94.7%
- `historicalCriteriaMet=true`
- 2026は繰り返し開発へ使ったため、これ単独ではReleaseしない。

本番候補 `nextLiveConfig`:
- alpha 0.25
- minEv 1.05
- minProbability 0.005
- maxOdds 150.0
- maxPoints 2
- allocationMode equal
- budget 1200

### 独立複数年検証（最優先）

現行Run: **35817304411**
head commit: `acca55854ce44ea4dcc61e69f4eeb7a2f30081cf`

最新確認時:
- learning-parts 2021: SUCCESS
- learning-parts 2022: SUCCESS
- learning-parts 2023: SUCCESS
- learning-parts 2024: IN_PROGRESS
- 2023/2024/2025 validateは2024 learning完了待ち

直前Run `35814229078` の失敗原因は戦略成績ではなく、公式Bファイルの事前指標coverageが4.81%しか取れないパース不具合だった。
原因: 歴史Bファイルは1ファイルに複数会場（`21BBGN`, `20BBGN`, ...）が連結されるのに、旧実装が1ファイル1会場と仮定していた。

修正済み `scripts/build_kfile_validation_records.py`:
- Bファイル会場ヘッダを行単位で追跡。
- 会場ごとの1〜12Rへ正しく紐付け。
- 選手行の固定スペース依存を廃止し、級別後の数値から全国/当地勝率・motor/boat 2連率を抽出。
- Kファイルの対象レース実ST/実進入/結果時風波は同レース予測に使わない。
- 平均STは前年まで＋前日までのK結果から再構成。

厳格Release条件は2023/2024/2025の各年すべて:
- 5〜9月 ROI >= 105%
- 4/5月以上プラス
- 最悪月 ROI >= 90%
- 各月50購入以上
- 年500購入以上
さらに2026 `historicalCriteriaMet=true`。
基準は緩めない。

### Android側

Value Strategy統合済み:
- 公式3連単120通り取得
- Value StrategyでBUY/SKIP確定
- SKIP時に旧4点へ自動フォールバックしない
- 個別/一括/履歴が同じ確定買い目を使用
- 購入時に再予想しない
- SKIP履歴は仮想投資0円
- 手動でSKIPを買う場合のみ明示的なmanual override
- BUY/SKIP、120通り、最大10点、1200円配分、Python parity、判定凍結/復元Unit testあり

最新Android Build:
- Run **35817872634**: SUCCESS
- Unit tests / lint / Debug APKすべてSUCCESS

### 月別バックテスト表示

v0.15用に旧4点バックテスト表示からv12戦略表示へ修正済み。
- `HistoricalBacktestRepository.kt`: `data/strategy_search_2026.json` を読む。
- `HistoricalBacktestCard.kt`: 過去3連単オッズ込みv12を表示。
- 1〜4月は学習・校正期間として成績を作らない。
- 5〜9月を運用検証として表示。
- 2026だけではRelease判定しない旨を明示。
- この変更込みBuild Run `35817872634` SUCCESS。

### 昇格・Release安全ロック

`promote-value-model.yml` と `export_value_strategy_model.py` は以下を全要求:
- validationYears == [2023, 2024, 2025]
- 3年すべて strict criteria pass
- `independentValidationPassed=true`
- `releaseCandidate=true`
- 2026 criteria pass

合格すると `app/src/main/assets/value_strategy_model.json` を生成・commit。
不合格ならassetは生成しない。

Release Workflowは `app/build.gradle.kts` 更新で起動。
現在:
- versionCode 17
- versionName 0.14.1

独立検証＋asset昇格＋最終Build成功後だけ:
- versionCode 18
- versionName 0.15.0
へ変更し、signed Release APK、署名検証、GitHub Releaseへ進む。

## 次の具体的な1手

1. **Run 35817304411** を確認。
2. 2024 learning完了後、2023/2024/2025 validate結果を確認。
3. パーサ/coverageの技術エラーならログを見て修正し再実行。
4. 成績結果まで成功したら `data/multiyear_validation.json` を確認。
5. `releaseCandidate=true` なら Promote Workflow → asset生成 → Android Build/Parity確認 → versionCode18/versionName0.15.0 → Release。
6. `releaseCandidate=false` なら基準を下げずReleaseしない。3年結果は一度見た時点で完全未使用holdoutではなくなるため、その事実を保持して次の改善を設計する。

## 通常チャット復帰文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
