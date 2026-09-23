# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-24

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 安定公開版: `v0.15.8`
- versionCode: 26
- versionName: 0.15.8
- Release Run: `35881038684` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.8`
- APK: `BOAT-AI-v0.15.8.apk`
- APK SHA-256: `a0d10f2aca01ba623489fd067cb105453a7568deed050bb45c7947ae5c8c4830`

## 最初に確認

1. `PROJECT_STATUS.md`
2. `WORK_HANDOFF.md`
3. 最新GitHub Actions / 進行中Run
4. ユーザー実機がv0.15.8へ更新済みか
5. 右上歯車の独立設定画面
6. Android戻るキーの画面階層動作
7. 新通知チャンネルでバイブレーションが止まったか
8. 次回購入可能時間の一括公式投票ハンドオフ
9. 翌開催日の全レース事前予想保存率

## v0.15.8 UI / 操作修正

### 設定を独立

- 右上に歯車の設定ボタンを追加
- `SettingsScreen` を新設
- 通知・Exact Alarm・バックアップを設定画面へ集約
- 損益タブの `通知・バックアップ設定` 折りたたみを削除
- 下部4タブ `予想 / 購入 / 結果 / 損益` は日常操作専用に整理

### 端末の戻るキー

- 設定 → 元画面
- レース詳細 → 競艇場一覧
- 競艇場一覧 → 予想ホーム
- 購入 / 結果 / 損益 → 予想ホーム
- 予想ホーム → アプリを終了しない

### 通知を完全無振動化

Androidが以前のNotification Channel設定を保持するため、新しいチャンネルIDへ切り替えた。

- 通常通知 `boat_ai_events_visual_v3`
- 購入推奨 `boat_ai_buy_alerts_visual_v3`
- 購入判定service `boat_ai_alert_checks_visual_v3`
- 事前予想tracker `boat_ai_prediction_tracking_visual_v2`

Channel側とNotification Builder側の両方で音・振動を無効化。購入推奨だけでなくforeground service / tracker通知も対象。

## Build / Release検証

UX修正 Debug Run `35880611845`: SUCCESS
- API schema
- Unit test
- Android lint
- Debug APK build
- artifact upload

v0.15.8 Release Run `35881038684`: SUCCESS
- version確認
- signing secrets確認
- signed Release APK build
- APK署名検証
- GitHub Release公開

### CI深夜対策

0時直後に当日BOAT APIが未公開でも誤失敗しないよう、API schema確認は当日から直近3日前までフォールバックする。

## v0.15.7から継続: 4タブUI

`予想 / 購入 / 結果 / 損益`

- 購入タブ: 公式投票待ち / 本日購入 / 結果待ち / 確定損益 / 購入履歴
- 結果タブ: 競艇場単位の折りたたみ
- 損益タブ: `今日 / 7日 / 月 / 全期間` 切替、実購入損益を最優先
- AI分析は折りたたみ
- 設定はv0.15.8で損益から分離

## v0.15.6から継続: 一括購入

`複数レース選択 → 選択分を一括投票へ → 買い目/金額を固定保存 → 公式シンプル投票サイト → BOAT AIへ戻る → 実際に投票したレースだけ一括確定 → 実損益へ反映`

- ブラウザ移動中も購入待ちは保持
- 戻った後に買い目を再計算しない
- 投票できたレースだけ実購入へ確定
- 現在は完全自動投票ではない

## 通知・事前予想

- Exact Alarmはユーザー実機で設定OK確認済み
- 全レース事前予想は通知設定と独立して追跡
- BUY/SKIP両方を締切前保存
- 結果約20分後にsettle
- v0.15.8から全関連通知チャンネルを表示のみ・無振動へ更新

## v0.16 Work研究

- CORE r1の144条件は2024通年で不採用確定
- 年間ROI105%以上通過: 0
- 十分な件数を持つ最高ROI: 94.081871%
- 同じ144条件は再実行しない
- r2 conditional hypotheses / auditを研究専用workflowで継続
- Run `35876699180`: SUCCESS
- 2025 Q4 final holdoutは候補完全固定前に開かない
- Android本体/UI/Releaseは通常チャット側
- 詳細な最新研究位置は `WORK_HANDOFF.md` を優先

## 実機で最優先確認

- v0.15.8へ更新
- 右上の歯車で設定画面が開く
- 損益に設定項目が残っていない
- 設定 → 戻るキーで元画面
- 購入 / 結果 / 損益 → 戻るキーで予想へ
- レース詳細 / 場一覧 → 戻るキーで1段ずつ戻る
- 予想ホームで戻るキーを押してもアプリが閉じない
- 次の購入推奨通知で振動しない
- バックグラウンド処理 / 事前予想trackerでも振動しない
- 次回購入可能時間に一括購入フローを実機確認
- `締切前保存 X / 当日結果 Y` に大きな欠落がない

## 次の優先順位

1. v0.15.8の設定・戻る・通知を実機確認
2. 公式アプリを参考に4タブの情報密度・操作導線をさらに調整
3. 一括購入フローの実機確認
4. 公式サイトへの入力作業短縮を検討
5. 全レース事前予想保存率 / settle確認
6. Work側v0.16研究結果レビュー

## Work利用時の中断ルール

Workで上限・タイムアウト・コンテキスト不足に近づいたら黙って終了しない。
GitHubへ現在位置・Run ID・次の具体的1手を保存し、通常チャットへ戻るようユーザーへ案内する。

通常チャット復帰文:
`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
