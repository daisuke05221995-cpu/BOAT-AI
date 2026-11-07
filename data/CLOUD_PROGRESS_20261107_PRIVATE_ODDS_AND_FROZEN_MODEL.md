# BOAT AI 2026-11-07 — 個人利用オッズ継続と固定Model Aアセット準備

## ユーザー要望と既存動作

- BOAT AIは個人用Androidアプリ。これまで端末で取得していた3連単オッズ機能は**削除・無効化しない**。
- 既存 `BoatRaceRepository.loadOfficialTrifectaOddsDetailed` は公式PC→公式スマホページを順に読み込み、失敗時はBoatraceCSV公開CSVから120点が揃う場合のみ予備推定。取得済みの観測値と推定値は同一の「確定オッズ」と扱わない。
- 既存 `TrifectaOddsParserTest` は公式3連単表のrowspanを含む120通りの構文を検証している。今回Androidのオッズ経路は変更していない。
- 2026-11-07 JSTの診断で公式の公開オッズページへの単発のHTTPSリクエストはHTTP 200を返した。**それは当日全場の120点完備・取得時刻の真偽・Cloudflare Workerからの稼働・アクセス許諾の保証ではない**。
- 公式のサイトポリシーには私的使用に関する記載と、運営に支障を及ぼす大量アクセス等の禁止がある。端末での個人向け閲覧・取得があったことだけで、クラウドからの全国一斉自動巡回やデータ再配信まで許諾済みとは扱わない。本番Cronで無断の大量取得を開始しない。

## 今回の安全な実装

- `0007_model_a_frozen_assets.sql`: 既存レース・購入・D1履歴世代を壊さない追加テーブルのみ。
- `model-a-model-store.mjs`: Android固定の3本のLightGBMモデルSHA・サイズ・545/715/885特徴量を検証し、256KiB以下に分割してD1へ原子的にステージングし、全チャンク再検証後に読み出せる。任意モデルへの入替え・再学習は不可。
- 本番Worker API・Cron・Androidのオッズ取得は変更しない。固定モデル本体はD1へ未投入、実推論はまだ有効化しない。
- `model-a-model-store.test.mjs` とschemaテストで、固定Android 3資産の一致、実LightGBM評価の一致、破損拒否、DBトランザクションのロールバックを確認。

## 履歴の確認（本番昇格は禁止）

- Android固定 `model_a_history.bin`: 最終日2026-09-23、141,542レース。
- GitHub `data/model_a_recent_history.bin`: 最終日表示2026-11-06、147,741レース、SHA-256 `dd7f5f0908a086b4b9299bd09a61e2937743f8188aa896d2caebd33df436a406`。
- 同日 `data/model_a_recent_virtual_summary.json` には `sourceRaces=156`、`skippedUnsettledOrNonUnique=24`、`eligibleSettled=132` と記録。直前オッズarchive取得失敗と120点欠損もあり、仮想収支に0件の窓がある。
- これは研究用rolling履歴の存在証拠であり、日別の全開催・6艇・結果・事前展示・使用許諾が網羅された証拠ではない。`MODEL_A_HISTORY_STALE` を解除せず、更新済みと偽装しない。2025Q4の未開封生データにはアクセスしない。

## 未解決・次の工程

1. 私的利用とクラウド自動収集の運用条件を分け、特に公式サイトへのリクエスト頻度・保存と派生配信の扱いを確認する。WorkのPR #42の調査範囲は変更しない。
2. 日付別の独立開催マニフェストによる実履歴検査。完全性が証明されるまでは研究用rollingファイルを本番投入しない。
3. 固定モデルをテスト専用のクラウドD1へステージングする運用を別工程にして、SHA検証と実レースのAndroid対Worker確率一致を確認する。
4. 締切8分前の6艇展示・展示ST・気象・120オッズ・各配信元観測時刻の信頼できる取得経路が確定するまで、WorkerのBUY/SKIP生成は止めておく。
