# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`
安定公開版: `v0.15.1`

## Work上限・停止時の最重要ルール

Workの使用上限、タイムアウト、コンテキスト不足などで継続できなくなりそうな場合は黙って終了しない。
終了前に必ず有効な変更をcommit/pushし、このファイルへ現在位置・Run ID・次の具体的1手を保存する。
その後ユーザーへ通常チャットへ戻るよう案内する。

復帰案内:
> Workの上限に近づいたためGitHubへ状態を保存しました。通常チャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて」と送ってください。

## v0.15.1 公開完了

- versionCode: 19
- versionName: 0.15.1
- Release commit: `cca585662acdb2a977b56b716ec218a33d0baf1d`
- Release Run: `35849568130`
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.1`
- APK: `BOAT-AI-v0.15.1.apk`
- APK SHA-256: `14150eac19a1ae1265e7740fa79ca532254a3b2955727abcde9837a6828927aa`

Release WorkflowでUnit test / lint / signed APK / signature verify / GitHub Release公開まで成功。

## v0.15.1 購入推奨アラート

別アプリへロジックをコピーせず、まずBOAT AI本体へ実装して予想性能の完全互換を優先。

- 全国全レースを対象
- 当日レースを毎朝6:30 JSTに自動登録
- 各レースの締切約5分前にバックグラウンドで再評価
- その時点の開催/出走/展示/進入/気象データを再取得
- BOAT AI本体と同じ `PredictionEngine` / `LearningStore` / `PerformanceMemoryStore` を利用
- 同じ購入推奨/見送り条件を利用
- 公式BOAT RACE 3連単オッズを直前に再取得
- `BetStrategy.oddsRecommended()` を画面側最終オッズ判定と通知側で共有
- AI条件＋オッズ条件の両方を通過したレースだけ高優先度通知
- 通知に買い目、現在オッズ、推奨金額、判定理由を表示
- 通知から公式オッズページへ移動可能
- 見送りレースはレース通知しない
- 自動投票はしない。最終購入はユーザー判断
- 端末再起動/アプリ更新後はAlarmManager経由で当日スケジュールを復旧
- Android 12以降は正確な5分前実行のため「アラームとリマインダー」特別アクセスをUIから許可可能
- Android 13以降は通知権限が必要

主な実装:
- `NotificationScheduler.kt`
- `BoatAlertBootRecoveryReceiver.kt`
- `NotificationSettingsCard.kt`
- `AndroidManifest.xml`
- `BetStrategy.oddsRecommended()`
- `BetStrategyTest` に画面/通知オッズ判定のparity test追加

設定場所: 損益タブ下部の「購入推奨アラート」。

## 本番予想ロジック

v0.15.1も研究用Value Strategy / race-softmaxは本番へ入れていない。
`app/src/main/assets/value_strategy_model.json` は存在せず、現行安定ロジックを使用。

主な不採用研究結果:
- v12: 2026 ROI117.3%だが、2023 72.0% / 2024 45.5% / 2025 56.3%
- rich race-softmax Run `35839229134`: 2024 ROI90.1%、2025固定ROI59.2%

2025-10-01〜2025-12-31 Q4最終holdoutは未開封。

## 次の具体的1手

1. 実機をv0.15.1へ更新
2. 損益タブ下部で「購入推奨アラート」をON
3. Android 13+は通知を許可
4. 「5分前通知を正確にする」が表示された場合はアラームとリマインダーを許可
5. 実開催で通知時刻・買い目・オッズ・公式ページ導線を確認
6. 実機不具合があればv0.15.2で修正
7. 将来別APK化する場合は同一予想コアを共有/生成する構成にして性能差を発生させない

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
