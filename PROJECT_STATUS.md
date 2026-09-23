# BOAT AI 引継ぎメモ

更新日: 2026-09-23

## 現在の状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.6`
- Android package: `jp.boatai.app`
- versionCode: `24`
- versionName: `0.15.6`
- Release target commit: `26fc08b9c71f255b58a07f8402dcc109eee683c0`
- Release workflow Run: `35872050504` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.6`
- APK: `BOAT-AI-v0.15.6.apk`
- APK SHA-256: `bf2400fe899a6cf5cb136e0f7781ca2ab530ebaaf8337a61a9ca7183121fd022`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.6/BOAT-AI-v0.15.6.apk`

## v0.15.6 主修正: 実購入の一括公式投票ハンドオフ

一括購入を最優先に、従来の「購入記録を先に作る」方式から、実際の公式投票と実購入記録を分離した。

### 一括購入フロー
1. 予想画面で複数レースを選択
2. `選択分を一括投票へ` を押す
3. その時点のレース・3連単買い目・各金額を `PendingPurchaseSession` に固定保存
4. 公式BOAT RACEのシンプル投票サイト `https://bu.tbbr.jp/` を開く
5. 公式サイトで実際に投票する
6. BOAT AIへ戻ると `公式投票待ち` カードを表示
7. 実際に投票できたレースだけチェックを残す
8. `Nレースを投票完了として記録` で、そのレースだけ実購入として `BetStore` へ保存
9. 結果確定後は従来どおり払戻・実損益へsettle

### 実装ファイル
- `PendingPurchaseStore.kt`
  - ブラウザ移動中も買い目・金額を永続保存
  - レース単位の投票完了選択を保持
  - 締切後に戻っても買い目を再計算せず、投票前に固定した内容を使用
- `PendingPurchaseCard.kt`
  - レース一覧 / 買い目 / 金額 / 合計を表示
  - レース単位で実投票済みチェックをON/OFF
  - 公式投票サイト再表示 / 全選択 / 実購入確定 / 破棄
- `BoatViewModel.kt`
  - 一括・個別の投票待ち作成
  - 投票済みレースの選択
  - 確認済みレースだけ実購入へ変換
- `BetStore.kt`
  - `addConfirmedPurchases()` を追加
  - 投票前に固定した正確な金額だけを実購入記録へ反映
- `MainActivity.kt`
  - 一括購入の主ボタンを `選択分を一括投票へ` に変更
  - 個別購入も `公式投票へ` に変更

### 重要: 現在は完全自動投票ではない
v0.15.6は「BOAT AIで買い目確定 → 公式投票サイトへ移動 → 本人が公式側で投票 → BOAT AIで実購入確定」の半自動フロー。
公式サイトへ無人ログインして最終投票ボタンまで自動確定する処理は未実装。
`BetGateway` は将来、公式に利用可能な安全な連携方式が確認できた場合に差し替えられる境界として維持する。
二重投票・誤投票を避けるため、公式連携手段がない状態で無人の最終投票は行わない。

## v0.15.5から継続: 通知は無音・無振動

- 購入推奨アラートを画面通知のみへ変更
- 通知音なし
- 振動なし
- Androidが既存通知チャンネル設定を保持する問題を避けるため、新しい購入推奨通知チャンネルIDを使用
- バックグラウンド判定用foreground service通知も無音・無振動

## v0.15.4から継続: Exact Alarm対策

Android 14以降のExact Alarm未許可による締切前保存の遅延対策を維持。

- 購入推奨アラートON/OFFとは独立してExact Alarm状態を表示
- 未許可時に `締切前の自動記録を正確にする` ボタンを表示
- Androidの `アラームとリマインダー` 設定画面へ直接遷移
- 許可後に当日レースの事前予想トラッカーを即再登録
- `ExactAlarmPermissionReceiver` で許可後に再構築
- 購入推奨アラートONなら通知側アラームも再構築
- 未許可でも不正確アラームへフォールバックし、完全停止はしない

## v0.15.3から継続: 全レース事前予想トラッカー

- 購入推奨アラートON/OFFと独立して常時動作
- アプリ起動時に当日追跡を再登録
- 毎朝6:25 JSTに当日全国レースを登録
- 端末再起動 / アプリ更新後も再登録
- 締切前に同じ本番PredictionEngineでBUY/SKIP両方を保存
- 締切約20分後に結果を取得してprediction historyをsettle
- 過去の未保存レースを結果後に後付け予想しない

## 結果・損益表示

- 3連単結果 / 払戻 / 締切前事前予想 / 的中・ハズレ / 想定払戻
- 損益の日別カードは全予想（BUY+SKIP）を表示
- 購入推奨のみの仮想成績を別表示
- `締切前保存 Xレース / 当日結果 Yレース` を表示
- 実購入はv0.15.6以降、公式投票後に確認したレースだけ損益へ入る

## Release検証

一括購入実装 Debug検証 Run `35871671482` SUCCESS:
- Live race API schema
- Unit test
- Android lint
- Debug APK build
- APK artifact upload

v0.15.6 Release Run `35872050504` SUCCESS:
- Unit test
- Android lint
- signed Release APK build
- APK署名検証
- GitHub Release公開
- APK / SHA256資産アップロード

## 本番予想ロジック

研究用Value Strategy / race-softmaxは本番へ未統合。現行安定ロジックを継続使用。

主な過去不採用結果:
- v12: 2026年5〜9月 ROI117.3%だが旧年 2023 72.0% / 2024 45.5% / 2025 56.3%
- rich-feature race-softmax Run `35839229134`: 2024設計 ROI90.1%、2025固定 ROI59.2%

**2025-10-01〜2025-12-31 Q4最終holdoutは候補完全固定前に開かない。**
Work側は `WORK_HANDOFF.md` に従いv0.16研究専用で進める。

## 次の実機確認

1. 実機をv0.15.6へ更新
2. `事前予想の自動記録` が `正確な時刻で記録：有効` か確認
3. 購入推奨アラートが無音・無振動で届くか確認
4. 複数の購入推奨レースを選択して `選択分を一括投票へ` を押す
5. 公式シンプル投票サイトが開くか確認
6. BOAT AIへ戻って `公式投票待ち` が残っているか確認
7. テスト時は1レースだけチェックを外し、残したレースだけ実購入記録へ入るか確認
8. 結果確定後、確認済み実購入だけが払戻・損益へ反映されるか確認
9. 全レース事前予想保存率とsettleを確認
10. Work側のv0.16研究結果を通常チャット側でレビュー

## 将来の購入自動化

- 現在: 半自動の公式投票ハンドオフ
- 次段階: 公式サイトへの入力作業短縮、購入待ち画面の操作性向上
- 完全自動投票: 公式に利用可能な安全な連携方式と認証・二重投票防止・金額上限・監査ログを確認した後にのみ検討
- `BetGateway` を将来の差し替え境界として維持

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
