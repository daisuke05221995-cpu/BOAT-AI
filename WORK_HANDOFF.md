# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`
安定公開版: `v0.15.3`

## Work上限・停止時の最重要ルール

Workの使用上限、タイムアウト、コンテキスト不足などで継続できなくなりそうな場合は黙って終了しない。
終了前に必ず有効な変更をcommit/pushし、このファイルへ現在位置・Run ID・次の具体的1手を保存する。
その後ユーザーへ通常チャットへ戻るよう案内する。

復帰案内:
> Workの上限に近づいたためGitHubへ状態を保存しました。通常チャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて」と送ってください。

## 並行開発ルール

通常チャットとWorkを並行利用してよい。ただし同じ本番ファイルを同時編集しない。

### 通常チャット担当
- Android本体
- UI / 通知 / 履歴 / 結果 / 損益
- 本番ロジックへの最終統合
- Release判定と公開
- `app/`、`PROJECT_STATUS.md`、Release関連を優先管理

### Work担当
- v0.16予想モデル研究専用
- 原則として `scripts/v016_*`、`.github/workflows/v016-*`、`data/v016_*` の新規ファイル中心
- Android本番ファイル、versionCode/versionName、Release workflow、`app/src/main/assets/value_strategy_model.json` を勝手に変更しない
- 研究結果は本番へ自動昇格しない
- Run ID、採否、次作業をこのファイルへ残す

### GitHub Actions担当
- 年別・モデル別・パラメータ群の重い計算をmatrixで並列実行
- 2023 / 2024 / 2025など独立可能な年は並列化する
- 同じcacheを使う探索はArtifact再利用で再計算を避ける

## v0.16予想モデル方針

最終目的は実運用で利益を保証することではなく、過去検証上で十分な再現性を持つ候補だけを本番候補にすること。

### 年間リリースゲート
- 月単位のマイナスは許容
- 最終評価では12か月合計ROI 105%以上を必須
- 年間購入件数が少なすぎる候補は不可
- 単発の異常高配当だけで成績が成立していないかを別指標で監視するが、高配当そのものは排除しない
- 候補を完全固定するまで最終holdoutを開かない
- 最終holdoutを含む年次評価でROI 105%未満なら不採用

### 2系統で作る
1. `CORE BUY`：現在進行中の低〜中配当寄り・期待値重視。まずこちらを最後まで走り切りBaselineとして固定する。
2. `LONGSHOT BUY`：CORE固定後に開始。従来SKIPだったうち「荒れそうで見送った」レースを対象に、穴狙い6〜12点程度まで許容する。

最終的には `CORE BUY / LONGSHOT BUY / SKIP` の3分類を目標とする。
LONGSHOTでは人気薄を無条件に買わず、展示変化、進入ズレ、1号艇信頼度低下、モーター差、風波、オッズ歪み等から荒れレースを抽出する。
COREとLONGSHOTは別々の成績も保存し、最後に合算年間ROIも評価する。

## v0.15.3 公開完了

- versionCode: 21
- versionName: 0.15.3
- Release commit: `446b7e3005a18b592d88d2726cc9abb3dd3c8d95`
- Release Run: `35863168523` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.3`
- APK: `BOAT-AI-v0.15.3.apk`
- APK SHA-256: `ea8992abdf28b45a919e99940381165c10845e4b28d5051a83ecc6ab4c3771bf`

Release WorkflowでUnit test / lint / signed APK / signature verify / GitHub Release公開まで成功。
Debug検証 Run `35862849909` もSUCCESS。

## v0.15.3 重要修正

ユーザー実機で結果タブの「事前予想」が多数 `記録なし` だった原因は、v0.15.2の5分前保存が購入推奨アラートONに依存していたこと。

v0.15.3で予想履歴保存とユーザー通知を分離した。

- `PredictionTrackingScheduler.kt` 追加
- 全レース事前予想トラッカーは通知ON/OFFと無関係に常時予約
- 毎朝6:25 JST、アプリ起動時、端末再起動/アプリ更新後に追跡復旧
- 締切前に同じPredictionEngine / BetStrategy / LearningStoreで予想
- BUY/SKIP両方の買い目をPredictionHistoryへ保存
- 結果約20分後に自動settle
- 自動記録サービスの通知は無音・無振動・低優先度
- BUYユーザー通知だけは従来どおり「購入推奨アラート」ON/OFFに従う
- 既存アラート側が先に `legacy-final-v1` / `value-v1` を保存していれば追跡側は重複評価を避ける

過去の未保存レースを結果後に後付け生成しない。2026-09-23の桐生等の `記録なし` は履歴の正確性のため残す。

## v0.15.2から継続する表示

- レース詳細AI購入判断直下の結果カード
- 結果 / 払戻 / 事前予想 / 的中・ハズレ / 想定払戻
- 損益の日別カードで全予想（BUY+SKIP）を先頭表示
- 購入推奨だけの仮想成績も別表示
- `締切前保存 X / 当日結果 Y` で保存漏れ可視化

## 本番予想ロジック

研究用Value Strategy / race-softmaxは本番へ入れていない。
`app/src/main/assets/value_strategy_model.json` は存在せず現行安定ロジックを使用。

不採用研究:
- v12: 2026 ROI117.3%だが2023 72.0% / 2024 45.5% / 2025 56.3%
- rich race-softmax Run `35839229134`: 2024 ROI90.1%、2025固定59.2%

2025-10-01〜2025-12-31 Q4最終holdoutは未開封。

## 次の具体的1手

1. CORE BUY側の研究を年間ROI105%ゲート前提で完走させる
2. COREをBaselineとして固定する
3. その後LONGSHOT BUY研究を別系統で開始する
4. CORE / LONGSHOT / 合算の年次成績を別々に検証する
5. 候補固定後だけ最終holdoutを一度開く
6. 実機v0.15.3では翌開催日の事前予想自動保存も確認する

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`

## Work研究: v016 CORE r1（2026-09-23）

- Work分担厳守: Android/本番/Release/PROJECT_STATUS.mdは未変更。並行更新を検知したため最新mainへ研究ファイルのみ再適用。
- 現在位置: scripts/v016_core_research.py / v016_core_test.py / .github/workflows/v016-core-research.yml / data/v016_core_protocol.json を実装。日付/Q4拒否・会計・改変・欠落matrixの6テスト成功。
- 初回確認: b9687da、最新Run 35866413097 SUCCESS、進行中/queuedなし。公開版は通常チャット管理。
- cache Run 35833959070再利用、3年並列準備→2年×3モデル×2パラメータ群のscreen。144候補を2023/2024で選び、1候補固定後だけ2025へ適用。
- 年間ゲート: 12か月ROI>=105%、年360購入以上。月次赤字許容。5〜9月screenは年間成績ではない。
- Run ID: このpushで起動後に追記。まだ研究結果/採用候補なし。Q4未開封/自動開封機能なし。LONGSHOTは適格CORE固定まで保留。
- 次: Actions結果・固定候補2025確認→通過時のみ欠損月の年間検証、オッズ時刻監査。失敗時は後付け閾値緩和せず不採用を保存。

## 最新Work研究チェックポイント — 2026-09-23 CORE r1結果確定

**現在位置: CORE r1のscreenと監査を完了。採用候補0件。年間105%以上・複数年再現性は未検証であり、CORE完成ではない。**

### 実施内容とRun

- v016専用研究コード、matrix workflow、事前登録プロトコル、全候補監査を追加。
- CORE Run `35868298662`: **SUCCESS**。3年分のキャッシュ準備→2023/2024×3モデル×2条件群の12並列ジョブ。144候補を比較。
- 初回監査Run `35869208371`: **SUCCESS**。
- 監査の「年間購入数未評価」と「購入0件」を区別する修正後Run `35869447339`: **SUCCESS**。
- 6件の会計/holdout/改変/欠落matrixテストおよび年間ゲート境界/カバレッジ/時刻テスト成功。
- 研究実装commit `4888d3e71d052d40f31e00fa10478af3aa33c72e`、監査実装 `6dc2d825498b22a1338f9f7eebe9019a3072a9a5`、監査表示修正 `a4a22c3bf8d682efba9fca94a239d46f36757e71`。
- 実行失敗はなし（最初のpushは通常チャット更新によるnon-fast-forwardで安全に拒否され、最新mainへ研究ファイルだけを再適用して成功）。

### 採用/不採用理由

- 両年で150購入以上を満たすのは144候補中48、screen通過0。
- 十分な件数を持つ代表的最良条件（5〜9月限定）:
  - 市場べき補正: 2023 ROI75.55%（16,942購入）、2024 ROI78.48%（16,903購入）。
  - 既存モデル混合: 2023 ROI66.19%（438購入）、2024 ROI68.92%（365購入）。
  - 縮約補正: 全候補で購入件数不足。
- 108.21% / 235.33%の少数候補は28 / 15購入かつ各年1的中、払戻100%が1件依存で不採用。
- 2025は候補がないためこのラウンドの候補成績評価を実施せず、confirmationはNO_CANDIDATE。
- **部分期間screenでの不採用であり、年間ROIの不合格を実測したという意味ではない。年間評価は未完。**
- CORE固定に至らないためLONGSHOT研究と3分類最終評価は未着手。SKIPモデルを「合格CORE」と扱うこともしない。

### データ監査と未完事項

- 元cacheは各年2〜9月のみ。1月・10〜12月が欠ける。
- オッズmirrorに2022年なし、2023年は1/16開始（350日）。2024年は366日分の元ファイルがあるが通年cacheはまだ作成していない。
- 提供元scraperは前日/過去日取得。締切5分前の時刻証跡が既存cacheにないため、そのまま実運用再現性を証明できない。
- 別ソースBoatraceCSVは取得日時/締切時刻付きod3があるが保存年は2026年のみ。複数年通年の代替にならない。
- 途中検討した「2022学習→2023/2024通年検証」は現在のmirrorでは実行できず、未実行として保存。
- 本番昇格はfalse。Android/app/バージョン/Release/PROJECT_STATUS.md/現行ロジックは一切commit対象にしていない。
- **2025-10-01〜2025-12-31は未開封。自動開封コードもなし。**

### 保存先

- `data/v016_core_research_report.md`: 日本語の結果・限界・再開手順
- `data/v016_core_audit.json`: 144候補すべての年別数値・不採用理由・cache監査
- `data/v016_data_source_audit.json`: 元データ期間・取得時刻・代替ソース監査
- `data/v016_core_protocol.json` / calibration / screen / candidate / confirmation.json
- 元cache Run `35833959070` のArtifactは2026-10-23期限。研究prepared/screenはRun `35868298662`、2026-12-22期限。重い再計算前に再利用する。

### 次に行う具体的な作業

1. 上記2つのauditと日本語reportを読み、部分期間と年間成績を混同しない。r1を後付けで閾値緩和しない。
2. **2024年の通年cacheを研究専用ファイルで作る。** 未収録1月/10〜12月を追加し、1月の学習は2023年以前に限定。既存2〜9月cacheとの一致・欠損/中止/返還の母集団差を確認する。これは可能な次作業であり、今回未実施。
3. 2023年欠損15日と学習用旧年データの別ソースを調査。欠損期間を0購入/SKIPとして埋めて年次合格にしない。
4. 取得日時付き2026年od3で実運用オッズとの差を別検証し、年次の代用にしない。
5. 新CORE候補は新しい事前登録プロトコルで学習/選択/確認を分離。年次ゲート105%以上・年360購入以上、月次赤字許容。CORE固定後にLONGSHOT、両方の候補/パラメータ完全固定後にだけQ4を一度評価。
6. 採用候補でも通常チャット側の最終確認まで本番統合・Releaseしない。

復帰案内: **通常チャットへ戻ってBOAT AIの続きを依頼してください。**

## 継続チェックポイント: 2024通年検証を実装（上記「未実施」の更新）

- 安全に続行可能な2024通年拡張をそのまま続けて実装した。終了ではなく途中保存。
- 新規 `scripts/v016_annual2024.py` / test / `v016_kfile_records.py` / `.github/workflows/v016-annual2024.yml` / `data/v016_annual2024_protocol.json`。
- 2024年2〜9月は元cacheの値を完全再利用。1月モデルの学習は2023年5〜9月のみ。10〜12月は評価月より前の2024年レコードのみ。
- 同じ144条件を6ジョブで並列年次評価。旧5〜9月の会計との完全一致を必須チェック。Q4 2025は取得せず、2025年間cacheは読み込み前に拒否。
- 3件の年度境界/12か月/会計テスト成功。実処理はこのpush後のActions（Run IDは起動後追記）。
- 次: cache生成→6並列screen→年次集計の完了を確認。結果が `data/v016_annual2024_result.json` にcommitされる。年次105%未満ならr1不採用を確定。通過時も複数年・時刻監査が必要で自動採用しない。

### 2024通年Run起動済み（最新の実行位置）

- Run `35870380669`: IN_PROGRESS。https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/35870380669
- 実装commit `fff90a33eb362ffe34b7c076fe9bc60bbde550b3`。
- 現在は共通2024通年cache生成中。完了後6条件群をmatrixで並列screenし、集計を `data/v016_annual2024_result.json` へ自動commitする（本番更新なし）。
- 次の1手: このRunのbuild/screen/aggregateの状態を読む。失敗なら失敗jobのログを確認しv016専用ファイルだけ修正。成功なら年次105%/購入件数/高配当依存の結果を読み、上の部分期間判定を更新する。
- まだ年次ROI数値は出ていない。Q4 2025未開封、LONGSHOT未着手。

## 最新確定結果: 2024年通年まで完了（上記IN_PROGRESSを更新）

- **Run `35870380669`: SUCCESS**。build、6並列screen、aggregateすべて成功。現在この研究に実行中Runなし。
- 2024-01-01〜12-31の通年cacheは52,179レース（対象確定済み6艇53,225、98.03%、月別95.87〜99.43%）。
- 未収録の1月/10〜12月を追加。全144条件で既存5〜9月の購入判断・会計がr1と完全一致。年度境界/12か月/会計の3テスト成功。
- 年間360購入以上は48条件。**年間ROI105%以上等の通過候補0件**。この144条件は通年ゲートでも不採用。
- 十分な件数を持つ最高ROI: **94.081871%**、仮想購入1,710レース、投資2,052,000円、払戻1,930,560円、損益 **-121,440円**。
- 最良条件: blend0.35、minEV1.0、minProbability0.01、maxOdds20、maxPoints3（4と同一結果）、budget1200。
- 市場補正系の最高ROI77.73%、縮約補正は件数不足。月次赤字を理由に棄却せず12か月合算で判断した。
- 年次結果 `data/v016_annual2024_result.json`、日本語report `data/v016_core_research_report.md`、機械可読現在地 `data/v016_research_status.json`。
- 次回の共通cache: Run `35870380669` / Artifact `v016-annual-cache-2024` / ID `10755851267` / 約198MB / 2026-12-22期限。再取得・同じ月次学習は不要。
- 元データ時刻・中止/返還・母集団差の制約は継続。単年だけで複数年再現性を合格としない。
- **CORE適格候補を固定できなかったため、LONGSHOT/3分類検証は未着手。Q4 2025は未開封。本番変更なし。**

### 次の具体的1手（旧「2024 cache作成」を置換）

1. 上記status、年次result、日本語reportを読む。144条件は不採用として固定し、同じグリッドを再実行しない。
2. 新CORE仮説を事前登録する場合、今回の失敗を踏まえ「過去に見たROIへ閾値を合わせる探索」を繰り返さず、事前特徴量/取得時刻を監査した新しいモデル設計から始める。今回の市場/既存モデルの確率補正だけでは105%を達成できなかった。
3. 新研究で必要なデータのみ補完。2024通年cacheは上記Artifact再利用。2023欠損15日/旧年訓練期間/2026時刻付きod3はdata source audit参照。
4. 年次105%以上で固定できるCOREを得た後にLONGSHOTを開始。両者完全固定後のみQ4を一度使い、通常チャット側の最終確認前に本番へ反映しない。

**研究1巡と2024通年評価は完了、アプリとして採用できるCORE/LONGSHOTの完成は未達。**
通常チャットへ戻ってBOAT AIの続きを依頼してください。


## v0.16 CORE r2開始: 新しい条件付き着順モデル（2026-09-23）

- 現在位置: 旧144条件は不採用確定のまま、新仮説3種×モデル容量2種を事前登録し実装。通常チャット側mainの変更を保持して研究専用ファイルのみ追加。

- fundamental: 展示・進入・機力/ボート・選手成績の相対差から条件付き1/2/3着確率を学習。学習器に市場特徴量を入れない。
- residual: 市場の条件付き確率を基準に、1号艇の弱さ・人気集中・事前特徴量で残差を学習。
- place: 1着の市場確率を固定し、条件付き2/3着だけ補正する。
- 各7葉/15葉の2容量。2023年5〜7月学習、8月loglossで早期停止、9月screen。2024通年は固定後評価（探索済み開発年であり最終holdoutではない）。
- 買い方は1条件固定（1200円、最大3点、minEV1.10、minP0.01、最大40倍）。年間ROI105%以上、購入360以上、的中30以上、最大払戻比率25%以下、最大1的中除外ROI100%以上。月次赤字は許容。
- programs/previewsの事前情報whitelistを固定ソースcommitから取得。風向/級別はカテゴリとして使用。2024の既存通年Artifactを再利用し、オッズ/月次旧モデルの再計算なし。特徴量sidecarは年別matrix、学習/評価はモデル別matrix。
- 6テスト成功（確率連鎖、市場priorの二重加算防止、結果混入防止、Q4封印、勾配、キー不一致）。実データ処理はActionsで実行する。
- Run ID: このcommitで起動後追記。現段階では新モデルのROI未測定、採用候補なし。
- 次の具体的1手: v016-r2 Runを確認し、features→fit-screen→annual→aggregateまで監視。失敗はv016_r2専用ファイルで修正。合格候補があればモデルSHAと買い方を固定して2025 Q4前の独立確認へ進む。全不合格なら6モデルを不採用記録し同じ閾値探索はしない。
- 2025全期間を現コードでは読取拒否。Q4未開封、LONGSHOT未着手、本番反映なし。取得時刻・中止/返還・除外母集団の制約は継続。

### r2起動チェックポイント

- Run `35875673825`: IN_PROGRESS。https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/35875673825
- 実装commit `63cf47e9cd44f0f0c34facc3a9cc79a35128a954`。まだ成績未測定、採否未確定。
- 次: このRunのcheck、features(2023/2024)、fit-screen(6)、annual(6)、aggregateの状態を確認し、完了まで続行する。

## r2通年結果確定・保存済み予測の監査へ

- Run `35875673825`: SUCCESS。6テスト、2年の特徴量作成、6学習/screen、6年次評価、集計すべて成功。
- 新6モデルは全不採用。fundamental-small/mediumは2024 ROI79.93%/80.12%、購入33,198/34,652。residual-smallはROI139.79%だが47購入・3的中、最大的中比率40.94%、最大1的中除外ROI82.55%で不採用。residual-mediumは65購入・ROI47.38%。place両方は購入0。
- 2024特徴量有効52,008/52,179レース。欠損171レースは事前ルールによりSKIP。2023年9月は4,078/4,079有効。
- 2023年9月でもresidualの高ROIは1的中依存。複数年収益再現性の合格には程遠く、2025独立確認を行う候補なし。2025は全期間未追加参照、Q4封印、LONGSHOT未着手。
- 追加実施: 保存済み予測と特徴量Artifactだけを再利用する12並列校正監査。モデル再学習・買い方再探索はしない。日単位bootstrapで市場に対するlogloss差を確認し、予測期待ROIと実績ROIの乖離を記録する。
- 次の具体的1手: `v016-r2-audit.yml` の新Run（起動後追記）を確認して監査結果を取得。結果/制約/次研究の根拠をreportとこのファイルへ保存する。

### 校正監査Run起動

- Run `35876699180`: IN_PROGRESS。https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/35876699180
- 実装commit `450ededf920fef483983d2fa179fac25934afc52`。r2本体Run `35875673825` はSUCCESSで全6モデル不採用確定。
- 次: 12並列auditとaggregateの成否を確認し、`data/v016_r2_audit.json` を読む。


## 最新確定チェックポイント: r2の6モデル・校正監査まで完了

- 現在位置: **新CORE 3仮説×2容量の研究一巡を完了。全6モデル不採用。CORE完成・複数年収益再現性の合格は未達。** 上のr2 IN_PROGRESS記載はこの項目で更新。
- 本体Run `35875673825`: **SUCCESS**。年別特徴量・6モデルscreen・2024通年評価・集計完了。
- 監査Run `35876699180`: **SUCCESS**。2023/2024×6モデルの12ジョブとaggregate完了。新たな学習/閾値探索なし。購入件数・投資・払戻を全12結果で再照合。
- 今回の研究Runに失敗なし。6つの数学/境界/結果混入防止テスト成功。研究の実行成功とモデル採用合格を混同しない。
- 採否: fundamental-small/mediumは年次ROI79.93%/80.12%（購入33,198/34,652）で不採用。residual-smallは139.79%でも47購入・3的中、最大1的中除外ROI82.55%で不採用。residual-mediumは47.38%・65購入。place両容量は購入0。候補を固定できず2025確認には進まない。
- 校正監査: fundamental-mediumは予測期待ROI132.62%に対し実績80.12%。残差補正は両年でloglossを小幅改善（2024 smallの市場との差-0.007692、日単位bootstrap95%区間-0.008563〜-0.006841）したが十分な購入機会にならず、収益再現性を示せなかった。
- 保存先: `data/v016_r2_result.json`（全6モデル×2023screen/2024月次・年次）、`data/v016_r2_audit.json`（期待/実績の校正・日単位bootstrap）、`data/v016_r2_report.md`（日本語詳細）、`data/v016_research_status.json`（現在地）。
- 再利用: Run `35875673825` の `v016-r2-features-2023` ID `10757750512`、`v016-r2-features-2024` ID `10756333376`。同Runに6モデルと年別予測Artifact。2026-12-22期限。元2024通年Artifact `10755851267` も保持。重い特徴量取得/旧月次モデル学習は再実行不要。
- Q4 2025未開封、今回2025全期間を追加参照していない。LONGSHOT/3分類未着手。本番app/、versionCode/versionName、Release、PROJECT_STATUS.md、本番モデルは変更していない。

### 次の具体的1手（r1/r2の閾値再探索はしない）

1. 上記r2 report/result/auditと最新Runを読む。2023年9月はscreenであり年間再現性の証明ではない。
2. 次仮説r3は「固定3か月学習ではなく、評価時点より前のデータで四半期ごとに更新して校正を改善できるか」。**最初に2024 Q1〜Q4の学習/validation/評価の分割manifestを研究専用ファイルに作り、train最終日 < 評価開始日の境界テストを実装する。** 固定買い方と105%/360購入ゲートは緩和しない。
3. 2023年10〜12月はr2 sidecarにないので学習期間の欠損を明示。2024全四半期の評価データは既存sidecarを使い、モデル/四半期をActions matrixで並列化する。これは次仮説であり、まだ実装・検証していない。
4. 採用COREを固定できるまではLONGSHOTへ進めず、Q4は開かない。時刻監査・除外母集団の制約は継続。通常チャットの最終確認なしに本番統合しない。

通常チャットへ戻ってBOAT AIの続きを依頼してください。


## r4事前登録（2026-09-24）

- 初回確認main `aa1fde295e94635fad64a9e57969b74c73a08b02`。最新v016 Run `35933816549` SUCCESS、進行中/queuedなし。Androidはv0.15.11、本番には触らない。
- r1〜r3は不採用確定。r4「2025年中心・選手ID×コース×展示反応」を `data/v016_r4_protocol.json` にコード/履歴構築前に事前登録。
- 2024既存通年cacheは履歴seedに再利用。2025 Jan-May学習、Jun logloss調整、Jul-Aug開発評価。Sepは候補モデル/買い方/SHA固定後だけ確認し、Q4は常にURL生成前に拒否。
- 3モデルcurrent/history/reactionで増分価値を検証。候補はreactionのみ。登録番号はlookup専用、同日の特徴量を全て生成してからその日の履歴を更新。実ST/実進入は使わない。
- 現在位置: protocolのみ登録、r4実装/Run/成績は未完。次: player history accumulatorとリーク防止テスト→年別raw cache→時系列feature cache→モデル別Actions matrix→品質gate→固定買い方→条件を満たせばfreeze後Sep確認。
- 年次105%/360購入ゲートは維持。Jul-Aug/Sepだけで年間合格としない。Q4未開封、LONGSHOT未着手、本番変更なし。


### r4実装チェックポイント

- protocol事前登録commit `b97e3969b04953435a93cccf10556f27f85bbadd` 後に研究専用コードを実装。
- `v016_r4_features.py`: 固定commit programs/previews/results/odds、2024既存年次cacheの結果再利用、2025 Jan-Augのみ取得。9月はfreeze必須、Q4は許可経路なし。
- `v016_r4_player_history.py`: 登録番号×previewコースの履歴、30/60/90/180日成績、階層縮約、本人比展示/ST、コース別展示反応。同日全snapshot完了後に結果更新。
- `v016_r4_model.py`: current/history/reactionの3比較、登録番号・市場情報を予測入力へ入れない。Jun loglossで学習停止とtemperature固定。
- `v016_r4_evaluate.py`: まずJul-Augの確率増分gate、その後固定2policyのみ。候補時はprotocol/コード/モデル/履歴状態/買い方をSHAでfreezeしSepのみ確認。年次gateは常に未評価表示。
- 14テスト成功（r4 8、確率エンジン6）。同日/未来ラベル改変、同日順序入れ替え、ID/オッズ/結果入力排除、実ST/実進入の未使用、NPZ結果読込前Q4拒否などを確認。
- Run ID: このpushで起動後追記。実データcache/学習/採否はまだ未完。
- 次の1手: v016-r4 Actionsのcheck→raw 2年並列→history-features→model 3並列→select→候補時のみseptember→publishを監視。失敗は研究専用ファイルのみ修正し、再計算はcacheを再利用する。

### r4 Run起動済み

- Run `35940538399`: 起動済み（起動直後QUEUED）。https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/35940538399
- 実装commit `fdc32e27cf58ddcad69cffa497f6c1be79f2d5b0`。
- 現在位置: check→年別raw準備待ち。実測成績/採否はまだ未確定。
- 次: このRunのジョブを確認し、cache取得率・history chronology・3モデル比較・品質gateまで完走。成功/失敗と採否を追記する。Q4は未開封。

### r4初回Runの取得処理修正

- Run `35940538399`: FAILED（raw2025の結果/出走表ID照合）。checkとraw2024はSUCCESS、学習以降SKIPPED、9月/Q4未参照。
- raw2024は52,179レースを保存済み。次RunはこのRunの `v016-r4-raw-2024` を再利用し、再取得しない。
- 非完走/中止など着順1〜6が揃わない結果は研究対象外とする判定を、ID照合より先に実施する。通常6艇完走のID不一致は引き続きfatalとし、日付/場/R/IDの診断情報を追加した。基準緩和やIDの強制付け替えはしない。
- 当該境界テスト追加後r4 8テストSUCCESS。次の1手: 修正Runのraw2025を確認し、不一致が残る場合は記録されたrace keyで元データを照合する。

### r4再実行チェックポイント

- 修正Run `35940833546`: IN_PROGRESS。https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/35940833546
- commit `da8248a2692e611f50cdf0affc8e1b7731065228`。checkと2024Artifact復元はSUCCESS、2025raw実行中。初回Run `35940538399` はFAILEDとして保持。
- 次: raw2025のログを確認し、通常完走のID不一致なら元race keyで原因確認。通過したら履歴/特徴量→3モデル比較へ続行。まだr4モデル成績なし、Q4未開封。

### r4データ準備・履歴構築完了

- Run `35940833546`: check/raw2024/raw2025/history-featuresすべてSUCCESS、3モデル学習中。
- 2025 Jan-Augは35,505 eligible settled six-boat races、事前特徴量有効35,483（22欠損）。各月95%coverage gate通過。sourcePrograms 38,736、対象外の中止/非完走等3,231は月別ledgerに記録。
- 履歴更新は2024 seedから2025 Augまで、登録番号1,670人。同日更新なし・全raceのhistory_through < dayを検証。
- `v016-r4-features` Artifact ID `10784104679`（Run `35940833546`）。train/development NPZ、history_state、feature_metadataを再利用可能。モデル不具合等の再実行でも年次source取得/履歴計算はcacheから復元。
- 初回のID不一致は通常6艇完走ではなく対象外結果の照合順で発生。修正後、通常完走のID照合を維持して全期間を通過。無視/強制変換は行っていない。
- 次: current/history/reactionの3モデルを完了させ、Jul-Aug増分価値gate→通過時だけ2固定policyを評価。9月/Q4は未参照。


## r4最新確定結果 — 2026-09-24

- **現在位置: protocol事前登録→player history→feature cache→3モデル比較→開発期間の固定2policy検証まで完了。r4は不採用、CORE完成ではない。** 以前の「未実装/実行中」はこの項目で更新。
- 初回Run `35940538399`: FAILED（raw2025のID照合順序）。raw2024は成功。修正後Run `35940833546`: **SUCCESS**。check、raw両年、履歴、3モデル、select、publishすべて成功、Septemberは候補なしでSKIPPED。
- protocol commit `b97e3969b04953435a93cccf10556f27f85bbadd`、実装 `fdc32e27cf58ddcad69cffa497f6c1be79f2d5b0`、取得処理修正 `da8248a2692e611f50cdf0affc8e1b7731065228`。モデル/閾値の後付け再探索なし。
- 2024 seed有効52,008、2025 Jan-Aug有効35,483、1,670選手・履歴87,491レース。同日混入0。14テスト成功。年別raw・モデル別計算はActions matrix、履歴は日付依存順でActions実行。
- 学習Jan-May 21,391レース、Jun調整4,509、Jul-Aug評価9,583。9月はこのr4では未取得/未評価。Q4 2025は未開封。
- 確率品質: current logloss3.809066 → history3.797649 → reaction3.796222（市場3.716979）。reaction vs current差 -0.012843、日単位bootstrap95% -0.018526〜-0.007704。Brier/ECEも改善し、事前登録の品質gateはPASS。
- ただしreaction vs historyの純追加差は -0.001426、95% -0.003192〜+0.000386で0を跨ぐ。本人比展示反応だけの効果が確定したとは言わない。
- Jul-Aug固定core policy: **7,265購入・581的中、ROI81.12%、損益-1,646,180円**。最大1的中除外ROI80.57%、予測期待ROI134.24%。
- Jul-Aug固定reaction selector: **2,888購入・230的中、ROI82.05%、損益-622,160円**。最大1的中除外ROI80.68%、予測期待ROI134.63%。
- 不採用理由: ROI105%未達、最大1的中除外ROI100%未達、期待/実績差52〜53ptで校正gate不合格。件数不足による見せかけではなく、十分な購入件数でマイナス。候補freezeはnull、LONGSHOT未着手。
- **上のROIは2025 Jul-Augの2か月であり年間成績ではない。** Jan-Junを学習/調整に使うため、将来Q4だけ開いても2025全12か月の独立検証にはならない。年間105%/360購入・複数年再現性は未達。
- 保存: `data/v016_r4_report.md`、`data/v016_r4_result.json`、`data/v016_r4_feature_audit.json`、`data/v016_r4_frozen_candidate.json`、`data/v016_research_status.json`。月別・previewコース別・履歴件数別・本人比展示別・1号艇弱化別成績もresultに保存。
- 再利用Artifact: Run `35940833546` / `v016-r4-features` ID `10784104679`（train/development NPZ、履歴state、metadata）。raw2024 ID `10785285539`、raw2025 ID `10785505050`。モデル/予測3種も同Runにあり、期限2026-12-23。再取得/履歴再計算は不要。
- オッズの締切5分前時刻証跡は未確認。sourcePrograms38,736から対象外3,231、対象内の事前情報欠損22を除いた条件付き母集団であり、返還/中止の実運用会計は未検証。
- 本番app/、versionCode/versionName、Release、PROJECT_STATUS.md、本番モデルは未変更。本番自動反映なし。

### r4後の次の具体的1手

1. report/result/auditを読み、r1〜r4のminEVや展示z等を微調整して救済しない。
2. 次仮説は「選手履歴の増分を使う、時系列out-of-fold予測に基づく市場差の校正/選別」。**最初に新protocolで2025 Jan-Jun内のforward-only分割manifestを登録し、選別器学習に使うModel A予測が必ずその対象レース以前の学習だけで作られたことを検証する。** これは未実装であり今回成功扱いしない。
3. 既存r4 train cacheを再利用してOOF予測をActions matrixで作る。Jul-Augを追加学習に混ぜず、市場情報は最終選別器でのみ使用。結果を見て閾値を合わせる探索はしない。
4. 新候補も完全固定前にSep/Q4を開かない。Q4は今回のコードに許可経路なし。COREが基準を満たすまでLONGSHOTを進めない。

通常チャットへ戻ってBOAT AIの続きを依頼してください。

## v016 OOF研究・進行中チェックポイント（2026-09-24）

- 現在位置: protocol事前登録 commit `5a9b333eeae78e2d100f0ca69251bec98e223c6a`、forward-only manifest commit `1c9998b6664d0d93158f4fcb65f2e9fbe5c22dec`、実装workflow commit `a06d8e91af7ecdbb10dee6b51465fb508bd12fd3`。
- Actions Run `35982657474`: 実行中。guard SUCCESS、2025-03 fold と7〜8月固定Model A予測 SUCCESS、残り3fold実行中（この記録時点）。
- 次の1手: Runのfold→logistic→3候補matrix→publishを追跡し、失敗時はv016_oof_*専用ファイルで修正。成功時は data/v016_oof_result.json、feature_audit、report、frozen_candidateを検証する。
- r1〜r4閾値救済なし。2025年9月/Q4未取得。Android/app/Release/本番ロジック未変更。

## v016 OOF市場差研究 — 結果確定（2026-09-24）

- protocol commit `5a9b333eeae78e2d100f0ca69251bec98e223c6a`、forward manifest commit `1c9998b6664d0d93158f4fcb65f2e9fbe5c22dec`、実装commit `a06d8e91af7ecdbb10dee6b51465fb508bd12fd3`。
- Run `35982657474`: guard、4 OOF fold、固定Model A予測、logistic、3 selector matrix、成果物生成はSUCCESS。final Artifact `v016-oof-final` ID `10800503335`。publish jobのみ当handoffとのrebase競合でFAIL。Artifact内容をGitHub連携で直接保存し、報告commit `3b502c674fd1a2781555b53b637d87d8ec9e40a6`。実測数値は `data/v016_oof_report.md` と `data/v016_oof_result.json`。
- 7〜8月固定評価: raw_ratio ROI81.12%（7,265購入、581的中）、log_residual_half ROI85.91%（2,262購入、112的中）、logistic_residual購入0件。どれもROI105%/最大1的中除外ROI100%等のgateに届かず、candidate=null。不採用。
- 日付監査: fold全件forward、履歴同日混入0、重複キー0。2025年9月・Q4未開封。r1〜r4閾値救済なし。Android/app/Release/本番ロジック未変更。LONGSHOT未着手。
- 次の1手: 別の新仮説なら新protocolを事前登録。歴史オッズの締切時刻と未決済/返還の母集団差を監査し、年間/複数年の独立評価が可能になるまでは本番採用不可。同じ3候補の閾値再調整をしない。

## v016 integrity監査・実行中（2026-09-24）

- protocol事前登録commit `44c617f78f25baeb19aff9d5fdd466c51cfd6c95`。実装commit `3ab3d64abd44ddce040f8684d0984091d316541e`、guard修正 `128cd99fcf390eb36c659dfe2a2dd1ff58e9ac82`。
- Run `35986088143`: guardのworkflow自己検査に誤記がありFAIL（データ処理未開始）。修正Run `35986196670`: 実行中。7月/8月のオッズ・除外母集団はmatrix、source provenanceとforecastは別job。publish成果物待ち。
- 途中証拠: pinned `lamrongol/BoatraceOdds` commit `ddd2f0c1011889779d04dfb802bee4e152b35b30` の `scraper.php` は前日データ取得、日次cronは00:00 UTC、過去日backfillあり、`OddsSaver`は日別JSONを上書き。判定はActionsのハッシュ・払戻照合後に確定する。
- 次の1手: Run `35986196670` のguard→month2並列/provenance/forecast→publishを追跡。失敗ならv016_integrity_*専用ファイルのみ修正。9月/Q4未開封。Android/app/Release未変更。

## v0.16 INTEGRITY監査・forecast-only候補確定（2026-09-24）

- **現在位置**: 事前登録→歴史オッズの取得経路・7〜8月払戻/除外母集団監査→市場入力なしModel A候補固定→Android搭載可能性監査を完了。本番採用・購入条件探索は行っていない。結果ファイル保存時のmain commit `9760abc9c685e8f9d6b8ef7bd65f404e6ddda1c5`、集約コード修正commit `ba96a5eab4669584d39c14da5bfd2dfc3cac073d`、事前登録commit `44c617f78f25baeb19aff9d5fdd466c51cfd6c95`。
- Actions Run [`35986304640`](https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/35986304640): guard、7月/8月matrix、provenance、forecastの計算はSUCCESS。publishジョブのみforecast候補の `integrityProtocolCommitSha` を `protocolCommitSha` と誤参照してFAILED。生成済みArtifactを使い、修正済み同一集約コードでローカルの軽量集計・境界テストを成功させて4成果物をGitHubへ保存。重い監査計算の再実行なし。初回guard失敗Run `35986088143`、再修正Run `35986196670` も記録。
- 計算Artifact ID: 7月 `10802451970`、8月 `10801559042`、ソース経路 `10801583919`、forecast監査 `10802680652`、研究用モデル/履歴bundle `10802362375`。出典r4 Run `35940833546` のモデル `10784912368`（ZIP digest `sha256:58b845fa8d07efe258b08a23ac6caafab2e4854ce4b84618fb4af6ae3f3687fe`）、特徴量 `10784104679`、raw2025 `10785505050`。
- **Track A: `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`**。固定ソース `lamrongol/BoatraceOdds@ddd2f0c1011889779d04dfb802bee4e152b35b30` は前日分の日次取得・過去日backfill・日別上書き保存。レース別snapshot時刻/T−5分の証拠なし。最終払戻との高度な一致は事後値に近い可能性を示すが、購入可能時点の引用値を証明しない。このアーカイブでのROIに基づく購入モデル昇格を停止。
- 払戻照合（既開封2025年7〜8月のみ）: 元出走表 `10,284`レース、対象の6艇完走・単一3連単払戻 `9,588`、対象外 `696`、事前特徴量と120通りオッズの同時使用可能 `9,583`（うち事前特徴量不足5）。保存数値と払戻/100の一致 `9,546/9,588`、差≤0.1 `9,549`、≤0.5 `9,563`、相対差≤1%/3%/5%はいずれも `9,588`。符号付き平均差 `−0.002534`、最大絶対差 `0.9`オッズ点、24場の詳細は結果JSON。複数3連単払戻0件、返還明示フィールドは検出されず、返還0件とは断定しない。対象外696件の中止・欠場・不成立などの内訳とROIへの偏りの方向は特定不可。
- **Track B: `FORECAST_READY_FOR_INTEGRATION_DESIGN_PENDING_HOLDOUT`**。市場入力なしModel Aを `FORECAST_ONLY`、`PENDING_INDEPENDENT_HOLDOUT`、`productionPromotion=false` で固定。7〜8月開発9,583レースでlogloss `3.796223`、Brier `0.960191`、1着Top1/Top2 `56.09%/75.81%`、3連単Top1/Top4/Top8 `9.72%/29.34%/45.42%`。同期間Android純AIの1着Top1/Top2 `45.33%/66.94%`、3連単Top1/Top4/Top8 `5.61%/19.20%/32.95%`。独立holdoutは未実施で優越の最終確認ではない。
- Android設計監査: 3段LightGBMで1レース156行評価、モデル3ファイル合計約2.59MB、研究用履歴state約46.89MB（1,670選手・87,491レース、2025-08-31まで）。事前入力の完全性、日単位の同日結果混入防止、履歴更新、互換推論・端末性能・モデル/schema/stateハッシュ検証が必要。現行Androidに互換エンジンや現在時点の履歴は未導入。
- 保存先: `data/v016_integrity_protocol.json`、`data/v016_integrity_result.json`、`data/v016_integrity_report.md`、`data/v016_forecast_candidate.json`、`data/v016_forecast_deployability.md`。境界テスト成功。2025年9月と10〜12月Q4は未取得・未開封。r1〜r4/OOFの閾値救済なし。Android `app/**`、versionCode/versionName、Release、PROJECT_STATUS.md、本番ロジック未変更。
- **次の具体的1手**: 締切前のレース別取得時刻を監査可能なオッズソースを確保するまでROIによる購入候補昇格を止める。forecast候補は独立holdoutの対象期間・開封権限と評価規約を別途決め、2025年9月/Q4はこの引き継ぎから自動開封しない。並行して通常チャットでAndroid向けLightGBM互換推論と日次履歴更新の設計を検討できるが、搭載・Releaseは別判断。

## 2025年9月 forecast-only holdout 実行中（2026-09-24）

- 事前登録commit `2fbf3239f8ac68e4d45775b353aa03217d9a517f` を9月への初回アクセス前に単独作成。固定対象は市場非入力Model A、baselineはAndroid v0.15.16純AI。Q4は取得/閲覧禁止。
- 実装commit `5b8bbd11b49ba5a3a1b8b929379e3d0aa55d03dd`、境界テスト `18b2f78c2611f2cb8b1adb596e6cab376c173b8d`、Actions workflow `4a6e18cd811a06846b0690f7d8f2caa2b34b3cae`。
- Run [`35993900879`](https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/35993900879): guard SUCCESS、9月fetchと7〜8月baseline parityを並行実行中。この時点で9月のpopulation/精度は未確定。オッズ・払戻・購入指標は取得/評価しない。
- 次の1手: 同Runのfetch/parity→固定Model Aとbaseline並列推論→日単位ペアbootstrap/evaluateまで確認。失敗ならコード/データ整合性問題のみ修正し、9月の成績に応じてモデルや係数を変更しない。final Artifact IDと判定/指標を本ファイルに追記。Q4を開かず、app/とReleaseも変更しない。
