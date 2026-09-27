# v0.16 ライブ累計損益 研究基盤

更新: 2026-09-27。対象は研究用の評価基盤であり、Android本番コードや公開APKは変更しない。

## 現在位置

- `data/v016_live_money_protocol.json`: 入力形式、監査・会計・期間・診断の規則と将来候補の昇格前提を事前固定。
- `scripts/v016_live_money_eval.py`: 既存Androidの「バックアップ」で共有する `BOAT-AI-backup.json`（schemaVersion 1）を直接読む。`predictions` の `value-v1` settled / evaluationEligible / BUYだけをAIライブ用に抽出する。重複レースは拒否し、監査不足は件数・理由として数え、損益から除く。
- 同じバックアップの `bets` は実購入の別系列として集計する。同一レースの複数買い目は1購入レース・1的中レースとして数え、未settledの購入額は保留金額として分離する。同一買い目の二重購入記録は拒否する。
- 出力: 今日、7日、30日、月、年、全期間のBUY数・的中数・購入額・払戻・損益・ROI・平均購入額・累計曲線・最大ドローダウン・監査完備率。
- 会場、選択オッズ帯、点数、総購入額帯、Model A確率またはconfidence帯、1号艇の予想構造、曜日、時間帯の診断は、全体360BUY以上、各slice100BUY・20日・10的中以上で初めて記述値を出す。曜日と時間帯は補助のみ。sliceの黒字をモデル改善の証拠と呼ばない。
- `scripts/v016_live_money_eval_test.py`: 合成データで期間境界、会計、最大ドローダウン、欠損監査、旧ロジック除外、重複拒否、診断の少数標本ガードを確認。
- `.github/workflows/v016-live-money-research.yml`: 上記のprotocol JSONとテストをCIで検証する研究専用workflow。

## 入力と実行

入力は既存 `DataBackupManager.backupJson()` の `schemaVersion:1`、`appVersion`、`exportedAt`、`bets`、`predictions`、`learning` を含むバックアップ。テスト用には `PredictionRecord.toJson()` のオブジェクト配列も使える。各予想レースに `date`、`stadiumNumber`、`raceNumber`、`combinations`、`stakes`、`liveOddsFetchedAt`、`liveOddsSource`、`liveOddsCount`、`livePickOdds`、`resultCombination`、`trifectaPayout` 等を含む。モデル確率は本番記録にないため、任意の `modelProbability` が無い場合は保存済みの `confidence` を別名で表示する。両者を同じ確率と見なさない。

```bash
python scripts/v016_live_money_eval.py BOAT-AI-backup.json --output live_money_result.json
python scripts/v016_live_money_eval_test.py -v
```

`--as-of` は省略すると日本時間の今日になる。固定再現時は `--as-of 2026-09-27` のように指定する。AI仮想払い戻しは100円あたりの3連単払戻と的中買い目の配分から再計算し、実購入は `bets` の払戻フィールドをそのまま集計する。期間内の最大ドローダウンはその期間の初期損益0を基点とする。各期間に入るBUY候補の監査完備率も独立に計算する。

## 結果・限界・採否

- GitHubにはユーザー端末の実ライブ履歴エクスポートがない。**実ライブBUY件数、実利益、実ROIは未測定**。合成テストの数値を実績として扱わない。
- 監査の取得時刻・取得元・120通り件数はAndroid保存フィールドに依存する。研究スクリプト単体ではオッズ原本の120個の値、取得元の真正性、締切前に実際に購入できたかを独立証明できない。
- `dataStatus=NO_LIVE_EXPORT` で空入力はROIをnullとする。金額ゼロを利益なしの実測結果と誤認させない。
- Model B/C/LONGSHOTの採用判断: **保留**。予想品質、監査可能なライブ判断、十分な購入件数、独立期間の再現性、累計ROI、ドローダウン、高配当集中依存を事前固定して評価する。最終オッズをライブで実現可能なROIとして採用しない。本スクリプトは本番昇格しない。
- Android本体、versionCode、Release、`PROJECT_STATUS.md`、`CURRENT_STATUS.md`、本番Model A / value-v1には変更を加えていない。

## 検証・次の1手

- ローカル: 合成fixture 12テスト全件成功、protocol JSON構文検証成功。CI Run IDは実行後に追記する。
- 次は端末の既存「バックアップ」からユーザー自身が `BOAT-AI-backup.json` を保存し、実ライブ記録が貯まった時点で本スクリプトへ渡して計算する。バックアップには実購入や学習情報も含まれるため、リポジトリへ公開commitしない。原因別の監査欠落や端末と集計器の照合を優先する。
