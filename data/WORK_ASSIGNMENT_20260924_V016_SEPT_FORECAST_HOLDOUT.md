# BOAT AI v0.16 Work assignment — 2025年9月 forecast-only 独立holdout

作成日: 2026-09-24 JST

## 目的

固定済みの市場非入力 Model A が、2025年7〜8月の開発期間だけでなく、これまで未開封だった **2025年9月** でも現行Android v0.15.16純AI forecastを上回るかを、事前登録した **forecast-only独立holdout** として確認する。

今回の評価は予想品質だけを対象とする。購入ROI・期待値・オッズ選別・BUY/SKIP閾値は一切評価・探索しない。

2025年10〜12月Q4は最終holdoutとして引き続き完全未開封にする。

## 最優先で読むもの

1. `data/WORK_ASSIGNMENT_20260924_V016_INTEGRITY.md`
2. `data/v016_integrity_report.md`
3. `data/v016_forecast_candidate.json`
4. `data/v016_forecast_deployability.md`
5. `data/v01516_forecast_audit_protocol.json`
6. `data/v01516_forecast_audit_report.md`
7. `data/v016_r4_protocol.json`
8. `data/v016_r4_report.md`
9. `WORK_HANDOFF.md`
10. 最新main / 最新v016 Actions

## 絶対条件

- **最初に protocol をGitHubへcommitするまで2025年9月データを取得・閲覧・集計しない。**
- Q4 `2025-10-01..2025-12-31` は取得・閲覧・集計禁止。
- 固定候補は `data/v016_forecast_candidate.json` の Model A のみ。モデル再学習、特徴量追加、温度再選択、ハイパーパラメータ探索は禁止。
- Model Aのモデル3ファイル、temperature=1.0、feature schema、履歴ロジック、2025-08-31時点stateの扱いを固定する。
- 市場オッズ、人気、払戻、購入判定はforecast入力・選択・評価に使わない。
- 9月を見てから係数/feature/fallback/欠損処理を変えない。
- r1〜r4、OOF候補の閾値救済をしない。
- `app/**`、versionCode/versionName、Release、本番ロジック、`PROJECT_STATUS.md` は触らない。
- Workが編集してよいのは新規 `scripts/v016_sept_forecast_*`、`.github/workflows/v016-sept-forecast-*`、`data/v016_sept_forecast_*`、必要な `WORK_HANDOFF.md` checkpointのみ。

## Phase 0 — 事前登録

まず `data/v016_sept_forecast_protocol.json` を作り、**単独commit**してSHAを固定する。このcommit完了前に9月を開かない。

protocolに最低限以下を固定する。

- holdout期間: `2025-09-01..2025-09-30`
- Q4 prohibited=true
- candidate: `data/v016_forecast_candidate.json` のmodel/artifact/hash一式
- baseline: 現行Android v0.15.16 `AverageRoiReferenceStrategy.forecast` の完全再現
- population rule: 6艇、必要な事前/直前入力が揃い、結果が一意に確定しているレース。Model Aとbaselineを**同一レース集合**で比較する。
- history rule: 2025-08-31までの結果でstateを作成し、9月中は各日について「当日全レースの予想snapshotを先に生成→その日の全確定結果をまとめて履歴更新」。同日レース結果混入禁止。
- market inputs=false / payout inputs=false / ROI metrics=false
- missing required Model A inputはModel A欠測として記録し、勝手なbaseline fallbackでModel A成績に混ぜない。coverageを別指標として出す。

## Phase 1 — 9月データ取得とリーク監査

protocol commit SHAをworkflow入力/成果物へ固定した上で、2025年9月だけ取得する。

監査:

- min/max race dateが9月内のみ
- Q4 row=0
- duplicate race key=0
- same-day result leakage=0
- history state start through=2025-08-31
- 予想snapshot生成時に当日結果未反映
- Model A入力にresult/payout/odds由来feature=0
- baseline/Model A比較集合のキー完全一致

## Phase 2 — 固定Model A推論

`data/v016_forecast_candidate.json` と研究Artifactのhashを照合し、固定Model Aで120通り3連単確率と6艇1着周辺確率を出す。

監査:

- 120 probabilities finite / nonnegative
- sum=1 within tolerance
- 1着marginal sum=1
- model/schema/state hash一致
- stage0/1/2のモデル変更なし
- temperature=1.0

## Phase 3 — 現行v0.15.16 baseline完全再現

Androidの `AverageRoiReferenceStrategy.forecast` をPython側で式・course prior・temperature=14.0・Plackett-Luce順序確率まで一致させる。

9月同一race populationで Model A と baseline をペア比較する。

## 評価指標

### Primary

- trifecta logloss
- trifecta Brier
- paired **calendar-day block bootstrap** 95% CI of `ModelA - baseline` for logloss and Brier

Primary pass:

- logloss point estimate: Model A < baseline
- logloss day-block bootstrap 95% CI upper bound < 0
- Brier point estimate: Model A < baseline

### Secondary

- first-place Top1
- first-place Top2
- trifecta Top1 / Top2 / Top4 / Top8
- top-choice ECE
- coverage / missing-input rate
- daily and venue breakdown（診断のみ、後付け閾値化禁止）

Secondary safety:

- first-place Top1 point estimateがbaseline以上
- trifecta Top4 point estimateがbaseline以上
- catastrophic regressionが特定の大量母集団で起きていないかを記述するが、venue別最適化は禁止

## 判定

### `PASS_FORECAST_HOLDOUT`

Primary passを満たし、secondary safetyも満たす。

この場合でも `productionPromotion=false` のまま。次は通常チャット側でAndroid互換推論/履歴更新prototypeを作り、Pythonとのparityと端末性能を検証する。Q4はまだ開けない。

### `FAIL_FORECAST_HOLDOUT`

Primaryまたはsecondary safety未達。

この場合Model AをAndroidへ本番統合しない。9月を見て救済調整しない。新仮説は別protocolから開始。Q4は開けない。

### `INCONCLUSIVE_FORECAST_HOLDOUT`

データcoverage・履歴再構成・parity監査に重大な不確実性があり、精度判定自体が信用できない場合。

## 成果物

最低限:

- `data/v016_sept_forecast_protocol.json`
- `data/v016_sept_forecast_data_audit.json`
- `data/v016_sept_forecast_result.json`
- `data/v016_sept_forecast_report.md`
- `data/v016_sept_forecast_decision.json`

`decision.json` には最低限:

- decision
- protocol commit SHA
- Model A artifact/hash
- baseline source hash
- population / coverage
- Model A metrics
- baseline metrics
- paired bootstrap intervals
- septemberOpened=true
- q4Opened=false
- productionPromotion=false

## Actions

重いデータ取得・履歴再生・推論・bootstrapはGitHub Actionsへ回す。

可能なら:

- guard
- fetch/build September cache
- Model A inference
- Android baseline replay
- paired evaluation/bootstrap
- publish

に分ける。

## 完了時

`WORK_HANDOFF.md` に次を追記する。

- protocol commit SHA
- Run ID / Artifact ID
- 9月population / coverage
- Model A vs baseline主要数値
- bootstrap CI
- 最終decision
- Q4未開封の明記
- Android/app/Release未変更の明記
- 次の具体的1手

## Work上限時

制限・タイムアウト・コンテキスト不足が近い場合、現在位置・commit SHA・Run ID・次の1手を `WORK_HANDOFF.md` に保存してから通常チャットへ戻るよう案内する。
