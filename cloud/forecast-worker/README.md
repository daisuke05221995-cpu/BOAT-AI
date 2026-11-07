# BOAT AI クラウド実行基盤（段階1：データ収集・監査・直前品質検証）

Androidを起動していなくても、Cloudflare Workersの定期実行でレース情報を蓄積するための基礎実装。**2026-11-06にCloudflareへ初期デプロイ成功**（GitHub Actions `42216781153`）。ただし、**クラウドAI購入予想は未実装**。`READY` を偽装せず、必要なモデル同等性検証が終わるまで `PENDING` / `UNAVAILABLE` とする。

## 実装済み

- `* * * * *` のCronがD1内の締切時刻を確認。**外部サイトに毎分アクセスしない**。
- 日本時間（JST）当日06:00〜23:59に開催スケジュールを1回取り込み。デプロイ遅延・午前のソース障害時も当日中に復旧し、失敗時のみ最大1時間ごとに再試行。過去の締切済み予想は生成しない。
- **締切8分前**に展示＋オッズの取得を開始。失敗時は**5分前に1回のみ**再試行。遅延時は締切前に限り実行し、締切後の後付け予想は禁止。
- 一連の取得をD1に記録し、Cronの重複起動でも同一レースの同時重複を抑止。公開APIは読取専用。
- 結果・払戻は締切20分後から別途取得。`0006_result_reconciliation.sql` により未確定結果は**15分間隔で再照合**し、翌JST日も前日分を回収する。旧 `result_stage=2` でも実結果が未記録なら再試行する。1 Cronで最大30R、日別フィードは1日1回の読込にまとめる。既存の確定結果は上書きしない。
- 3連単の通常結果は全成立組番を保持（同着の複数的中も欠落させない）。返還で「不成立」の場合は `UNFORMED`、明示的な「中止」「順延」は `CANCELLED` / `POSTPONED` として**通常の的中・払戻とは区別**する。出典IDが不一致、未知の状態、未掲載の結果は欠損のまま保持し架空の払戻を作らない。
- `GET /v1/health`、`GET /v1/forecasts?date=YYYY-MM-DD`。現時点では購入履歴・端末バックアップの送信は不要。
- 運用監査 `/v1/audit?date=YYYY-MM-DD`：Cron最終起動・完了時刻、T-8/T-5試行回数、取得/欠損、原因コード、結果回収率、BUY/SKIP確定数を**個別選手情報・ユーザーの購入情報なし**で確認できる。`0002_operational_audit.sql` が試行履歴・heartbeatを永続化する。結果は `settled` / `unformed` / `postponed` / `cancelled` / `legacy_settled` / `unresolved_due` に分け、再取得失敗コードも集計する。
- `0008_program_roster_candidate.sql` で、当日の日付フィード取り込み時に**6艇の出走登録番号・全国勝率等の形だけ**を検査し、診断用の別テーブルに記録する。レースID/6艇の重複・欠損・締切後の取り込みを拒否し、日別監査の `program_roster_candidate` に件数・原因を表示する。取得元の実観測時刻・利用許諾は未検証なので、通過しても **`SHAPE_ONLY_UNVERIFIED`（予想利用不可）** とする。生の展示・結果は候補へコピーせず、Android APIにも出さず、Model A/BUY/SKIPには接続しない。既存の開催・結果収集を維持する。
- GitHub mainにクラウド関連コードが反映されると自動デプロイし、公開APIのhealthとauditをスモークテストする。
- D1無料枠の1回の実行あたりのクエリ数制限に対応するため、開催表（最大288R）、同時刻のT-8/T-5取得、結果記録をまとめたD1 batchで保存する。外部展示・オッズのT-8/T-5取得タイミングは変更しない。
- 同時刻の直前取得は最大4レースを並行処理。遅い1レースが後続の締切を圧迫するのを緩和し、取得先への集中アクセスは上限4で抑える。取得元の表示時刻が古い場合は並行化しても失敗扱いにする。
- `0003_preclose_provenance.sql` と**追加の `0005_weather_provenance.sql`** で展示・オッズ・気象それぞれの配信元と取得元観測時刻を別々に保存。**6艇の展示・進入・展示ST、事前気象の個別観測時刻と出典、3連単120通りのオッズ**が揃い、同じレース・締切前・観測から2分以内でなければ、直前データ完備と判定しない。時刻不明・不一致・期限切れ・欠損は理由コードを監査に記録し、`READY` を返さない。旧レコードの気象観測時刻は補完せず未確認のまま残す。
- Android の凍結済み Model A と対応する**数値LightGBMテキスト評価器・3段階の条件付き確率エンジン**をクラウド用JavaScriptに移植。82特徴量×6艇＋24レース特徴量から**545/715/885**次元の段階別入力行を生成し、120通りの確率を計算する。数値ツリー・欠損ルーティング・順序・正規化と実アセットの読込をテスト済み。**本番Workerの予想判定にはまだ接続していない**。
- Pythonの既存 `scripts/v016_r2_model.py` と固定LightGBM 4.6.0を独立実行し、人工特徴量4レース×120通り＝**480確率**のgolden fixtureを生成。クラウドJSと全値を突き合わせ、最大絶対誤差1e-7未満を自動テストする。元モデル3本のSHA-256一致も必須。**これは確率チェーンのパリティであり、Android選手履歴・特徴量生成の実データパリティ完了を意味しない**。2025年の未開封holdout・結果・オッズは取得しない。
- Android `ModelAPlayerHistory` / 固定Python `v016_r4_player_history.py` を純JavaScriptに移植。**日別確定後に一括コミット**し、同日結果の先読みを禁止。独立Pythonコードによる合成38スナップショット（履歴32＋展示反応20）×52＝**1,976数値**と各フラグを照合し、最大誤差1e-6未満。途中失敗による履歴の部分更新も防ぐ。
- Android `ModelAFeatureBuilder` の **6艇×82特徴量＋レース24特徴量**（6艇の展示相対順位・風向ワンホット・選手履歴・反応含む）を純JavaScriptに移植。独立Pythonの合成3レース×516＝**1,548特徴量**を比較し、欠損値も保持するテストに合格。**本番Workerへ組み込んだ意味ではなく、実レース履歴・実観測入力との一致は未検証**。これらの検証用fixtureは履歴サンプルも含めすべて人工データで、未開封holdoutにアクセスしない。
- Android 同梱の実履歴 `model_a_history.bin`（BAH1、4,222,646バイト）を純JavaScriptで復元する `model-a-history-codec.mjs` を実装。Android公開アセットの固定 SHA-256 とサイズを照合し、**33,363統計キー、1,726選手、141,542レース・849,252出走分**を復号。破損・欠落・不正バージョン・余剰バイトを拒否する。ただしアセットは**2026-09-23まで**の履歴であり、直近レースには適用できない。
- `model-a-runtime.mjs` に、レース入力→履歴→特徴量→固定3段LightGBM→120通り確率の**副作用のない実行境界**を追加。日付が前日まで揃っていない履歴・欠損レース入力・未読込モデルなら確率推論自体を拒否する。独立Python LightGBM 4.6.0の合成**2レース×120通り=240確率**と全値1e-7未満で一致し、Androidの**実履歴×11月の合成レース**は `MODEL_A_HISTORY_STALE` により拒否することを検証。**まだ本番Worker APIに接続しておらず、BUY/SKIPや実レースでのパリティ完成を意味しない**。
- `model-a-daily-reconcile.mjs` に**日別選手履歴更新の厳格な入力検証ゲート**を追加。外部から供給された確定開催マニフェスト（全レースID・件数・取得元・確定観測時刻）と終局結果のキーを完全照合し、欠損・重複・日付不連続・結果不確定・6艇着順不正・モデル用直前特徴量欠損を拒否する。確定中止は理由付きのみ0更新として記録。全レースの特徴量を**同じ前日履歴**で構築し、全件成功後にコピーした状態へ1日分をコミットするため、失敗時に元の履歴は変わらない。**現段階では純粋関数と合成テストのみで、実結果の取得・D1/R2保存・本番への適用は行わない**。
- `model-a-history-codec.mjs` に Android BAH1の**バイナリ書き出し**を追加。固定Android履歴4,222,646バイトとの全バイト一致・SHA-256一致を検証。`0004_model_a_history_generations.sql` と `model-a-history-store.mjs` で約512KiBずつのD1チャンク、世代全体/各チャンクのSHA-256監査、原子的なステージングと検証後のCAS有効化を実装。途中失敗・破損・日付飛びでも既存の有効世代を維持する。**本番Cronには未接続で、固定履歴を最新と偽装しない**。
- `0007_model_a_frozen_assets.sql` と `model-a-model-store.mjs` に、固定済みAndroidのLightGBM 3ファイル（545/715/885特徴量）を**元のSHA-256とバイト数を厳密に検証し、D1へ256KiB以下のチャンクで原子的にステージングする処理**を追加。読込時は全チャンク・3モデルのハッシュと機械的なLightGBM解析・特徴量幅を再検証する。予想API・Cronへの接続、実D1への投入、モデルの再学習・変更・BUY/SKIP有効化は**していない**。
- `model-a-historical-normalizer.mjs` に**非通信の過去日JSON正規化契約**を追加。出走表・展示・結果の3つのレースID、全6艇の登録番号・進入・展示ST・着順を照合し、後付け結果値を事前特徴量へ流し込まない。中止は明示された理由のみ受理。返す `SOURCE_COVERAGE_UNVERIFIED` は「全国全レースの網羅性・配信許諾・締切前時刻は未証明」の意味。**本番データ取得や履歴への自動適用はしていない**。

### 選手履歴の安全な日別更新ゲート（本番未接続）

1. 信頼できる提供元から全国の**確定した開催レースID全件**と期待件数を独立照合し、出典・観測時刻を保存する。現在の `daily_import` のレース数だけでは全国の網羅性を証明できない。
2. 各レースを同じ ID で照合し、6艇の着順（1〜6の順列）とレース前に観測した選手ID・進入・展示・ST等が揃うことを要求する。正式な中止は出典付きの終局状態として扱い、選手履歴に架空の成績を加えない。結果だけあるレースを用いて展示を後付け補完しない。
3. 前日に続く**1日だけ**を、当日がJSTで終わった後の確定観測として検証する。`reconcileModelAHistoryDay` は元状態に触れず、合格時のみ候補状態と監査を返す。返す監査は `VALIDATED_AGAINST_SUPPLIED_MANIFEST` であり、提供元自体の独立監査を終えたという意味ではない。
4. 本番接続前に、入力マニフェストの真正性・レース網羅性の証跡と保存先（大容量履歴のバージョン・ハッシュ・原子的切替・ロールバック）を別途実装・検証する。**現時点の2026-09-23履歴を「最新」として扱わない。日付だけを書き換えて公開しない。**

### 履歴checkpoint保存（本番未接続）

- 約4.22MBのBAH1履歴をD1に一括で1行保存せず、**512KiB以下のチャンク**へ分割し、SHA-256付きで段階保存する。固定Androidアセットをバイナリ完全一致で検証した世代は `FROZEN_BASE`、全件照合済みの翌日のみ `RECONCILED_DAY` とする。
- `stageHistoryCheckpoint` はマニフェストとすべてのチャンクを1回のD1トランザクションで保存するだけで、運用中の履歴を切り替えない。
- `loadVerifiedHistoryCheckpoint` が全チャンク・全体SHA・バイナリ内部情報を照合。`activateVerifiedHistoryCheckpoint` は前世代SHAと日付が一致した場合だけcompare-and-swapで有効世代を切り替える。旧世代は破棄しない。
- **現時点ではモジュールとmigrationだけ**であり、公開API、Cron、Model Aの予測判定で使う履歴の参照先を変えていない。クラウドへ履歴を実際に投入した証拠ではない。正規ソースの完全性確認を経てから初回ステージングと有効化を別工程で行う。
- Cloudflare D1無料版にはデータベース全体の容量上限もある。履歴は1日数MB増えるため、長期保存前に監査記録を残したアーカイブ・世代保持方針を確定する。勝手に旧世代を削除しない。

## 許諾済み直前データ提供元との接続仕様（未設定）

Worker環境変数 `PREVIEW_API_URL`、`ODDS_API_URL` を**それぞれ認可済みHTTPS提供先**に設定する。認証が必要なら対応する `PREVIEW_API_TOKEN` / `ODDS_API_TOKEN` をWorker Secretとして登録する。URLには `date=YYYY-MM-DD&stadium=1&race=1` を付加して `GET` する。

展示データの期待レスポンス例：

```json
{
  "date": "2026-11-07", "stadium_number": 1, "race_number": 1,
  "source": "licensed-exhibition-provider",
  "observed_at": "2026-11-07T02:52:00Z",
  "preview": {
    "date": "2026-11-07", "stadium_number": 1, "race_number": 1,
    "wind_speed": 2, "wind_direction_number": 5, "wave_height": 3,
    "air_temperature": 19, "water_temperature": 17,
    "weather_source": "licensed-weather-provider",
    "weather_observed_at": "2026-11-07T02:51:50Z",
    "racers": {
      "1": { "course_number": 1, "exhibition_time": 6.75, "start_timing": 0.12 },
      "2": { "course_number": 2, "exhibition_time": 6.77, "start_timing": 0.13 },
      "3": { "course_number": 3, "exhibition_time": 6.72, "start_timing": 0.11 },
      "4": { "course_number": 4, "exhibition_time": 6.74, "start_timing": 0.14 },
      "5": { "course_number": 5, "exhibition_time": 6.73, "start_timing": 0.10 },
      "6": { "course_number": 6, "exhibition_time": 6.76, "start_timing": 0.15 }
    }
  }
}
```

オッズデータ：同じ上位の `date`、`stadium_number`、`race_number`、`source`、`observed_at` を持ち、`"odds": {"1-2-3": 12.4, ...}` に全**120通り**の正の有限小数を入れる。`observed_at` はキャッシュを配信した時刻ではなく、**配信元が該当レースの実データを観測した時刻**とする。UTC ISO8601 (`Z`) で指定。気象の観測は展示と異なる場合があるため、`weather_observed_at` / `weather_source` にそれぞれ実観測時刻・実出典を渡す。キャッシュ受信時刻を転記してはならない。配信元をまたいでレースIDが一致しない場合も拒否する。値や時刻を推測で埋めない。

この契約はサーバーで検証するためのものであり、**配信元の利用許諾・鮮度・品質を保証するものではない**。提供先が決まるまでは `PREVIEW_PROVIDER_NOT_CONFIGURED` または `ODDS_PROVIDER_NOT_CONFIGURED` の取得失敗を記録し、クラウド予想完了扱いにしない。`GET /v1/forecasts` には展示・気象・オッズそれぞれの `*_source` / `*_observed_at` を含む。

## 現時点のブロッカー（推奨購入は返さない）

1. 現行の公式オッズHTMLをクラウドから安定取得できると確認できていない。`ODDS_API_URL` は利用許可とレスポンス形式が確認されたHTTPS配信先のみ設定する。
2. 現在参照する非公式の[Boatrace Open API](https://github.com/boatraceopenapi/api)は当日オッズを提供せず、更新が約10分周期で反映に10〜20分遅れる場合がある。**T-8に新鮮な展示が必ず届くとは扱わない**。T-8用の利用許可のある低遅延ソースが必要。
3. Model A の固定ツリー・120確率、選手履歴・特徴量生成の**単体移植と合成Pythonエンドツーエンド照合は完了**。ただし、**Androidの実レースに対する入力、実際の全開催結果を前日まで欠損なく日別反映した履歴、モデルと購入判定の実運用同等性は未検証**。本番Workerへの接続も未実装。実運用には6艇の選手登録番号、全国勝率、展示ST・進入などに加え、過去履歴と場・風・気象等の24次元情報が必要。**利用許可済みソース＋実入力・履歴の完全性＋同一結果のパリティテストが揃うまで、クラウド側でBUY/SKIP判定しない**。
4. Android v0.18.25にクラウド予想の**読取専用同期**を実装済み。実購入履歴とAI仮想購入は従来どおり端末側で管理し、同期衝突や「予想後に購入」等の挙動は実運用テストを要する。
5. CloudflareのCronは実行開始が遅れる場合がある。時刻監査と実データでの運用試験が必要であり、厳密な8分前実行の保証ではない。

### Model A 実運用へ残る接続条件

固定3モデル（合計約2.59MB）と実履歴（約4.22MB）は、**検証テスト時のみ**Androidのアセットから読んでおり、現状のWorkerデプロイには含まれていない。D1へ固定モデルをステージング・SHA検証できるコードは用意したが、**本番D1へのモデル実投入は未実施**。選手履歴・直前入力の完全性、Model A実入力パリティ確認後にのみ実予想へ接続する。モデルや履歴がない場合は推論せず `UNAVAILABLE` にする。

`data/model_a_recent_history.bin` の見かけの最終日が11月6日でも、研究用の日次処理では未確定・着順不整合のレースを除外している。ファイル末尾の日付のみを本番用の「全国全レース検証済み」の証拠にしない。日別マニフェストと履歴の完全照合を必須とする。

### 固定Model AのD1ステージング（予想OFFのまま）

- GitHub Actionsの `Stage frozen Model A assets in D1` は、**このworkflowファイル自体のmain更新時のみ自動起動**（手動再実行も可）。通常のコード更新・デプロイ・PRでは起動しない。既存のCloudflare Secretsを利用し、Android同梱の3本だけをSHA-256・長さ・特徴量幅で検証する。
- `tools/build_frozen_model_d1_sql.mjs` が一時SQLを生成する。D1の**SQL文100KB上限**を守るため、3モデルの256KiB以下のチャンクをさらに64KiB以下のSQLリテラルに分割して段階的に追加。実行途中で停止・再実行しても二重連結しない。SQLファイルをGitHubにコミットしない。
- 書き込み後、`tools/verify_frozen_model_d1_export.mjs` が認証付きD1の該当チャンクを読み返し、各チャンクSHA、3ファイルの全体SHA、実LightGBMパース・特徴量幅を検証する。加えて固定済みPython独立ゴールデン2ケースで3連単120通り×2の予想確率を比較し、最大絶対誤差1e-7未満を強制する。モデル内容・秘密トークンは公開APIに返さない。
- この操作は**モデルの保存だけ**であり、固定モデルの再学習、D1選手履歴の活性化、予想APIへの接続、`BUY/SKIP` 有効化はしない。モデル保存成功とレース予想稼働を区別する。

### Android固定選手履歴のD1ベース配置（履歴更新・予想OFF）

- `Stage frozen Model A history base in D1` はその専用workflowのmain更新時だけ起動（手動再実行可）。**2026-09-23まで**のAndroid同梱 `model_a_history.bin`（4,222,646バイト、SHA-256 `a180aa722ad0520b5d86705bac742ff588309e72a49bed373eabf102f257acc3`）だけをBAH1構造・141,542レース・出走849,252件まで検証してD1に保存する。
- 9チャンクを64KiB以下のSQLリテラルでべき等投入。中断時は再実行で再開し、D1再読込後に全チャンク・全ファイルのSHA・BAH1構造・33,363統計キー・1,726選手を照合する。固定履歴の内容はGitHub ActionのログやAPIに出力しない。
- `model_a_history_active` は**更新しない**。このベースだけでは直近日付の予想は必ず `MODEL_A_HISTORY_STALE`。前日までの全国完全履歴が日別検証されてから、連続した世代だけを別工程で有効化する。

### クラウド実取得率の定期監査

- GitHub Actions `Audit live Cloud collection and results` は毎日11:15/翌01:10 JSTと該当workflow/監査コードのmain更新時に、公開の**読み取り専用** `/v1/audit` から当日・前日の取得実績を収集する。直前データ提供元へのアクセス・過去予想補完・D1更新は行わない。
- `tools/cloud_audit_report.mjs` が開催取込、Cron、締切前に検証できた展示・オッズ、`BUY/SKIP` 件数、結果回収率と失敗理由を照合。`UNAVAILABLE` は `SKIP` に計上しない。完備率ゼロでもjob成功は可能であり、**job成功とデータ取得成功を混同しない**。
- 監査JSONをGitHub Actions artifactとして30日保存し、ActionsのSummaryに日別表を掲載。欠損や提供元未設定はそのまま表示し、架空の時刻・オッズ・購入推奨で埋めない。
- 研究用 `data/model_a_recent_history.bin` も**読み取り専用**でBAH1デコードし、日別選手出走数÷6とD1の日別終端成立件数を比較して差を報告する。研究用は全国履歴の完全性が未証明で、件数が一致しても本番履歴へ昇格しない。差が出た日は `COUNT_DISCREPANCY_UNCERTIFIED` として記録する。

前日までの履歴を満たすには単に `lastDay` を更新するだけでは不十分。開催レース・全6艇の**結果確定・重複/欠損照合が完了した日だけ**コミットし、その監査結果を永続化すること。事故・欠損時は `MODEL_A_HISTORY_STALE` または履歴未完了として保留。新鮮なデータが揃わない日も予想を捏造しない。

## 初期セットアップ（完了済み：以下は再構築時の手順）

1. Cloudflareの無料アカウントを作成する。パスワード・APIトークンをチャットに送らない。
2. 手元/CIから `npx wrangler login`、`npx wrangler d1 create boat-ai-forecast` を実行し、出力された `database_id` を `wrangler.toml` に設定する。
3. `npx wrangler d1 migrations apply boat-ai-forecast --remote` で `migrations/0001_initial.sql` を適用する。
4. 利用許可のある展示・オッズ配信先が決まった場合のみ、`PREVIEW_API_URL` / `ODDS_API_URL` をWorker環境変数、認証が必要ならそれぞれの `*_API_TOKEN` を `wrangler secret put` で設定。上記レスポンス契約に従い、3連単120点すべて正の数値でなければ不完全として扱う。
5. **スマホからの公開ルート:** GitHubのリポジトリ `Settings → Secrets and variables → Actions` に以下の3つを登録する（このチャットには貼らない）：
   - `CLOUDFLARE_API_TOKEN` : Workers Scripts 編集とD1操作に必要な範囲のみ認可したCloudflare APIトークン
   - `CLOUDFLARE_ACCOUNT_ID` : CloudflareアカウントID
   - `BOAT_AI_D1_DATABASE_ID` : 作成したD1データベースのID（UUID）
6. GitHub `Actions → Deploy Cloud forecast → Run workflow` でマイグレーション適用＋Worker公開を一括実行。以後は **mainのクラウド関連コードが更新されると自動再公開**される（PR・それ以外の変更では公開しない）。初期設定時に `workers.dev` アカウント用サブドメインが未登録なら、APIで一度だけ自動登録する。既存の登録名は変更しない。
   - 直接CLIを使う場合は `npx wrangler d1 migrations apply boat-ai-forecast --remote` → `npx wrangler deploy` でも可。
7. まず数日間の取得時刻・漏れ・配信元制限を監査し、モデルパリティ実装・端末同期・段階リリースへ進む。

## データと運用の注意

- プログラムJSONはAndroidが参照する `boatraceopenapi.github.io/api/v1/YYYY/YYYYMMDD.json` の公開日付フィードと同形式を期待。`closed_at` をJSTとして解釈する。この**低頻度更新の日付フィードは開催表と結果専用**とし、T-8の展示・オッズの代替には使わない。
- 取得不能は `failure_code` で記録。`UNAVAILABLE` は見送り (`SKIP`) と区別し、的中率・ROIの分母へ入れない。
- 当日/前日 `result_json` の再照合は結果・払戻表示の回復処理のみで、Model Aの選手履歴更新ゲートには接続していない。締切後の実データを事前特徴量に入れない。`UNFORMED` / `POSTPONED` / `CANCELLED` は勝ちレースと数えず、通常配当扱いにも変換しない。
- `POST` を含む外部書き込みAPIは提供しない。公開APIにはレース情報のみを返す。必要に応じてCloudflare側のレート制限とアクセス制御を追加。
- D1スキーマは **初期構築用**。本番データがある場合、後から `0001` を再適用してデータ移行するのではなく、追加のmigrationを作る。

## ローカル検証

```sh
cd cloud/forecast-worker
npm test
```

Node 22以上で実行可能。Cloudflareの認証やネットワーク接続を必要とせず、時刻制御・取引条件・HTTP応答・D1互換SQLiteのスキーマを検証する。

Python fixture の再生成にはリポジトリの既存 `scripts/v016_r4_player_history.py`、`scripts/v016_r2_model.py`、Python `numpy` と `lightgbm==4.6.0` が必要。通常の `npm test` 実行にはPython不要。

```sh
python cloud/forecast-worker/tools/build_python_model_a_history_fixture.py
python cloud/forecast-worker/tools/build_python_model_a_feature_fixture.py
python cloud/forecast-worker/tools/build_python_model_a_end_to_end_fixture.py
```

Cloudflare環境にこれらのfixtureをデプロイする必要はない。現段階では実レースのBUY/SKIPを返すことなく、入力契約を先に検証する。
