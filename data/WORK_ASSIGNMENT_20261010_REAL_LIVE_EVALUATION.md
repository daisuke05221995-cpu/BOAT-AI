# BOAT AI 実ライブ評価 再開指示 — 2026-10-10

## 目的

端末に蓄積された実データを使い、BOAT AI v0.16.9 のライブ運用成績を初めて正式評価する。

最優先で答える質問:

1. AIのBUYだけを実際に買ったと仮定した場合、累計でプラスかマイナスか。
2. ユーザーが実際に購入した金額・払戻・損益・ROIはどうか。
3. AIライブ仮想成績と実購入成績の差はどこから生じているか。
4. どの条件で利益/損失が集中しているか。
5. 次に購入ロジックを直す価値がある箇所はどこか。

## 入力

端末の Settings > Data management から直接保存した `BOAT-AI-backup.json`。

- 公開GitHubへcommitしない。
- 実購入履歴・学習状態を含むためprivate inputとして扱う。
- schemaVersion=1 を現行契約とする。
- v0.16.9以降の直接保存バックアップを優先する。

## 固定評価器

- `scripts/v016_live_money_eval.py`
- `data/v016_live_money_protocol.json`
- Android serializer parity済み。
- golden backup + 18 contract tests済み。
- この実データを見てから評価ロジックや閾値を変更しない。

## 最初に出す集計

AI live audited:
- BUY races
- audited BUY count / completeness
- stake
- payout
- profit
- ROI
- hit count / hit rate
- average stake
- max drawdown
- Today / 7d / 30d / Month / Year / All

Actual purchases:
- settled purchase races
- settled stake
- payout
- profit
- ROI
- hit count / hit rate
- pending stake
- same period breakdown

## 診断

十分な件数がある場合のみ、以下で分解する。

- venue
- selected odds band
- selected point count
- total stake band
- confidence/model probability band
- first-lane structure
- weekday
- hour JST

追加で、実ライブデータから安全に算出できる場合:
- 点数別 4/5/6/7/8
- BUY confidence帯
- 会場別
- 1号艇中心/非1号艇
- 低オッズ集中/中穴/高配当
- 連敗長
- 最大1日損失
- 利益への上位的中レース依存度

## 判定ルール

- 回顧 `model-a-retro-flex-v2` を実ライブ実績に混ぜない。
- 最終オッズ/回顧オッズを実現可能ROIとして扱わない。
- 監査不足レコードは母数に残し、金額集計から除外し、原因を表示する。
- 1〜数本の高配当で黒字になっている場合は「安定して勝てる」と判定しない。
- 実ライブ成績が不十分な場合は、モデル変更ではなく蓄積継続を優先する。
- 十分な根拠なしにModel B/C/LONGSHOTをproductionへ昇格しない。

## 現時点の参考値（実ライブとは別）

2026-10-09更新の30日回顧 `model-a-retro-flex-v2`:
- 2,060 races
- stake 3,018,400円
- payout 2,452,600円
- ROI 81.25%
- 5点: ROI 100.04%
- 6点: ROI 89.97%
- 4点: ROI 76.83%
- 7点: ROI 53.96%
- 8点: ROI 68.23%

これは post-race odds allocation を含む回顧診断であり、ライブ実績ではない。

2026年walk-forward参考:
- through 2026-10-09
- 43,546 evaluated races
- 14,663 purchase races
- stake 17,595,600円
- payout 13,874,130円
- ROI 78.8%

この値も live odds final gate を含まないため、本番ライブROIではない。

## 次の作業

1. ユーザーから `BOAT-AI-backup.json` を受け取る。
2. frozen evaluatorへ投入。
3. schema/auditエラーがあれば原因を先に特定し、データを書き換えて数字を作らない。
4. AI-live と actual purchase を完全分離して集計。
5. 累計曲線・drawdown・利益集中を確認。
6. その結果を見て、次の修正を「購入条件」「点数」「資金配分」「モデル」のどこに入れるか決める。
7. 実装する場合は Android本番変更前に評価仮説・成功条件を固定する。
