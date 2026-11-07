# Android常時取得端末 — クラウド受信監査（v0.18.27）

## 今回完了した実装

- 既存の2台目Android専用「常時取得モード」から、60秒前面ループの実績を最大2分間隔でWorkerへ送信する新しいオプション。従来モードがOFFまたはキー未設定なら何も送信せず、既存の取得機能へ影響しない。
- 送信は `schema_version`、JST開催日、匿名UUID-v4の端末ID、アプリ版、端末の送信時刻、プログラムの端末取得時刻、当日レース件数、オッズ試行/成功/失敗件数、最後の試行/成功の端末時刻の12項目だけ。購入履歴・オッズ値・展示映像・アカウント・予想は含まない。
- トークンは各Android端末上で個別に設定し、Android KeystoreのAES-GCMで暗号化。旧端末への同期やOSバックアップには含めない。アプリ内のキー削除で消去。キーはGitHubやチャットに載せない。
- Worker `POST /v1/device-collector/heartbeat` は `COLLECTOR_INGEST_TOKEN` 未設定503、誤認証401、検証不合格400系、正常202。D1 migration 0012へ端末の直近監査1件のみ保存。`GET /v1/device-collector/status?date=YYYY-MM-DD` で匿名集計を参照可能。
- 既存の固定Model A、確定結果、ユーザー実購入・仮想収支、予想判定処理、クラウド監査Cronを変更しない。`DEVICE_RECEIPT_ONLY` は配信元観測時刻の真正性を保証しないので **UNAVAILABLE→BUY/SKIPの昇格根拠にならない**。

## 運用開始の最少手順

1. GitHubの最新mainのCIが成功し、v0.18.27の署名APKがReleasesに出たことを確認する。2台目Androidのみ上書きアップデート。アンインストールやデータ削除はしない。
2. Cloudflareの `boat-ai-forecast` Workerの「Settings → Variables and Secrets」で、`COLLECTOR_INGEST_TOKEN` を**Secret**として登録。任意の英数字・ハイフン・アンダースコア32〜200文字の乱数を用いる。GitHub Actions Secretsではなく、Worker環境のSecretに置く。
3. 2台目Androidの「設定 → クラウド監査送信用の共有キー」に**同じ文字列**を入力して保存。常時取得モードをONにして画面を前面表示する。
4. 端末画面の「最後の受信確認」が更新されることを確認。`GET /v1/device-collector/status` で `active_devices_10m` が1以上、`mode=DEVICE_RECEIPT_ONLY` を確認する。503はCloudflare Secret未設定、401はキー不一致、400は時刻や計数の不一致を示す。

## 今後の未完了

- 本番端末からの送信成功・公開集計値の実証は、Worker SecretとAndroidキー設定後に初めて確認できる。**コード実装と実機導入完了は別**。
- 直前展示映像の利用許諾がある取り込み、画像解析、元サイト観測時刻の証明、120通りオッズの真正な観測、Cloudflare本番Model Aの完全パリティは別タスク。今回の通信は取得元の許諾や予想適格性の代替ではない。
- 端末を前面で開き続ける必要がある。熱・電源・OSによる停止やネット断時の再送保証はまだない。
