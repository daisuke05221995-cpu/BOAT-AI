# BOAT AI クラウド実行基盤（段階1：データ収集・監査契約）

Androidを起動していなくても、Cloudflare Workersの定期実行でレース情報を蓄積するための基礎実装。**2026-11-06にCloudflareへ初期デプロイ成功**（GitHub Actions `42216781153`）。ただし、**クラウドAI購入予想は未実装**。`READY` を偽装せず、必要なモデル同等性検証が終わるまで `PENDING` / `UNAVAILABLE` とする。

## 実装済み

- `* * * * *` のCronがD1内の締切時刻を確認。**外部サイトに毎分アクセスしない**。
- 日本時間（JST）当日06:00〜23:59に開催スケジュールを1回取り込み。デプロイ遅延・午前のソース障害時も当日中に復旧し、失敗時のみ最大1時間ごとに再試行。過去の締切済み予想は生成しない。
- **締切8分前**に展示＋オッズの取得を開始。失敗時は**5分前に1回のみ**再試行。遅延時は締切前に限り実行し、締切後の後付け予想は禁止。
- 一連の取得をD1に記録し、Cronの重複起動でも同一レースの同時重複を抑止。公開APIは読取専用。
- 結果・払戻は締切20分後から別途取得。未掲載なら45分後に最後の再試行。
- `GET /v1/health`、`GET /v1/forecasts?date=YYYY-MM-DD`。現時点では購入履歴・端末バックアップの送信は不要。
- 運用監査 `/v1/audit?date=YYYY-MM-DD`：Cron最終起動・完了時刻、T-8/T-5試行回数、取得/欠損、原因コード、結果回収率、BUY/SKIP確定数を**個別選手情報・ユーザーの購入情報なし**で確認できる。`0002_operational_audit.sql` が試行履歴・heartbeatを永続化する。
- GitHub mainにクラウド関連コードが反映されると自動デプロイし、公開APIのhealthとauditをスモークテストする。
- D1無料枠の1回の実行あたりのクエリ数制限に対応するため、開催表（最大288R）、同時刻のT-8/T-5取得、結果記録をまとめたD1 batchで保存する。外部展示・オッズのT-8/T-5取得タイミングは変更しない。

## 現時点のブロッカー（推奨購入は返さない）

1. 現行の公式オッズHTMLをクラウドから安定取得できると確認できていない。`ODDS_API_URL` は利用許可とレスポンス形式が確認されたHTTPS配信先のみ設定する。
2. 現在参照する非公式の[Boatrace Open API](https://github.com/boatraceopenapi/api)は当日オッズを提供せず、更新が約10分周期で反映に10〜20分遅れる場合がある。**T-8に新鮮な展示が必ず届くとは扱わない**。T-8用の利用許可のある低遅延ソースが必要。
3. Androidの Model A / 購入判定のサーバー版がまだない。**同一入力・同一結果のパリティテスト合格まで、クラウド側でBUY/SKIP判定しない**。
4. Android側のクラウド同期と競合解消が未実装。アプリの実購入履歴はローカルに残す。
5. CloudflareのCronは実行開始が遅れる場合がある。時刻監査と実データでの運用試験が必要であり、厳密な8分前実行の保証ではない。

## 初期セットアップ（完了済み：以下は再構築時の手順）

1. Cloudflareの無料アカウントを作成する。パスワード・APIトークンをチャットに送らない。
2. 手元/CIから `npx wrangler login`、`npx wrangler d1 create boat-ai-forecast` を実行し、出力された `database_id` を `wrangler.toml` に設定する。
3. `npx wrangler d1 migrations apply boat-ai-forecast --remote` で `migrations/0001_initial.sql` を適用する。
4. 利用許可のある展示・オッズ配信先が決まった場合のみ、`ODDS_API_URL` をWorker環境変数、認証が必要なら `ODDS_API_TOKEN` を `wrangler secret put` で設定。契約: `GET ?date=YYYY-MM-DD&stadium=数字&race=数字` → `{ "odds": { "1-2-3": 12.4, ... }, "source": "provider-name" }`。3連単100点以上、正の数値でなければ不完全として扱う。
5. **スマホからの公開ルート:** GitHubのリポジトリ `Settings → Secrets and variables → Actions` に以下の3つを登録する（このチャットには貼らない）：
   - `CLOUDFLARE_API_TOKEN` : Workers Scripts 編集とD1操作に必要な範囲のみ認可したCloudflare APIトークン
   - `CLOUDFLARE_ACCOUNT_ID` : CloudflareアカウントID
   - `BOAT_AI_D1_DATABASE_ID` : 作成したD1データベースのID（UUID）
6. GitHub `Actions → Deploy Cloud forecast → Run workflow` でマイグレーション適用＋Worker公開を一括実行。以後は **mainのクラウド関連コードが更新されると自動再公開**される（PR・それ以外の変更では公開しない）。初期設定時に `workers.dev` アカウント用サブドメインが未登録なら、APIで一度だけ自動登録する。既存の登録名は変更しない。
   - 直接CLIを使う場合は `npx wrangler d1 migrations apply boat-ai-forecast --remote` → `npx wrangler deploy` でも可。
7. まず数日間の取得時刻・漏れ・配信元制限を監査し、モデルパリティ実装・端末同期・段階リリースへ進む。

## データと運用の注意

- プログラムJSONはAndroidが参照する `boatraceopenapi.github.io/api/v1/YYYY/YYYYMMDD.json` の公開日付フィードと同形式を期待。`closed_at` をJSTとして解釈する。公開フィードの更新遅延を実行時刻監査で区別する。
- 取得不能は `failure_code` で記録。`UNAVAILABLE` は見送り (`SKIP`) と区別し、的中率・ROIの分母へ入れない。
- `POST` を含む外部書き込みAPIは提供しない。公開APIにはレース情報のみを返す。必要に応じてCloudflare側のレート制限とアクセス制御を追加。
- D1スキーマは **初期構築用**。本番データがある場合、後から `0001` を再適用してデータ移行するのではなく、追加のmigrationを作る。

## ローカル検証

```sh
cd cloud/forecast-worker
npm test
```

Node 22以上で実行可能。Cloudflareの認証やネットワーク接続を必要とせず、時刻制御・取引条件・HTTP応答・D1互換SQLiteのスキーマを検証する。
