# BOAT AI 引継ぎメモ

更新日: 2026-09-24

## 現在の状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.8`
- Android package: `jp.boatai.app`
- versionCode: `26`
- versionName: `0.15.8`
- Release target commit: `b1a8f8752cbd7b9af88edfa84975a0ec041ff65b`
- Release workflow Run: `35881038684` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.8`
- APK: `BOAT-AI-v0.15.8.apk`
- APK SHA-256: `a0d10f2aca01ba623489fd067cb105453a7568deed050bb45c7947ae5c8c4830`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.8/BOAT-AI-v0.15.8.apk`

## v0.15.8 主修正: 設定分離 / 戻る操作 / 完全無振動化

ユーザー実機と公式BOAT RACEアプリのUIを参考に、日常操作と設定を分離し、Androidの戻る操作と通知振動を修正した。

### 設定画面を独立

- 画面右上に歯車アイコンの `設定` ボタンを追加
- `SettingsScreen.kt` を新設
- 設定画面へ以下を集約
  - 通知・自動記録
  - Exact Alarm状態 / 設定
  - データ・バックアップ
  - アプリバージョン
- 損益タブにあった `通知・バックアップ設定` の折りたたみを削除
- `予想 / 購入 / 結果 / 損益` は日常操作だけに集中させる

### Android戻るキー

`BackHandler` を追加し、端末の戻る操作を画面階層に合わせた。

- 設定 → 元画面
- レース詳細 → 競艇場一覧
- 競艇場一覧 → 予想ホーム
- 購入 / 結果 / 損益 → 予想ホーム
- 予想ホーム → 戻るキーを消費し、誤操作でアプリを終了しない

### 通知の振動対策

Androidは一度作成したNotification Channelの音・振動設定を保持するため、以前のチャンネル設定が残り、コードを無音化しても振動する端末があった。

v0.15.8では既存チャンネルを再利用せず、表示専用の新チャンネルIDへ切り替えた。

- 通常通知: `boat_ai_events_visual_v3`
- 購入推奨: `boat_ai_buy_alerts_visual_v3`
- 購入推奨バックグラウンド判定: `boat_ai_alert_checks_visual_v3`
- 事前予想トラッカー: `boat_ai_prediction_tracking_visual_v2`

各Channelで `setSound(null, null)` / `enableVibration(false)` を設定し、Notification Builder側でも `setDefaults(0)` / `setVibrate(longArrayOf(0L))` / `setSilent(true)` を指定した。
購入推奨だけでなく、foreground service通知と事前予想トラッカーも同様に無振動化した。

### 深夜CI安定化

0時直後はBOAT RACE Open APIの当日JSONがまだ公開されていないことがあり、正常なアプリ変更でも `Verify live race API schema` が誤失敗していた。

`build-apk.yml` を変更し、当日データが未公開の場合は直近3日まで順番に確認するようにした。これにより深夜のビルド検証がAPI公開タイミングだけで止まりにくくなった。

### v0.15.8 検証

UX修正後 Debug検証 Run `35880611845`: **SUCCESS**
- Live race API schema
- Unit test
- Android lint
- Debug APK build
- APK artifact upload

Signed Release Run `35881038684`: **SUCCESS**
- version確認
- signing secrets確認
- 署名鍵復元
- Unit test / Android lint / signed Release APK build
- APK署名検証
- GitHub Release公開
- APK / SHA256資産アップロード

## v0.15.7から継続: 4タブ + コンパクトUI

下部ナビゲーション:

`予想 / 購入 / 結果 / 損益`

- 購入待ち・購入履歴・結果待ち・確定損益は購入タブへ集約
- 結果は競艇場単位で折りたたみ
- 損益は `今日 / 7日 / 月 / 全期間` で切替
- 実購入損益を最優先表示
- AI分析・検証は必要時だけ展開
- v0.15.8で設定類は損益から完全分離

## v0.15.6から継続: 実購入の公式投票ハンドオフ

`複数レース選択 → 選択分を一括投票へ → 買い目/金額を固定保存 → 公式シンプル投票サイト → BOAT AIへ戻る → 実際に投票したレースだけ一括確定 → 実損益へ反映`

- ブラウザ移動中も `PendingPurchaseSession` を保持
- 投票前に買い目・金額を固定し、戻った後に再計算しない
- 投票できたレースだけ実購入へ確定
- 現在は完全自動投票ではない
- `BetGateway` は将来の安全な公式連携差し替え境界として維持

## Exact Alarm / 全レース事前予想

- Exact Alarmはユーザー実機で設定OK確認済み
- 購入推奨アラートON/OFFとは独立して全レースを追跡
- BUY/SKIP両方を締切前保存
- 毎朝6:25 JST、アプリ起動、再起動、更新後に復旧
- 結果約20分後にsettle
- 結果後の後付け予想は行わない

## 本番予想ロジック

研究用モデルは本番へ未統合。現行安定ロジックを継続使用。

主な過去不採用結果:
- v12: 2026年5〜9月 ROI117.3%だが旧年 2023 72.0% / 2024 45.5% / 2025 56.3%
- rich-feature race-softmax Run `35839229134`: 2024設計 ROI90.1%、2025固定 ROI59.2%
- CORE r1 144条件: 2024通年で年間ROI105%以上通過0件、十分な件数の最高ROI 94.081871%

**2025-10-01〜2025-12-31 Q4最終holdoutは候補完全固定前に開かない。**

## v0.16 Work研究

通常チャットとは分離してWork側で研究継続。

- CORE r1の144条件は不採用確定、同じ条件グリッドを再実行しない
- r2 conditional hypotheses / saved-prediction calibration auditまで研究専用workflowで進行
- Run `35876699180` は SUCCESS
- 本番Android / UI / Releaseは通常チャット側管理
- Work研究結果を自動で本番へ昇格しない
- Q4 final holdoutは候補完全固定前に開かない

詳細・最新位置は必ず `WORK_HANDOFF.md` を優先して確認する。

## 次の実機確認

1. 実機をv0.15.8へ更新
2. 右上の歯車から独立した設定画面が開くか
3. 損益タブから設定項目が消え、画面が短くなっているか
4. 設定画面で端末の戻るキー → 元画面へ戻るか
5. 購入 / 結果 / 損益で戻るキー → 予想ホームへ戻るか
6. レース詳細 / 競艇場一覧で戻るキーが1段ずつ戻るか
7. 予想ホームで戻るキーを押してもアプリが終了しないか
8. 次の購入推奨通知でバイブレーションしないか
9. 事前予想トラッカー等のバックグラウンド通知でもバイブレーションしないか
10. 次回購入可能時間に一括投票フローを実機確認
11. `締切前保存 X / 当日結果 Y` の保存率 / settleを確認

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
