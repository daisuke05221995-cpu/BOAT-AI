# v0.16 OOF市場差校正 — 固定開発評価

- Run: 35982657474; protocol commit: `5a9b333eeae78e2d100f0ca69251bec98e223c6a`
- 最終成果物Artifact: `v016-oof-final` ID `10800503335`。全計算job成功。publish jobは引き継ぎ文書の同時追記によるrebase競合のみ失敗し、同一Artifactの4ファイルをGitHub連携から保存（最終commit `e641c719ea0d91c74bb4f9ce6e78046dc7d1d6f2`）。
- r4 Artifact再利用: features 10784104679、Model A 10784912368（Run 35940833546）
- 4 forward foldsは3〜6月、7〜8月は追加学習なし。9月とQ4は未取得・未評価。
- 4 foldの実日付検証は `max(fit)<max(validation)<min(prediction)`、履歴同日混入0、重複レースキー0。7〜8月の有効オッズ9,583レース。Model A logloss 3.796223、Brier 0.960191。

| 候補 | 購入 | 的中 | ROI | 最大1的中除外ROI | EV差 | 判定 |
|---|---:|---:|---:|---:|---:|---|
| raw_ratio | 7265 | 581 | 81.12% | 80.57% | 53.13pt | 不採用 |
| log_residual_half | 2262 | 112 | 85.91% | 84.14% | 32.57pt | 不採用 |
| logistic_residual | 0 | 0 | 0.00% | 0.00% | N/A | 不採用 |

採否: REJECT。候補: なし。確率品質gate: True。
raw_ratioの7月/8月ROIは84.64%/77.52%、log_residual_halfは100.05%/71.65%。日単位bootstrapの合算ROI 95%区間はそれぞれ73.60〜88.57%、69.60〜101.81%。logistic_residualは事前固定の購入条件を満たす買い目が0件。
年間105%と複数年再現性は未評価。本番統合は行わない。
