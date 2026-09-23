# BOAT AI 引継ぎメモ

更新日: 2026-09-23

## 現在の状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.2`
- Android package: `jp.boatai.app`
- versionCode: `20`
- versionName: `0.15.2`
- Release target commit: `da699f7e622623dc1d691e1d0fd74db0e0e29f77`
- Release workflow Run: `35859556778`
- GitHub Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.2`
- APK: `BOAT-AI-v0.15.2.apk`
- APK SHA-256: `e6580542ce1710fc4da3879af1023b944c50d3a340e9edffe83c59268b492835`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.2/BOAT-AI-v0.15.2.apk`

## v0.15.2 完成内容

### 基本機能
- 予想 / 結果 / 損益の3タブ
- 当日の予想一覧
- 購入推奨 / 見送り
- 全国一括 / 場別一括 / 個別購入記録
- 結果・着順・払戻・予想照合
- 実購入損益 / AI仮想損益
- 今日 / 直近7日 / 今月 / 全期間集計
- 2026年月別 / 年合計参考バックテスト
- 公式オッズ取得・60秒更新・取得診断
- JSONバックアップ / 復元、CSV出力
- GitHub Releasesアプリ内更新
- 通常アップデートで予想履歴・購入履歴を保持

### 購入推奨アラート
- 毎朝6:30 JSTに当日全国レースを登録
- 各レース締切約5分前に最新レース/展示/進入/気象/公式3連単オッズを再取得
- BOAT AI本体と同一 `PredictionEngine` / `BetStrategy` で判定
- BUYだけ通知、SKIPは通知しない
- 通知へ買い目 / オッズ / 推奨金額 / 判定理由を表示
- 公式オッズページへ遷移可能
- 自動投票は行わない

### 全レース予想履歴と日別合計の修正
v0.15.2では5分前バックグラウンド評価時にBUY/SKIPの両方を事前予想履歴へ保存する。
これにより、アプリで各レースを手動表示しなくても締切前に評価できた全国レースが日別成績へ入る。

- `PredictionHistoryStore.upsertEvaluatedRace()` 追加
- 暫定保存があっても未確定なら5分前最終判定へ置換
- BUY/SKIP両方で事前買い目を保持
- 結果後の後付け予想は作らない
- 締切約20分後に自動結果取得・prediction history settle
- 後続レース5分前評価時にも以前の結果をsettle
- 日別カードに `締切前保存 Xレース / 当日結果 Yレース` を表示
- 日別カードは「全予想（購入推奨＋見送り）」を先頭表示し、購入推奨のみの成績をその下へ表示

### レース詳細の結果復元
`AI購入判断` の直下に確定後の結果カードを再追加。
- 3連単結果
- 払戻
- 締切前保存した事前予想
- 的中 / ハズレ
- 想定払戻
- 事前履歴なしの場合は明示

## 既存データについて

v0.15.2導入前に締切前保存されなかった過去レースは、結果を知った後から予想を生成しない。
したがって2026-09-23のように既存履歴が4レースしかない日は、4レースを正しい事前予想母数として残し、画面上で保存数と当日結果数の差を表示する。
翌開催日以降、購入推奨アラートを有効にしていれば5分前評価で全国レースを自動保存する。

## 月別バックテスト

損益タブの月別カードは研究用v12ではなく、本番採用中の現行予想ロジックの `data/historical_backtest_2026.json` を表示する。
過去の締切時3連単オッズを完全再現できないため実機の最終オッズ判定は参考バックテストに含まず、UIにも参考値と明示。

2026年1〜9月参考合計:
- evaluatedRaces: 40,967
- purchaseRaces: 13,755
- purchaseHits: 4,504
- stake: 16,506,000円
- payout: 12,994,120円
- profit: -3,511,880円
- ROI: 78.7%
- hitRate: 32.7%

## 予想ロジックの扱い

複数年で再現性を確認できなかった研究モデルは本番へ入れていない。
`app/src/main/assets/value_strategy_model.json` は存在しない。
現行安定ロジックを継続使用。

不採用研究結果:
- v12: 2026年5〜9月 ROI117.3%、旧年 2023 72.0% / 2024 45.5% / 2025 56.3%
- rich-feature race-softmax Run `35839229134`: 2024設計 ROI90.1%、2025固定 ROI59.2%

**2025-10-01〜2025-12-31 Q4最終holdoutは未開封。**
新モデル候補を完全固定した後だけ一度使用する。

## Release検証

v0.15.2 Release Workflow:
- Release version解決成功
- Signing secrets確認成功
- Release signing key復元成功
- Unit test成功
- Android lint成功
- signed Release APK build成功
- APK署名検証成功
- GitHub Release公開成功
- APK / SHA256資産アップロード成功

## 次の作業

1. 実機をv0.15.2へ更新
2. 終了済みレース詳細で購入判断直下の結果カードを確認
3. 損益の日別カードで全予想が先頭に表示されることを確認
4. `締切前保存 X / 当日結果 Y` を確認
5. 購入推奨アラートONで翌開催日の全国レース履歴が自動蓄積されるか確認
6. 不具合はv0.15.xで修正
7. 予想精度研究はv0.16以降

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
