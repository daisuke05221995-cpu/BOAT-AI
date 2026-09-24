# BOAT AI Work Assignment — v0.16 OOF市場差校正

更新日: 2026-09-24

## 目的

Workはv0.16予想モデル研究専用として、r4後の新仮説を検証する。

新仮説:
**選手履歴の増分を使った時系列out-of-fold (OOF) 予測を作り、その予測と市場確率の差を、リークなしで校正・選別する。**

r1〜r4の閾値微調整・救済は行わない。

## 最初に必ず確認

- `WORK_HANDOFF.md`
- `PROJECT_STATUS.md`
- `NEXT_WEEK_HANDOFF.md`
- `data/v016_r4_report.md`
- `data/v016_r4_protocol.json`
- 最新main commit
- 最新/進行中のv016 GitHub Actions

現時点の通常チャット側最新mainは、確認時点で `11338ffc426662f60e02803bf5ceb333bb048f61`（Android v0.15.16 Release trigger）。作業開始時に必ず再確認すること。

## 役割分担・競合禁止

### Workが触ってよいもの

原則、新規の研究専用ファイルのみ:

- `scripts/v016_oof_*`
- `.github/workflows/v016-oof-*`
- `data/v016_oof_*`
- 必要ならこのAssignmentや`WORK_HANDOFF.md`の研究チェックポイント追記

### Workが触ってはいけないもの

- `app/**`
- `app/build.gradle.kts`
- versionCode / versionName
- Release workflow
- Android UI / 通知 / 履歴 / 損益
- `app/src/main/assets/value_strategy_model.json`
- v0.15.16純AI監査用 `v01516_*` ファイル
- 本番ロジックへの自動統合

通常チャット側がAndroid・v0.15.16純AI監査・本番統合・Releaseを担当する。

## 厳守するデータ境界

- **2025-10-01〜2025-12-31 final holdoutは絶対に取得・読込・評価しない。**
- **2025年9月も候補完全固定前は開かない。**
- 2025年7〜8月は最終学習へ混ぜない。開発評価としてのみ使用する。
- r4の結果を見た後にminEV、展示z、market edgeなどを再探索して救済しない。
- LONGSHOTはCORE候補が基準を満たすまで開始しない。

## 研究プロトコル

### Phase 0 — 事前登録

分析結果を見る前に `data/v016_oof_protocol.json` を作成しcommitする。

最低限固定するもの:

- 学習/OOF/開発評価期間
- forward-only split manifest
- 使用特徴量群
- Model Aの学習方法
- OOF予測生成ルール
- 市場確率の作り方
- 校正/selectorのモデル候補
- selectorへ渡す特徴
- 候補数を増やす場合の上限
- 採否gate
- ROI会計ルール
- bootstrap単位
- data leakage guard
- 2025年9月/Q4禁止条件

プロトコルcommit SHAを以後の全成果物manifestへ記録する。

### Phase 1 — forward-only OOF manifest

2025年1〜6月内で、各対象レースのModel A予測が必ず過去データのみから作られる時系列分割を定義する。

例の考え方:

- 初期training windowを確保
- その後を週単位または月内ブロックでforward prediction
- 各foldで `max(train_date) < min(predict_date)` を機械検証
- 同日結果の混入禁止

fold数や粒度は事前登録時に固定する。

### Phase 2 — r4 feature cache再利用

可能な限りRun `35940833546` のArtifactを再利用する。

主な再利用候補:

- `v016-r4-features` Artifact ID `10784104679`
- `v016-r4-raw-2025` Artifact ID `10785505050`
- `v016-r4-raw-2024` Artifact ID `10785285539`

2025年1〜6月のModel A OOF予測生成に必要なcacheを再計算しないで済むなら再利用する。

### Phase 3 — Model A OOF予測

r4で増分価値が確認された「個人・コース履歴」を含むモデルをベースにする。

重要:

- Model Aは市場オッズを入力にしない。
- 各OOF予測は対象レースより過去だけで学習。
- 3連単120通りの確率を保存。
- 1着6艇の周辺確率も保存。
- probability sum / NaN / duplicate race key / timestamp leakageを監査。

### Phase 4 — 市場差の校正/selector

市場情報を使ってよいのはこの最終層だけ。

最低限比較する候補:

1. raw ratio: `model_prob / market_prob`
2. log residual: `log(model_prob) - log(market_prob)`
3. 小容量の校正/selector（ロジスティック回帰等、過学習しにくいもの）

ただし観測結果を見てモデル候補や閾値を無制限に追加しない。候補はprotocolで固定する。

市場確率は同一レース120通りで正規化し、欠損/異常オッズの扱いを事前登録する。

### Phase 5 — 評価

2025年1〜6月OOFでselectorを構築し、**2025年7〜8月は完全に追加学習なしで固定評価**する。

確率評価:

- LogLoss
- Brier score
- ECE
- 1着top1 accuracy
- 1着top2 coverage
- trifecta top1 / top2 / top4 / top8 hit rate

購入評価:

- BUY率
- 購入レース数
- 的中数
- 投資 / 払戻 / 損益 / ROI
- 月別ROI
- 最大1的中除外ROI
- 最大1的中依存率
- predicted EVとrealized ROIのcalibration gap
- 日単位bootstrap CI

## 採否の考え方

r4同様、見かけの高ROIだけで採用しない。

最低限:

- 開発評価ROI 105%以上
- 最大1的中除外ROI 100%以上
- 適切な購入件数と的中件数
- EV校正gapが事前登録上限以内
- 単発高配当依存が過大でない
- 確率品質を著しく悪化させない

具体的数値gateはprotocolで結果を見る前に固定すること。

## 成果物

最低限以下をmainへ保存する。

- `data/v016_oof_protocol.json`
- `data/v016_oof_split_manifest.json`
- `data/v016_oof_feature_audit.json`
- `data/v016_oof_result.json`
- `data/v016_oof_report.md`
- `data/v016_oof_frozen_candidate.json`

候補なしなら `candidate=null` を正直に保存し、無理に候補を作らない。

## GitHub Actions

重い処理はActionsへ寄せる。

- OOF foldは独立可能ならmatrix化
- feature/artifactを再利用
- selector比較も独立可能なら並列化
- 最終publish jobで全成果物を集約

Run ID、Artifact ID、commit SHAをreportとhandoffへ保存する。

## 終了条件

1. protocol事前登録済み
2. forward-only guardテスト成功
3. OOF予測作成完了
4. selector候補比較完了
5. 2025年7〜8月固定評価完了
6. 採否を決定
7. 2025年9月/Q4未開封を監査で確認
8. `WORK_HANDOFF.md`へ現在位置・Run ID・次の1手を追記

Workの上限・タイムアウト・コンテキスト不足が近い場合は、必ず有効な変更をcommit/pushし、Run IDと次作業をGitHubへ保存してから通常チャットへ戻るようユーザーへ案内する。

## Workへ渡す短い開始文

`BOAT AI v0.16研究の続き。GitHubの data/WORK_ASSIGNMENT_20260924_V016_OOF.md を最優先で読み、そこに書かれた役割分担とデータ境界を厳守して、protocol事前登録→forward-only OOF manifest→Model A OOF予測→市場差校正/selector→2025年7〜8月固定評価→採否まで進めてください。r1〜r4の閾値救済は禁止。2025年9月と10〜12月Q4は開かないでください。Android app/Releaseは触らないでください。`