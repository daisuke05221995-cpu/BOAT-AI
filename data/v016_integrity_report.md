# v0.16 オッズ整合性とforecast-only候補

- Run: 35986304640 / 事前登録commit `44c617f78f25baeb19aff9d5fdd466c51cfd6c95`
- オッズ判定: **ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST**。購入可能な締切前オッズとして扱えないため、このアーカイブによるROI基準の本番昇格を停止。
- [オッズソース固定commit](https://github.com/lamrongol/BoatraceOdds/tree/ddd2f0c1011889779d04dfb802bee4e152b35b30) の `scraper.php` は東京時間の前日を取得し、`cron.yml` は毎日00:00 UTC起動。`get_past.yml` は過去日を遡る。`OddsSaver.php` は日付ごとに1配列を上書き保存。7月1日のJSONは144レース、取得時刻フィールドなし。READMEの「約30分間隔」は、この保存経路の時刻証明にならない。
- 2025年7〜8月の既存cacheと、同一SHAのprogram/resultソースだけを照合。9月/Q4は未取得。

| 集計 | 7月 | 8月 | 合計 |
|---|---:|---:|---:|
| sourceRaces | 5,196 | 5,088 | 10,284 |
| eligibleSettled | 4,820 | 4,768 | 9,588 |
| preRaceFeatureUsable | 4,820 | 4,763 | 9,583 |
| all120OddsUsable | 4,820 | 4,768 | 9,588 |
| jointUsable | 4,820 | 4,763 | 9,583 |
| payout races | 4,820 | 4,768 | 9,588 |
| payout exactStoredValue | 4,798 | 4,748 | 9,546 |
| payout withinAbsolute0_1 | 4,799 | 4,750 | 9,549 |
| payout withinAbsolute0_5 | 4,805 | 4,758 | 9,563 |
| payout withinRelative1Pct | 4,820 | 4,768 | 9,588 |
| payout withinRelative3Pct | 4,820 | 4,768 | 9,588 |
| payout withinRelative5Pct | 4,820 | 4,768 | 9,588 |

差分(オッズ−払戻/100): 平均 -0.002534、絶対差平均 0.002536、絶対差中央値 0.00000038、最大 0.9 オッズ点。月別・場別の分位点と最大不一致20レースのキーは `data/v016_integrity_result.json`。
完全一致は保存数値の浮動小数点誤差を許容した判定（絶対差≤0.0001）。資料から高配当時の丸め・切捨て規則を確証できないため、別の換算規則による一致率は仮定しない。
対象外の分類: `{'nonSixBoatOrIncompleteFinish': 696}`。返還を示す明示フィールド: `{}`。項目がない場合、返還が0件と断定しない。中止・欠場・不成立の内訳も現行の除外理由だけでは確定しない。
払戻との一致は事後・最終に近い値を示し得るが、事前取得の証明にはならない。除外に伴うROIバイアスの方向は、この母集団だけから確定できない。

- forecast判定: **FORECAST_READY_FOR_INTEGRATION_DESIGN_PENDING_HOLDOUT**。候補は市場入力なし、`PENDING_INDEPENDENT_HOLDOUT`、本番昇格なし。
- Model A 9,583レース: 1着Top1 56.09%、Top2 75.81%、3連単Top1 9.72%、Top4 29.34%、Top8 45.42%。Logloss 3.796223、Brier 0.960191。
- 現行Android純AI監査の同9,583レース: 1着Top1 45.33%、Top2 66.94%、3連単Top1 5.61%、Top4 19.20%、Top8 32.95%。ただし開発期間の比較であり、独立holdoutは未実施。
- 推論/履歴stateの詳細は `data/v016_forecast_deployability.md`。Android実装、version、Releaseには未着手。
