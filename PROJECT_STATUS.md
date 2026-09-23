# BOAT AI 引継ぎメモ

更新日: 2026-09-23

## 現在の状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.4`
- Android package: `jp.boatai.app`
- versionCode: `22`
- versionName: `0.15.4`
- Release target commit: `2fa7987ab5857114c6fd4ad6c4ace2d12acfcc4c`
- Release workflow Run: `35867749606` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.4`
- APK: `BOAT-AI-v0.15.4.apk`
- APK SHA-256: `6b277b4e36d4918f80b61ca70b15d760fcea8bc741813c34459adb087834dc5f`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.4/BOAT-AI-v0.15.4.apk`

## v0.15.4 主修正

### 締切前予想の保存精度を強化
Android 14以降では、新規インストール時に `SCHEDULE_EXACT_ALARM` が未許可になることがある。
未許可時は従来コードが不正確アラームへフォールバックするため、端末状態によって締切前の予想保存が遅れる可能性があった。

v0.15.4で以下を追加:
- 購入推奨アラートON/OFFとは独立してExact Alarm状態を常時表示
- 未許可時に `締切前の自動記録を正確にする` ボタンを表示
- Androidの `アラームとリマインダー` 設定画面へ直接遷移
- 許可後に当日レースの事前予想トラッカーを即再登録
- `ExactAlarmPermissionReceiver` を追加
- `ACTION_SCHEDULE_EXACT_ALARM_PERMISSION_STATE_CHANGED` を受信
- 許可直後に全レース事前予想トラッカーを再構築
- 購入推奨アラートがONなら通知側のアラームも再構築
- Exact Alarm未許可でも従来どおり不正確アラームへフォールバックし、完全停止はしない

## v0.15.3から継続する全レース事前予想トラッカー

- 購入推奨アラートON/OFFと独立して常時動作
- アプリ起動時に当日追跡を再登録
- 毎朝6:25 JSTに当日全国レースを登録
- 端末再起動 / アプリ更新後も再登録
- 各レース締切前に同じ `PredictionEngine` / `BetStrategy` / `LearningStore` で予想
- BUY/SKIPどちらでも買い目を `PredictionHistoryStore.upsertEvaluatedRace()` へ保存
- 既存購入推奨アラートが先に最終予想を保存済みなら重複評価を回避
- 締切約20分後に結果を取得しprediction historyをsettle
- 自動記録用foreground service通知は無音・無振動・低優先度
- BUYのユーザー通知は購入推奨アラート設定にのみ従う

### 重要: 過去レースは後付けしない
v0.15.3導入前、または締切前に保存できなかった過去レースは、結果を見た後から「事前予想」を生成しない。
2026-09-23の桐生等で `記録なし` のものはそのまま残す。これは的中率を水増ししないため。

## 結果・損益表示

- レース詳細のAI購入判断直下に確定結果カード
- 3連単結果 / 払戻 / 締切前事前予想 / 的中・ハズレ / 想定払戻
- 損益の日別カードは全予想（BUY+SKIP）を先頭表示
- 購入推奨のみの仮想成績を別表示
- `締切前保存 Xレース / 当日結果 Yレース` を表示
- 各レース締切約5分前の購入推奨アラート
- BUYだけ通知、SKIPは通知しない
- 自動投票は行わない

## Release検証

事前Debug検証 Run `35867410643` SUCCESS:
- Live race API schema
- Unit test
- Android lint
- Debug APK build

v0.15.4 Release Run `35867749606` SUCCESS:
- Unit test
- Android lint
- signed Release APK build
- APK署名検証
- GitHub Release公開
- APK / SHA256資産アップロード

## 本番予想ロジック

研究用Value Strategy / race-softmaxは本番へ入れていない。
`app/src/main/assets/value_strategy_model.json` は存在せず、現行安定ロジックを継続使用。

主な不採用研究結果:
- v12: 2026年5〜9月 ROI117.3%だが旧年 2023 72.0% / 2024 45.5% / 2025 56.3%
- rich-feature race-softmax Run `35839229134`: 2024設計 ROI90.1%、2025固定 ROI59.2%

**2025-10-01〜2025-12-31 Q4最終holdoutは未開封。**
新モデル候補を完全固定した後だけ一度使用する。

## 次の作業

1. 実機をv0.15.4へ更新
2. `事前予想の自動記録` が `正確な時刻で記録：有効` か確認
3. `要設定` の場合は `締切前の自動記録を正確にする` → Androidの `アラームとリマインダー` でBOAT AIを許可
4. 翌開催日、結果タブの事前予想がBUY/SKIPを問わず各レースに保存されるか確認
5. 損益で `締切前保存 X / 当日結果 Y` が近い値になるか確認
6. 購入推奨アラートOFFでも事前予想が保存されることを確認
7. BUY通知を使う場合のみ購入推奨アラートをON
8. 実機不具合はv0.15.xで修正
9. Work側では並行してv0.16予想モデル研究を継続

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
