# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`
安定公開版: `v0.15.3`

## Work上限・停止時の最重要ルール

Workの使用上限、タイムアウト、コンテキスト不足などで継続できなくなりそうな場合は黙って終了しない。
終了前に必ず有効な変更をcommit/pushし、このファイルへ現在位置・Run ID・次の具体的1手を保存する。
その後ユーザーへ通常チャットへ戻るよう案内する。

復帰案内:
> Workの上限に近づいたためGitHubへ状態を保存しました。通常チャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて」と送ってください。

## 並行開発ルール

通常チャットとWorkを並行利用してよい。ただし同じ本番ファイルを同時編集しない。

### 通常チャット担当
- Android本体
- UI / 通知 / 履歴 / 結果 / 損益
- 本番ロジックへの最終統合
- Release判定と公開
- `app/`、`PROJECT_STATUS.md`、Release関連を優先管理

### Work担当
- v0.16予想モデル研究専用
- 原則として `scripts/v016_*`、`.github/workflows/v016-*`、`data/v016_*` の新規ファイル中心
- Android本番ファイル、versionCode/versionName、Release workflow、`app/src/main/assets/value_strategy_model.json` を勝手に変更しない
- 研究結果は本番へ自動昇格しない
- Run ID、採否、次作業をこのファイルへ残す

### GitHub Actions担当
- 年別・モデル別・パラメータ群の重い計算をmatrixで並列実行
- 2023 / 2024 / 2025など独立可能な年は並列化する
- 同じcacheを使う探索はArtifact再利用で再計算を避ける

## v0.16予想モデル方針

最終目的は実運用で利益を保証することではなく、過去検証上で十分な再現性を持つ候補だけを本番候補にすること。

### 年間リリースゲート
- 月単位のマイナスは許容
- 最終評価では12か月合計ROI 105%以上を必須
- 年間購入件数が少なすぎる候補は不可
- 単発の異常高配当だけで成績が成立していないかを別指標で監視するが、高配当そのものは排除しない
- 候補を完全固定するまで最終holdoutを開かない
- 最終holdoutを含む年次評価でROI 105%未満なら不採用

### 2系統で作る
1. `CORE BUY`：現在進行中の低〜中配当寄り・期待値重視。まずこちらを最後まで走り切りBaselineとして固定する。
2. `LONGSHOT BUY`：CORE固定後に開始。従来SKIPだったうち「荒れそうで見送った」レースを対象に、穴狙い6〜12点程度まで許容する。

最終的には `CORE BUY / LONGSHOT BUY / SKIP` の3分類を目標とする。
LONGSHOTでは人気薄を無条件に買わず、展示変化、進入ズレ、1号艇信頼度低下、モーター差、風波、オッズ歪み等から荒れレースを抽出する。
COREとLONGSHOTは別々の成績も保存し、最後に合算年間ROIも評価する。

## v0.15.3 公開完了

- versionCode: 21
- versionName: 0.15.3
- Release commit: `446b7e3005a18b592d88d2726cc9abb3dd3c8d95`
- Release Run: `35863168523` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.3`
- APK: `BOAT-AI-v0.15.3.apk`
- APK SHA-256: `ea8992abdf28b45a919e99940381165c10845e4b28d5051a83ecc6ab4c3771bf`

Release WorkflowでUnit test / lint / signed APK / signature verify / GitHub Release公開まで成功。
Debug検証 Run `35862849909` もSUCCESS。

## v0.15.3 重要修正

ユーザー実機で結果タブの「事前予想」が多数 `記録なし` だった原因は、v0.15.2の5分前保存が購入推奨アラートONに依存していたこと。

v0.15.3で予想履歴保存とユーザー通知を分離した。

- `PredictionTrackingScheduler.kt` 追加
- 全レース事前予想トラッカーは通知ON/OFFと無関係に常時予約
- 毎朝6:25 JST、アプリ起動時、端末再起動/アプリ更新後に追跡復旧
- 締切前に同じPredictionEngine / BetStrategy / LearningStoreで予想
- BUY/SKIP両方の買い目をPredictionHistoryへ保存
- 結果約20分後に自動settle
- 自動記録サービスの通知は無音・無振動・低優先度
- BUYユーザー通知だけは従来どおり「購入推奨アラート」ON/OFFに従う
- 既存アラート側が先に `legacy-final-v1` / `value-v1` を保存していれば追跡側は重複評価を避ける

過去の未保存レースを結果後に後付け生成しない。2026-09-23の桐生等の `記録なし` は履歴の正確性のため残す。

## v0.15.2から継続する表示

- レース詳細AI購入判断直下の結果カード
- 結果 / 払戻 / 事前予想 / 的中・ハズレ / 想定払戻
- 損益の日別カードで全予想（BUY+SKIP）を先頭表示
- 購入推奨だけの仮想成績も別表示
- `締切前保存 X / 当日結果 Y` で保存漏れ可視化

## 本番予想ロジック

研究用Value Strategy / race-softmaxは本番へ入れていない。
`app/src/main/assets/value_strategy_model.json` は存在せず現行安定ロジックを使用。

不採用研究:
- v12: 2026 ROI117.3%だが2023 72.0% / 2024 45.5% / 2025 56.3%
- rich race-softmax Run `35839229134`: 2024 ROI90.1%、2025固定59.2%

2025-10-01〜2025-12-31 Q4最終holdoutは未開封。

## 次の具体的1手

1. CORE BUY側の研究を年間ROI105%ゲート前提で完走させる
2. COREをBaselineとして固定する
3. その後LONGSHOT BUY研究を別系統で開始する
4. CORE / LONGSHOT / 合算の年次成績を別々に検証する
5. 候補固定後だけ最終holdoutを一度開く
6. 実機v0.15.3では翌開催日の事前予想自動保存も確認する

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
