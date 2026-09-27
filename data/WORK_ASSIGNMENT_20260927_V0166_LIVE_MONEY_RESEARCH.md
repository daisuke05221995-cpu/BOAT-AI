# BOAT AI Work Assignment — v0.16.6 Live Money Research

Date: 2026-09-27
Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`

## 最優先で読むもの

1. `CURRENT_STATUS.md`
2. `data/V0166_MONEY_FIRST_PROFIT_HANDOFF_20260927.md`
3. `WORK_HANDOFF.md`
4. 最新main / 最新v016系Actions

古いv0.15.xメモや「Q4未開封」等は、現在のsource-of-truthを上書きしないこと。

## ユーザー目的

最優先は説明量ではなく、実運用で次の2点を改善すること。

1. AIの購入推奨に従ったとき、累計でお金が増えるか減るか。
2. その累計成績を、監査可能なライブ記録だけで正しく評価できるか。

## Workの担当範囲

Workは **研究・分析専用**。Android本番コードは通常チャット側が担当する。

変更してよい範囲:
- `scripts/v016_*` の新規/研究用ファイル
- `.github/workflows/v016-*` の研究用workflow
- `data/v016_*` / `data/WORK_*` の研究結果・プロトコル・handoff

変更禁止:
- `app/`
- versionCode / versionName
- Release workflow
- `PROJECT_STATUS.md` / `CURRENT_STATUS.md` の本番状態
- 本番Model A assetの差し替え
- 現行ライブBUYロジックの直接変更

## 今回の研究タスク

### A. ライブ累計評価プロトコルを作る

`value-v1` の監査済みライブBUYだけを対象に、将来端末からエクスポート可能な記録を評価するためのプロトコル/スクリプトを作る。

必須指標:
- BUY races
- stake
- payout
- profit
- ROI
- hit count / hit rate
- average stake
- cumulative profit curve
- max drawdown
- audit completeness
- 日/7日/30日/月/年/累計

実データがGitHubに無い場合は成績を捏造しない。入力schemaと集計器、synthetic fixtureによるテストまで作る。

### B. 損益悪化箇所の診断を作る

監査済みライブ記録が十分に貯まった後にだけ使える診断として、以下の切り口を準備する。

- venue
- odds band
- selected point count
- total stake band
- Model A probability/confidence band
- 1号艇関連の予想構造
- 曜日/時間帯は補助指標に留める

各sliceで最低サンプル数を要求し、少数的中・単発高配当で「改善した」と判定しない。

### C. 改善候補の昇格ルールを事前固定する

Model B/C/LONGSHOTなど将来候補は、後付け閾値調整をせず、以下を満たす場合だけ本番候補としてhandoffする。

- forecast品質を壊さない
- 監査可能な購入判定である
- 十分な購入件数がある
- out-of-sampleで再現する
- 累計ROIだけでなくdrawdown/集中依存も確認する
- 過去final-like oddsを実現可能ライブROIとして扱わない

現在のModel A/value-v1を勝手に置換しない。

## 成果物

最低限:
- `data/v016_live_money_protocol.json`
- `scripts/v016_live_money_eval.py`
- `scripts/v016_live_money_eval_test.py`
- `data/v016_live_money_research_report.md`
- 必要なら研究専用GitHub Actions workflow

テスト可能なところまで実装し、Run ID・結果・採否・次の具体的1手をレポートに残す。

## 停止/上限時

Work上限、タイムアウト、権限エラー等で止まりそうな場合は、黙って終了しない。
有効な変更をcommit/pushできるなら保存し、`data/v016_live_money_research_report.md` または新しいhandoffへ現在位置・Run ID・次作業を記録する。
書き込み不能なら、何がブロックされたかを明記する。

## 完了条件

今回のWork作業は「利益が出る」と結論を作ることではない。
**実ライブデータが貯まったとき、累計で増えた/減ったを改ざんなく評価し、どこで損益が生まれたかを安全に診断できる研究基盤を完成させること**が完了条件。
