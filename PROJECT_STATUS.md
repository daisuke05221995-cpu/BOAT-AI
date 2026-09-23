# BOAT AI 引継ぎメモ

更新日: 2026-09-23

## 現在の状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.0`
- Android package: `jp.boatai.app`
- versionCode: `18`
- versionName: `0.15.0`
- Release target commit: `c17a63ba6f6ec620ffd44fdec82d8559ee50a611`
- Release workflow Run: `35840056796`
- GitHub Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.0`
- APK: `BOAT-AI-v0.15.0.apk`
- APK SHA-256: `34540587dcb9913369d006a50cea5f89070f67baec1faaad869b36a91d34d7e4`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.0/BOAT-AI-v0.15.0.apk`

## v0.15.0 完成内容

- 予想 / 結果 / 損益の3タブ構成
- 当日の予想一覧
- 購入推奨 / 見送りの2択表示
- 全国一括 / 場別一括 / 個別購入記録
- 一括選択は「購入推奨のみ」「見送りも含む」に対応
- 結果・着順・払戻・予想の照合
- 実購入損益とAI仮想損益を分離集計
- 今日 / 直近7日 / 今月 / 全期間の成績表示
- 2026年の月別・年合計バックテスト表示
- 公式オッズ取得・60秒更新・取得診断
- JSONバックアップ / 復元、CSV出力
- GitHub Releasesからのアプリ内更新
- 通常アップデート時に予想履歴・購入履歴を保持

## v0.15.0 月別バックテスト

損益タブの月別カードは、研究用v12ではなく**実際に本番へ採用している現行予想ロジック**の `data/historical_backtest_2026.json` を表示する。

- 2026年1月〜9月を月選択可能
- 年合計表示あり
- 購入推奨数 / 見送り数 / 的中率 / 投資 / 払戻 / 損益 / 回収率を表示
- 同日結果は同日の予想に使わず翌日以降へだけ反映するwalk-forward
- 過去の締切時3連単オッズは取得できないため、実機のオッズ最終判定はバックテストへ含まない
- そのため画面上でも「参考値」と明示

2026年1〜9月参考合計:
- evaluatedRaces: 40,967
- purchaseRaces: 13,755
- purchaseHits: 4,504
- stake: 16,506,000円
- payout: 12,994,120円
- profit: -3,511,880円
- ROI: 78.7%
- hitRate: 32.7%

## 予想ロジックの扱い

v0.15.0では、複数年で再現性を確認できなかった研究モデルを本番へ入れていない。
`app/src/main/assets` に `value_strategy_model.json` は存在せず、研究用Value Strategyは無効。

現行の安定ロジックを継続使用する。

### 不採用研究結果

2026開発用v12:
- 2026年5〜9月 ROI 117.3%
- ただし独立旧年検証で失敗
  - 2023 ROI 72.0%
  - 2024 ROI 45.5%
  - 2025 ROI 56.3%

rich-feature race-softmax:
- Run `35839229134` SUCCESS
- 2024設計 ROI 90.1%
- 2025固定評価 ROI 59.2%
- `readyForFinalHoldout=false`
- よって不採用

**2025-10-01〜2025-12-31のQ4最終holdoutは未開封のまま。**
今後v0.16以降で新モデル候補を完全固定できた場合だけ一度だけ使用する。

## Release検証

v0.15.0 Release Workflowで以下を実施:
- Release version解決成功
- Signing secrets確認成功
- Release signing key復元成功
- Unit test成功
- Android lint成功
- signed Release APK build成功
- APK署名検証成功
- GitHub Release公開成功
- APK / SHA256資産アップロード成功

## 既存の信頼性仕様

- 結果確定後や締切後に生成された後付け予想は成績へ含めない
- `settled && evaluationEligible` の事前予想だけを損益集計
- 展示・進入など購入判断に必要な情報が揃う前は成績固定しない
- 判定と判定理由は予想時点で固定
- 過去の判定を結果後に書き換えない
- 見送りレースも追跡可能
- 実購入は結果確定分だけ確定損益へ計上

## 完全自動投票

完全自動投票は対象外。
公式購入ページへの導線＋購入記録方式を維持する。

## 次の作業

優先順位:
1. ユーザー実機でv0.15.0を更新/インストールして基本動作確認
2. 予想・結果・損益・月別バックテスト・自動更新を実機確認
3. 問題がなければv0.15.0を安定版として維持
4. 予想モデル改善はv0.16以降の別フェーズとして再開
5. Q4 holdoutは新候補固定まで開かない

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
