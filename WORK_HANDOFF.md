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
