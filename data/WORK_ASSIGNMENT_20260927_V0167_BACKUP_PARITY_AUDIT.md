# BOAT AI Work Assignment — v0.16.7 Backup / Evaluator Parity Audit

Date: 2026-09-27
Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`

## 目的

既存Androidアプリが実際に出力する `BOAT-AI-backup.json` と、Workが実装した `scripts/v016_live_money_eval.py` の入力契約を完全一致させる。

すでに1件、Androidが `1-2-3` 形式で保存するのに評価器の初版が `123` を期待していた不一致が見つかり、mainの `f2b8332479ada5af4313285e1e305b6c9b36b7ca` で修正済み。
同種の不一致を実機データ投入前に全て潰す。

## 最初に読むもの

1. `data/V0167_ACCOUNTING_RELIABILITY_HANDOFF_20260927.md`
2. `data/WORK_ASSIGNMENT_20260927_V0166_LIVE_MONEY_RESEARCH.md`
3. `data/v016_live_money_protocol.json`
4. `scripts/v016_live_money_eval.py`
5. `scripts/v016_live_money_eval_test.py`
6. Android側の以下の実装
   - `app/src/main/java/jp/boatai/app/DataBackupManager.kt`
   - `app/src/main/java/jp/boatai/app/PredictionHistoryStore.kt`
   - `app/src/main/java/jp/boatai/app/BetStore.kt`
   - `app/src/main/java/jp/boatai/app/LiveAuditedPerformance.kt`
   - `PredictionRecord` / `BetRecord` の `toJson` / `fromJson` 定義

## Workの編集範囲

研究・監査専用。

変更可:
- `scripts/v016_*`
- `data/v016_*`
- `data/WORK_*`
- 必要なら `.github/workflows/v016-*`

変更禁止:
- `app/`
- `app/build.gradle.kts`
- versionCode / versionName
- Release workflow
- 本番Model A asset
- BUY/SKIP本番ロジック

## 監査内容

Android serializer / deserializer とPython evaluatorをフィールド単位で照合する。
最低限、以下を確認すること。

### predictions
- id
- date
- stadiumNumber / venueNumber aliasの扱い
- raceNumber / race aliasの扱い
- combinations (`N-N-N` exact format)
- stakePerPick
- stakes
- resultCombination
- trifectaPayout
- settled
- createdAt
- confidence
- rank
- firstLane
- evaluationEligible
- autoSkipped
- recommended
- strategyId
- liveOddsFetchedAt
- liveOddsSource
- liveOddsCount
- livePickOdds
- missing/null時のAndroid `fromJson` デフォルトとの一致

### bets
- id
- date
- stadiumNumber / venueNumber
- raceNumber / race
- combination (`N-N-N` exact format)
- stake
- payout / actualPayout の実際のexport field
- settled
- createdAt
- 同一レース複数点のgrouping
- duplicate判定

### backup envelope
- schemaVersion
- appVersion
- exportedAt
- bets
- predictions
- learning
- historicalBaselineMigratedThrough

## 必須成果物

1. Android実装から手作業で推測せず、実serializer定義に基づく **golden backup fixture** を `data/` または `scripts/fixtures/` に追加する。
2. `scripts/v016_live_money_eval_test.py` に、そのgolden fixtureを評価器へ通すcontract testを追加する。
3. Androidの`fromJson`が許容するlegacy/missing/nullと、Python側fail-closed境界が意図的に違う場合は、理由をprotocol/reportへ明記する。
4. Android `LiveAuditedPerformance` とPythonの監査済みBUY母集団・stake・payout・profit・ROIが同一になることをsynthetic/golden testで確認する。
5. 実機バックアップが無い限り、実ROI・利益・的中率を作らない。

## 完了条件

- Androidの実バックアップJSONをそのまま渡して、形式違いで正常レコードを誤Rejectしない。
- 不完全監査レコードはAndroid側と同じ理由で監査母集団から除外される。
- 実購入とAIライブ成績を混ぜない。
- contract / unit testsが全成功。
- `data/v016_live_money_research_report.md` に監査結果、修正点、Run ID、残る差異、次の1手を追記する。

## 次工程

Parity audit完了後は、実機から出した `BOAT-AI-backup.json` が渡された時点で初めて実ライブ累計評価へ進む。
実データが無い間は閾値最適化や利益改善を装って進めず、評価器の正しさ・監査可能性を固めること。
