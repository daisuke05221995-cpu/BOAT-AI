# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

このファイルは、ChatGPT WorkでBOAT AI開発を継続する際の**中断対策とチャット復帰ルール**です。
Workは作業開始時と、上限・タイムアウト・ツール停止などで継続不能になりそうな時に必ず確認・更新してください。

## 作業開始時に必ず確認

1. Repository: `daisuke05221995-cpu/BOAT-AI`
2. Branch: `main`
3. `PROJECT_STATUS.md`
4. `NEXT_WEEK_HANDOFF.md`
5. `WORK_HANDOFF.md`
6. 最新コミット
7. 進行中のGitHub Actions
8. `data/strategy_search_2026.json`
9. `data/multiyear_validation.json` が存在すれば必ず確認

## Workでの基本ルール

- ユーザーへ細かい確認を繰り返さず、既存方針に沿って完成まで進める。
- ただし独立検証の合格条件は勝手に緩めない。
- `releaseCandidate=true` にならない限り、新Value Strategyを正式Releaseしない。
- GitHub Actions失敗時はログを確認し、原因を直して再実行する。
- 中途半端な実装をReleaseしない。
- 作業中は重要な節目ごとにcommitを残す。
- 長時間作業になる場合でも、次回再開可能な状態を常に保つ。

## 上限・停止・タイムアウト対策（最重要）

Workが以下のどれかに近づいたら、**作業を黙って終了しないこと**。

- Workの使用上限
- 5時間などの実行時間上限
- コンテキスト上限
- ツール利用上限
- GitHub Actions待ちで残り時間が少ない
- 何らかの理由でこのまま完成まで続行できない

その場合は、終了前に必ず次を実行する。

1. 途中の有効な変更をGitHubへcommit/pushする。
2. `PROJECT_STATUS.md` に現在位置を追記する。
3. この `WORK_HANDOFF.md` の「現在の作業地点」を更新する。
4. 進行中ActionsのRun ID、status、失敗なら失敗step/job IDを残す。
5. 次に実行すべき**具体的な1手**を書く。
6. ユーザーへ次の趣旨を明示する。

> Workの上限に近づいたため、続きが消えないようGitHubへ状態を保存しました。通常のチャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して続けて」と送ってください。

Work自身が別チャットへ自動移動できない場合でも、**必ずユーザーへ通常チャットに戻るよう指示すること**。

## 通常チャットへ戻った側のルール

ユーザーが通常チャットへ戻り、

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して続けて`

と送った場合、チャット側は以下を行う。

1. 上記3ファイルと最新commitを確認。
2. `WORK_HANDOFF.md` に記載されたRun IDのGitHub Actions状態を確認。
3. 完了済み作業をやり直さず、次の1手から再開。
4. 失敗Runならログ確認→修正→再実行。
5. Workへ戻す必要がある大規模作業になったら、再びこのファイルへ最新状態を残して引き継ぐ。

## 現在の作業地点

安定公開版: `v0.14.1`
次期候補: `v0.15.0`（まだ未Release）

### 独立複数年検証

最新方式では、2023〜2025の予測用入力を公開JSONへ依存せず、**BOAT RACE公式B/Kファイルから再構成**するよう変更済み。

主な変更:
- `scripts/backfill_historical.py`
  - 過去年Kファイルから選手別ST合計/件数を保存。
- `scripts/merge_validation_learning.py`
  - 選手別ST履歴を前年末スナップショットへマージ。
- `scripts/build_kfile_validation_records.py`
  - 公式Bファイルから全国勝率・当地勝率・モーター2連率・ボート2連率を取得。
  - Kファイルから展示タイム・確定結果を取得。
  - 平均STは過去確定レースのみから計算。
  - 対象レース自身の実進入・実ST・結果時風波は予測特徴へ入れない。
- `scripts/validate_multiyear_strategy.py`
  - 公式B/K方式へ切替。
- `.github/workflows/multiyear-validation.yml`
  - B/K依存をインストールして2023/2024/2025を並列独立検証。

現在確認すべき独立検証Run:
- **35814229078**

### Android Value Strategy統合

以下まで実装済み:
- `PredictionEngine`
  - Value StrategyのSKIP時に旧4点予想へ自動フォールバックしない。
  - 明示的な手動購入時だけ `manualOverridePicks()` を利用可能。
- `PredictionHistoryStore`
  - Value Strategyは公式オッズ判定後だけ履歴保存。
  - BUYは確定買い目を保存。
  - SKIPは仮想投資0円で判定だけ保存。
- `BetStore`
  - `addResolvedRacePicks()` を追加し、購入時の再予想を避ける。
- `BoatViewModel`
  - `value_strategy_model.json` が存在するときだけValue Strategyを有効化。
  - 展示済み・購入可能レースについて120通り公式オッズを順次取得し、BUY/SKIPを自動確定。
  - 個別画面、一括選択、一括購入、履歴を同じ確定結果へ寄せる。
  - AI SKIPをユーザーが手動購入する場合だけ旧候補を明示的に使用。

現在確認すべきAndroid Build Run:
- **35814862551**

### 次に実行する具体的な1手

1. Run `35814862551` のBuild結果確認。
   - 失敗なら該当job/stepログを確認してAndroid統合を修正。
2. Run `35814229078` の独立複数年検証結果確認。
   - 失敗ならK/Bパーサまたはcoverage判定をログから修正。
   - 成功なら `data/multiyear_validation.json` を確認。
3. `releaseCandidate=true` の場合のみ、Exporter→asset生成→Parity Test→Unit Test→versionCode 18 / versionName 0.15.0→Release APK→署名確認→GitHub Releaseへ進む。
4. `releaseCandidate=false` の場合はReleaseせず、結果を分析して次の改善へ進む。厳格条件は緩めない。

## ユーザーへ渡す復帰文

通常チャットへ戻るときは、次の一文だけで再開できる状態を維持する。

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
