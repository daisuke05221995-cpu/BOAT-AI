# BOAT AI 引継ぎメモ

更新日: 2026-09-23

## 現在の状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.3`
- Android package: `jp.boatai.app`
- versionCode: `21`
- versionName: `0.15.3`
- Release target commit: `446b7e3005a18b592d88d2726cc9abb3dd3c8d95`
- Release workflow Run: `35863168523` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.3`
- APK: `BOAT-AI-v0.15.3.apk`
- APK SHA-256: `ea8992abdf28b45a919e99940381165c10845e4b28d5051a83ecc6ab4c3771bf`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.3/BOAT-AI-v0.15.3.apk`

## v0.15.3 主修正

結果タブの「事前予想」が通知設定に依存して欠落する問題を修正。

### 全レース事前予想トラッカー
- `PredictionTrackingScheduler.kt` を追加
- 購入推奨アラートのON/OFFと独立して常時動作
- アプリ起動時に当日追跡を再登録
- 毎朝6:25 JSTに当日全国レースを登録
- 端末再起動 / アプリ更新後も再登録
- 各レース締切前に同じ `PredictionEngine` / `BetStrategy` / `LearningStore` で予想
- BUY/SKIPどちらでも買い目を `PredictionHistoryStore.upsertEvaluatedRace()` へ保存
- 既存購入推奨アラートが先に最終予想を保存済みなら重複評価を回避
- 締切約20分後に結果を取得しprediction historyをsettle
- 自動記録用foreground service通知は無音・無振動・低優先度
- BUYのユーザー通知は従来の購入推奨アラート設定にのみ従う

これにより次開催日以降、通知をOFFにしていても結果タブの「事前予想」と損益の日別母数を全レース分蓄積できる構成。

### 重要: 過去レースは後付けしない
v0.15.3導入前に締切前保存できなかったレースは、結果を見た後から「事前予想」を生成しない。
2026-09-23の桐生等で `記録なし` のものはそのまま残す。これは的中率を水増ししないため。

## v0.15.2から継続

- レース詳細のAI購入判断直下に確定結果カード
- 3連単結果 / 払戻 / 締切前事前予想 / 的中・ハズレ / 想定払戻
- 損益の日別カードは全予想（BUY+SKIP）を先頭表示
- 購入推奨のみの仮想成績を別表示
- `締切前保存 Xレース / 当日結果 Yレース` を表示
- 各レース締切約5分前の購入推奨アラート
- BUYだけ通知、SKIPは通知しない
- 自動投票は行わない

## Release検証

v0.15.3 Release Workflowで以下すべて成功:
- Unit test
- Android lint
- signed Release APK build
- APK署名検証
- GitHub Release公開
- APK / SHA256資産アップロード

事前Debug検証 Run `35862849909` も SUCCESS。

## 本番予想ロジック

研究用Value Strategy / race-softmaxは本番へ入れていない。
`app/src/main/assets/value_strategy_model.json` は存在せず、現行安定ロジックを継続使用。

主な不採用研究結果:
- v12: 2026年5〜9月 ROI117.3%だが旧年 2023 72.0% / 2024 45.5% / 2025 56.3%
- rich-feature race-softmax Run `35839229134`: 2024設計 ROI90.1%、2025固定 ROI59.2%

**2025-10-01〜2025-12-31 Q4最終holdoutは未開封。**
新モデル候補を完全固定した後だけ一度使用する。

## 次の作業

1. 実機をv0.15.3へ更新
2. 翌開催日、結果タブの事前予想がBUY/SKIPを問わず各レースに保存されるか確認
3. 損益で `締切前保存 X / 当日結果 Y` が近い値になるか確認
4. 購入推奨アラートOFFでも事前予想が保存されることを確認
5. BUY通知を使う場合のみ購入推奨アラートをON
6. 実機不具合はv0.15.xで修正
7. 予想精度研究はv0.16以降

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
