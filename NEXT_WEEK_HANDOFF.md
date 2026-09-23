# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-23

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 安定公開版: `v0.15.6`
- versionCode: 24
- versionName: 0.15.6
- Release Run: `35872050504` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.6`
- APK: `BOAT-AI-v0.15.6.apk`
- APK SHA-256: `bf2400fe899a6cf5cb136e0f7781ca2ab530ebaaf8337a61a9ca7183121fd022`

## 最初に確認

1. `PROJECT_STATUS.md`
2. `WORK_HANDOFF.md`
3. 最新GitHub Actions
4. ユーザー実機がv0.15.6へ更新済みか
5. Exact Alarmが有効か
6. 一括公式投票ハンドオフの実機動作
7. 翌開催日の全レース事前予想保存率

## v0.15.6で追加した重要仕様

### 一括購入を公式投票フローへ変更

従来の「一括購入登録」は実購入と公式投票が一致しないため廃止方向。
現在の主導線:

`複数レース選択 → 選択分を一括投票へ → 買い目/金額を固定保存 → 公式シンプル投票サイト → BOAT AIへ戻る → 実際に投票したレースだけ一括確定 → 実損益へ反映`

- `PendingPurchaseStore.kt` で購入待ちを永続化
- ブラウザ移動やアプリのバックグラウンド化でも保持
- 投票前に確定した買い目・金額を固定し、戻った後に再計算しない
- `PendingPurchaseCard.kt` で複数レースを一覧表示
- 実際に投票できたレースだけチェックを残して確定可能
- `BetStore.addConfirmedPurchases()` で確認済み投票だけ実購入へ保存
- 一括・個別とも公式BOAT RACEシンプル投票サイト `https://bu.tbbr.jp/` へ移動

### 現在は完全自動投票ではない

公式サイト上のログイン・買い目入力・最終投票を無人で確定する処理は未実装。
`BetGateway` は将来の公式連携差し替え境界として残す。
公式に利用可能な安全な連携がない状態で二重投票や誤投票を起こし得る無人最終投票は行わない。

## v0.15.5から継続: アラート無音・無振動

- 購入推奨アラートは表示のみ
- 通知音なし
- 振動なし
- 新通知チャンネルIDを使い、過去のAndroid通知チャンネル設定残留を回避
- バックグラウンド処理通知も無音・無振動

## v0.15.4から継続: Exact Alarm

- 通知ON/OFFと独立してExact Alarm状態を表示
- 未許可なら `締切前の自動記録を正確にする` からAndroid設定へ遷移
- 許可直後に全レース追跡を再登録
- 未許可でもフォールバックして完全停止はしない

## v0.15.3から継続: 全レース事前予想

- BUY/SKIP両方を締切前に保存
- 通知設定と独立して追跡
- 毎朝6:25 JST、アプリ起動、再起動、更新後に復旧
- 結果約20分後にsettle
- 過去未保存レースを結果後に後付けしない

## 実機で最優先確認

- v0.15.6へ更新
- Exact Alarmが `有効`
- 購入推奨通知が無音・無振動
- 購入推奨レースを複数選択
- `選択分を一括投票へ` で公式サイトが開く
- BOAT AIへ戻って購入待ちカードが保持される
- 1レースだけチェックを外した状態で確定し、残したレースだけ実購入記録に入る
- 結果確定後、その実購入だけ払戻・損益に反映される
- 一括投票待ち中に締切をまたいでも買い目/金額が変わらない
- 結果タブの事前予想がBUY/SKIP双方で蓄積される
- 損益の `締切前保存 X / 当日結果 Y` に大きな欠落がない

## Build / Release検証

一括購入Debug Run `35871671482` SUCCESS:
- API schema
- Unit test
- Android lint
- Debug APK build
- artifact upload

v0.15.6 Release Run `35872050504` SUCCESS:
- Unit test
- Android lint
- signed Release APK build
- APK署名検証
- GitHub Release公開

## 予想モデル研究

本番は現行安定ロジック。Work側は `WORK_HANDOFF.md` の並行開発ルールに従いv0.16研究専用。

- Android本体 / UI / 通知 / Releaseは通常チャット側管理
- Workは `scripts/v016_*`, `.github/workflows/v016-*`, `data/v016_*` など研究専用ファイル中心
- Q4最終holdout `2025-10-01..2025-12-31` は候補完全固定前に開かない

## 次の優先順位

1. v0.15.6一括購入フローの実機確認
2. 公式サイトへの入力作業をどこまで短縮できるか調査・改善
3. 全レース事前予想保存率と結果settleの実機確認
4. バックグラウンド制限による取りこぼし改善
5. v0.15.x実機不具合の解消
6. Work側v0.16研究結果のレビュー
7. 将来、公式に利用可能な購入連携方式が確認できた場合のみ `BetGateway` に自動購入実装を検討

## Work利用時の中断ルール

Workで上限・タイムアウト・コンテキスト不足に近づいたら黙って終了しない。
必ずGitHubへ現在位置・Run ID・次の具体的1手を保存し、通常チャットへ戻るようユーザーへ案内する。

通常チャット復帰文:
`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
