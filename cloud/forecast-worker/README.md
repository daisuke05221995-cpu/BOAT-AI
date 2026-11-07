# BOAT AI クラウド実行基盤（段階1：データ収集・監査・直前品質検証）

## 2026-11-08 Androidからの遠隔再取得指示（v0.18.29）

遠隔操作の最小範囲を `REFRESH_NOW` だけに固定した。D1 `0013_collector_remote_refresh.sql` に未実行1件/端末・3分期限・状態を記録する。既存の `COLLECTOR_INGEST_TOKEN` が未設定なら全経路503、欠落・不一致なら401、未知操作/余分な項目は400。全API `Cache-Control: no-store`。対象は5分以内に監査通信した最新の1端末だけ。コマンド重複は集約、連続発行は60秒制限。端末IDは公開しない。

- 1台目の `POST /v1/device-collector/remote/refresh` に `{"schema_version":1,"action":"REFRESH_NOW"}` を送る。Bearer認証必須。1台目の設定でも2台目と同じキーを**端末内暗号化**で保存。端末の常時取得モードはOFFのまま。
- 2台目の `GET /v1/device-collector/remote/next?device_id=UUID` はBearer認証必須。前面で約60秒間隔でポーリングし、許可された固定操作を受け取ったら既存の開催・出走・直前情報の再取得処理を開始する。受信後 `POST /remote/ack` で受付を記録する。`ACCEPTED` は**Androidで処理を開始した事実のみ**で、取得結果の成功証明ではない。結果は従来のheartbeatで監視する。
- 取得端末がオフライン、別画面、終了中、日付変更中の場合は自動操作しない。3分失効・新規コマンド実行履歴で重複防止。投票サイト・他のアプリ・Androidアクセシビリティ・スクリーン録画・ID/パスワード・自動舟券購入には**触れない**。
- **クラウド側の登録済み共有キーをAIに渡さない**。チャットからAIが直接操作を発行する連携は別の許可・監査付き工程。既存のCloudflare secret/Worker bindingsは変更しない。両端末ともv0.18.29に更新し、1台目にもキーを設定して初めて操作可能。古い2台目でも既存heartbeatは引き続き送る。

## 2026-11-08 2台目取得監視・通信停止判定（v0.18.28）

`GET /v1/device-collector/health` は認証不要の**読み取り専用・匿名集計**。`collector_device_heartbeat` で日付を跨いだ直近のサーバー受信時刻を調べる。5分以内なら `ACTIVE`、5分超なら `STALE`、一度も受信がなければ `NEVER_CONNECTED`。サーバーの判定時刻 `evaluated_at`、直近受信時刻・経過秒・最新開催件数・直近10分の端末数を返す。端末ID・共有キー・生オッズ・映像・購入記録は出さない。**日付が変わっても前日の通信時刻を確認する**ので、0時の境界で架空の切断を報告しない。

Android v0.18.28の通常利用側「予想」「設定」に2台目の状態カードを追加。アプリ前面表示中は最大2分間隔で更新、アプリ起動・復帰時は即時取得。監視APIのネットワークエラーは `UNKNOWN` とし、端末停止と混同しない。**Androidアプリを閉じている間に外部プッシュを送る機能ではない**。異常状態はAIの `UNAVAILABLE` / `SKIP` / `BUY` と無関係。既存v0.18.27の2台目は更新不要で、引き続き同じ共有キーで送信可能。


## 2026-11-07 2台目Androidからの取得監査通信（v0.18.27）

2台目の「常時取得モード」がONの間、Androidアプリは取得した**件数と端末受信時刻のみ**を約2分ごとに `POST /v1/device-collector/heartbeat` に送る機能を持つ。D1 migration `0012_device_collector_heartbeat.sql` は端末ごとの直近1行を保存する。`GET /v1/device-collector/status?date=YYYY-MM-DD` はデバイス識別子を公開せず、当日のアクティブ台数（直近10分）、直近の取得件数と受信時刻を表示する。

- 送信側とWorker側の**両方を設定するまで完全にOFF**。Workerには `COLLECTOR_INGEST_TOKEN` という32〜200文字のASCII英数字・`-`・`_`のSecretを登録。CLIなら `wrangler secret put COLLECTOR_INGEST_TOKEN`、Cloudflare管理画面なら該当Workerの「Settings → Variables and Secrets」からSecretとして追加。通常のGitHubリポジトリやチャットには値を貼らない。同じキーを2台目のBOAT AI「設定 → クラウド監査送信用の共有キー」に入力・保存する。
- 認証ヘッダーが無い/誤っている場合401、Secret未設定なら503。各payloadは最大2KiB、JST当日・端末時刻の近さ・項目集合・件数と時刻を検証し、未知の項目を拒否する。成功時202、`classification=DEVICE_RECEIPT_ONLY` と `eligible_for_forecast=false` を返す。
- 実購入履歴、オッズ値、展示値、選手ID、予想、アカウント情報は送らない。端末受信時刻は元サイトの観測時刻を証明しないため、**本経路を使って予想/BUY/SKIPを出してはいけない**。許諾済みのライブフィードによる別の本番予想経路は従来どおり必要。
- 端末側の共有キーはAndroid Keystoreで暗号化して保持、OSバックアップ/端末転送から除外。端末側をOFFにするかキー削除すれば送信停止。画面が前面にないと既存取得も停止する。利用者端末の購入記録・バックアップは従来のまま。


## 2026-11-07 Model A 前日までの履歴を自動確定する経路

`model-a-history-auto.mjs` + `0011_model_a_history_auto.sql` に、明示的に承認された全開催履歴APIから**連続した1日分だけ**取得し、全レースと6艇の着順・結果出典・時刻・締切前出走/展示/気象の生観測時刻を検証して、D1の固定BAH1履歴を1日ずつ更新する処理を追加。Workerの1分Cronで1回につき最大1日を処理し、失敗時は同日を1時間以上空けて再試行する。D1アクティブ履歴は完全検証・SHA照合・連続世代確認後だけ切り替え、不完全日は切り替えない。端末にある購入履歴やAndroid公式オッズ取得には触れない。

**本番運用設定はデフォルトOFF。** 以下すべてが、許諾と履歴完全性を確認済みの場合のみWorker環境へ設定する。

- `HISTORY_DAILY_FEED_URL`：HTTPSの全国確定結果・過去の締切前入力の保存済み観測証跡を返すAPI。`date=YYYY-MM-DD` を付与する。必要な場合は `HISTORY_DAILY_FEED_TOKEN` をsecret登録。
- `HISTORY_APPROVED_SOURCES_JSON`：配信元IDごとの明示的な承認リスト。キーは `coverage`,`schedule`,`result`,`roster`,`preview`,`weather` の6つ。例示の文字列を本番設定しても許諾・正しさの根拠にならない。
- フィード返却は `{ "manifest": { "date", "scheduledRaceIds", "expectedRaceCount", "scheduleSource", "resultSource", "confirmedAt", "coverageSource", "coverageStatus":"NATIONAL_ALL_VENUES_COMPLETE", "coverageConfirmedAt" }, "races": [...] }`。各SETTLEDの `race` は既存 `reconcileModelAHistoryDay` が要求するModel A入力と6艇全着順を持ち、`sourceEvidence` に観測元・`capturedAt`・`rosterObservedAt`・`previewObservedAt`・`weatherObservedAt`・`resultObservedAt`・`resultRecordId`・`resultRaceId`・`registrationNumbersByLane` が必須。**歴史を後から閲覧した時刻を締切前観測として扱わない**。現行の日付プログラムフィードや未監査の研究履歴ではこの条件を満たさない。
- `GET /v1/history-status` は認証済み履歴の最終日・今日の予想に使えるか・直近7日分の失敗理由だけを公開。選手の情報、トークン、実購入履歴、未検証予想は公開しない。

全国網羅性の宣言だけをモデル精度の保証とは扱わず、明示承認済みのcoverage sourceと公開日付フィードの既存スケジュール（ある日だけ）を突合する。日付フィード未収録の過去日も、認可済みcoverage manifestが必要。凍結履歴の9月23日から今日まで欠損せず昇格した場合だけ、前日の予想に使用できる。**現時点でこの履歴元は未設定で、実データの更新成功を示すものではない。**

## 2026-11-07 Model A shadow 接続（購入判定OFF）

`0010_model_a_shadow.sql` と `model-a-shadow.mjs` で、Cron のT-8/T-5試行から、**取得元が明示的に承認された出走6艇・展示・気象・120オッズ → 前日まで連続検証済みのD1履歴 → SHA検証済み固定LightGBM3本 → 120通りの純粋な予想確率**までを1回で実行できる経路を接続した。予想確率と各出典時刻は `model_a_shadow_attempt` に隔離して記録し、公開するのは `/v1/model-a-shadow?date=YYYY-MM-DD` の件数・理由別集計のみ。Android側の購入予想、既存の結果、実購入履歴、BUY/SKIPには一切反映しない。

- `MODEL_A_APPROVED_SOURCES_JSON` は、roster/preview/weather/odds ごとに事前確認済みの `source` ID配列を指定する必須の環境変数。JSON例: `{"roster":["approved-roster-id"],"preview":["approved-preview-id"],"weather":["approved-weather-id"],"odds":["approved-odds-id"]}`。**例のIDは許諾を意味せず、本番登録してはいけない。**
- 出走元のHTTPS `ROSTER_API_URL` と必要時 `ROSTER_API_TOKEN` を追加。既存 `PREVIEW_API_URL`/`ODDS_API_URL` は変更せず、各取得は独立して実施。日付フィードの候補出走表は観測時刻を確定できないため代用しない。
- 承認元だけでは十分でない。4取得元すべてに正確な実観測時刻・同一レースID・観測2分以内・全6艇ID一致が必要。締切後に計算が終わった場合も予想は保存しない。
- 固定D1モデルのbundle IDはAndroidの3本から確定した `c6d44a4bc9e2f27a4066c25ef0d375ec47055c566695ebfc30043c90433a4f2e`。任意のモデル差し替えや再学習は行わない。
- `model_a_history_active` のSHAをD1の全チャンクと再照合し、予想日**前日の暦日まで**完全に監査済みであることが必須。2026-09-23までの凍結履歴だけでは2026-11-07の予想は**必ず `MODEL_A_HISTORY_STALE` / `MODEL_A_HISTORY_NOT_ACTIVE`**。研究用11月履歴を認証なしに昇格しない。
- D1失敗、120確率の和が1でない、許諾/観測元の欠損、期限切れ等は`UNAVAILABLE`の監査記録のみ。`FORECAST_ONLY` は実購入可能なBUY推奨ではない。

現時点では本番用の直前情報提供元4種類と検証済み前日履歴が未接続であり、**実レースのshadow成功 / BUY/SKIP稼働を意味しない**。本番データでの同一入力Androidパリティを確認後に別工程で購入判定を審査する。

Androidを起動していなくても、Cloudflare Workersの定期実行でレース情報を蓄積するための基礎実装。**2026-11-06にCloudflareへ初期デプロイ成功**（GitHub Actions `42216781153`）。ただし、**クラウドAI購入予想は未実装**。`READY` を偽装せず、必要なモデル同等性検証が終わるまで `PENDING` / `UNAVAILABLE` とする。

## 実装済み

- `* * * * *` のCronがD1内の締切時刻を確認。**外部サイトに毎分アクセスしない**。
- 日本時間（JST）当日06:00〜23:59に開催スケジュールを1回取り込み。デプロイ遅延・午前のソース障害時も当日中に復旧し、失敗時のみ最大1時間ごとに再試行。過去の締切済み予想は生成しない。
- **締切8分前**に展示＋オッズの取得を開始。失敗時は**5分前に1回のみ**再試行。遅延時は締切前に限り実行し、締切後の後付け予想は禁止。
- 展示とオッズは**それぞれ独立して取得を試す**。展示が失敗しても認可済みオッズ取得元へのアクセスを省略せず、有効な片方だけの観測値と各失敗理由をD1監査に残す。ただし**両方揃うまでは取得完了にも予想完了にもならない**。Android端末内の既存公式オッズ取得は別経路で、変更しない。認可済みクラウド取得元の未設定を隠すものではない。
- 一連の取得をD1に記録し、Cronの重複起動でも同一レースの同時重複を抑止。公開APIは読取専用。
- 結果・払戻は締切20分後から別途取得。`0006_result_reconciliation.sql` により未確定結果は**15分間隔で再照合**し、翌JST日も前日分を回収する。旧 `result_stage=2` でも実結果が未記録なら再試行する。1 Cronで最大30R、日別フィードは1日1回の読込にまとめる。既存の確定結果は上書きしない。
- 3連単の通常結果は全成立組番を保持（同着の複数的中も欠落させない）。返還で「不成立」の場合は `UNFORMED`、明示的な「中止」「順延」は `CANCELLED` / `POSTPONED` として**通常の的中・払戻とは区別**する。出典IDが不一致、未知の状態、未掲載の結果は欠損のまま保持し架空の払戻を作らない。
- `GET /v1/health`、`GET /v1/forecasts?date=YYYY-MM-DD`。現時点では購入履歴・端末バックアップの送信は不要。
- 運用監査 `/v1/audit?date=YYYY-MM-DD`：Cron最終起動・完了時刻、T-8/T-5試行回数、取得/欠損、原因コード、結果回収率、BUY/SKIP確定数を**個別選手情報・ユーザーの購入情報なし**で確認できる。`0002_operational_audit.sql` が試行履歴・heartbeatを永続化する。結果は `settled` / `unformed` / `postponed` / `cancelled` / `legacy_settled` / `unresolved_due` に分け、再取得失敗コードも集計する。
- `0008_program_roster_candidate.sql` で、当日の日付フィード取り込み時に**6艇の出走登録番号・全国勝率等の形だけ**を検査し、診断用の別テーブルに記録する。レースID/6艇の重複・欠損・締切後の取り込みを拒否し、日別監査の `program_roster_candidate` に件数・原因を表示する。取得元の実観測時刻・利用許諾は未検証なので、通過しても **`SHAPE_ONLY_UNVERIFIED`（予想利用不可）** とする。生の展示・結果は候補へコピーせず、Android APIにも出さず、Model A/BUY/SKIPには接続しない。既存の開催・結果収集を維持する。
- `0009_six_finish_candidate.sql` は結果確定時に、**全6艇の選手登録番号と1〜6着の順列**が同一レースの公開結果内で一致するかを別テーブルに記録する。判定 `SHAPE_ONLY_UNVERIFIED` は**全開催網羅/観測元時刻/履歴確定を保証しない**。欠場・同着・着順未掲載などで6着順を確定できない場合は `UNAVAILABLE`、順延/中止/不成立などは `NON_SETTLED` として分離する。結果・払戻保存そのものは変更しない。`GET /v1/audit` と定期監査Actionには数・欠損理由のみ公開し、候補の選手IDや着順をアプリへ返さない。前日までのModel A履歴へは**反映しない**。
- `model-a-live-input.mjs` に本番接続前の**純粋な直前入力統合ゲート**を実装。オペレーターが外部で利用許可を確認した取得元の明示的なallowlistを要求し、出走・展示・気象・オッズを**同一レースID・締切前・観測2分以内・全6艇の選手登録番号一致・120オッズ完備**で照合する。成功時のみModel Aの特徴量入力形式に組み立てる。既存の出走表日付フィード、出典名の自己申告、後付け結果だけでは承認にならない。**Worker Cron・API・Model A実行やBUY/SKIPには未接続**。提供元許諾、前日履歴完全性、Android実レースパリティを確認するまで無効のままにする。
- `history-gap-diagnostic.mjs` は既存の日付結果フィードと研究用BAH1の選手出走日数を**読み取り専用**で比較。3連単払戻が確定したレース、全6艇の結果登録番号＋着順まで確認できたレース、研究履歴へ入ったレースの3つを分離する。BAH1はレースIDを持たないため、選手数から推定する候補レースは「疑い」に留める。`model-a-history-gap-readonly.yml` は2026-11-06の**同じ既存日付フィードを1回取得**し、監査JSONとActions Summaryを保存する。2025年の未開封holdoutやD1の履歴/予想には触れず、公式の全国網羅性を証明したとは扱わない。
- 同じ履歴差診断は `invalid_six_race_details` と `invalid_finish_raw_code_counts` に、全6着順を満たさないレースのIDと原文の着順コードだけを記録する（選手名は出力しない）。原文コードの意味を推測で確定したり、結果の観測時刻や認可済み取得元の代わりにしたりしない。**診断で見つけたケースを自動的に `EXCLUDED_TERMINAL` に変換しない。**
- `model-a-daily-reconcile.mjs` は、日別の全レース照合に**証拠付き `EXCLUDED_TERMINAL`** を追加。全6着順が成立しない確定結果を、理由（例：順位が6通り揃わない）とレースID・配信元・実結果の取得元観測時刻・記録IDが揃う場合に限り**更新対象外として件数計上**する。締切前観測、別レース、根拠欠損、無理由の `SETTLED` 失敗は拒否。通常の6艇成績も補わない。実日付の除外12件を自動昇格するコードではなく、**独立した全国網羅性と個別の結果根拠が確認できた将来のマニフェスト入力向け**。D1の履歴活性化・BUY/SKIPは変えない。
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
- 通常の公開APIは読み取り専用。例外として `POST /v1/device-collector/heartbeat` は共有キー認証で**監査件数のみ**保存し、予想・オッズ原本・購入履歴の書き込みは提供しない。必要に応じてCloudflare側で追加のレート制限を設定する。
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
