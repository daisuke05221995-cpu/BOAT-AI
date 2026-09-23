# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`
安定公開版: `v0.15.2`

## Work上限・停止時の最重要ルール

Workの使用上限、タイムアウト、コンテキスト不足などで継続できなくなりそうな場合は黙って終了しない。
終了前に必ず有効な変更をcommit/pushし、このファイルへ現在位置・Run ID・次の具体的1手を保存する。
その後ユーザーへ通常チャットへ戻るよう案内する。

復帰案内:
> Workの上限に近づいたためGitHubへ状態を保存しました。通常チャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて」と送ってください。

## v0.15.2 公開完了

- versionCode: 20
- versionName: 0.15.2
- Release commit: `da699f7e622623dc1d691e1d0fd74db0e0e29f77`
- Release Run: `35859556778`
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.2`
- APK: `BOAT-AI-v0.15.2.apk`
- APK SHA-256: `e6580542ce1710fc4da3879af1023b944c50d3a340e9edffe83c59268b492835`

Release WorkflowでUnit test / lint / signed APK / signature verify / GitHub Release公開まで成功。

## v0.15.2 主修正

- レース詳細の「AI購入判断」直下へ確定結果カードを復元
  - 3連単結果
  - 払戻
  - 締切前保存した事前予想
  - 的中/ハズレ
  - 想定払戻
- 損益の当日カードは「全予想（購入推奨＋見送り）」を先頭表示
- 購入推奨だけの成績も別枠で継続表示
- `締切前保存 Xレース / 当日結果 Yレース` を表示して取りこぼしを可視化
- 結果後に未保存レースを後付け予想しない方針は維持

## 全レース自動履歴

v0.15.1の5分前購入推奨アラートを拡張し、v0.15.2からは各レースの締切約5分前バックグラウンド評価でBUY/SKIPの両方を予想履歴へ保存する。

流れ:
1. 毎朝6:30 JSTに当日全国レースを登録
2. 各レース締切約5分前に最新データと公式オッズで最終評価
3. BUY/SKIPどちらも `PredictionHistoryStore.upsertEvaluatedRace()` で保存
4. BUYだけユーザーへ購入推奨通知
5. 締切約20分後に結果取得・予想履歴settle
6. 後続レース5分前評価時にも、それ以前の確定結果をsettle

これにより今後の日別成績は、アプリで各レースを手動表示しなくても締切前保存できた全国レース全体を集計できる。
通知/アラートが無効・OSが処理を止めた等で保存できなかった場合は、画面の保存数/結果数で欠損を確認できる。

## v0.15.1から継続する購入推奨アラート

- 全国全レース対象
- 締切約5分前に再評価
- BOAT AI本体と同じ `PredictionEngine` / `LearningStore` / `PerformanceMemoryStore`
- 同じ `BetStrategy.oddsRecommended()` を画面と通知で共有
- AI条件＋最新公式3連単オッズ条件を通過したBUYだけ通知
- 通知に買い目、オッズ、推奨金額、判定理由
- 公式オッズページへの導線
- 自動投票はしない
- Android 12+は正確な5分前実行のため「アラームとリマインダー」許可推奨
- Android 13+は通知権限が必要

## 本番予想ロジック

研究用Value Strategy / race-softmaxは本番へ入れていない。
`app/src/main/assets/value_strategy_model.json` は存在せず、現行安定ロジックを使用。

主な不採用研究結果:
- v12: 2026 ROI117.3%だが、2023 72.0% / 2024 45.5% / 2025 56.3%
- rich race-softmax Run `35839229134`: 2024 ROI90.1%、2025固定ROI59.2%

2025-10-01〜2025-12-31 Q4最終holdoutは未開封。

## 次の具体的1手

1. 実機をv0.15.2へ更新
2. 戸田等の終了済みレース詳細で「AI購入判断」直下に結果カードが戻っているか確認
3. 損益の今日カードで「全予想」が先頭、「締切前保存 X / 当日結果 Y」が表示されるか確認
4. 購入推奨アラートをONにして翌開催日に全レース履歴が自動保存されるか確認
5. 実機不具合があればv0.15.xで修正
6. 予想精度改善はv0.16以降

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
