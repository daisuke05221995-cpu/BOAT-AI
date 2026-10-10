# v0.16 版別ライブ証拠レポート — 2026-10-11 引き継ぎ

Assignment: [WORK_ASSIGNMENT_20261011_VERSIONED_EVIDENCE_REPORT.md](WORK_ASSIGNMENT_20261011_VERSIONED_EVIDENCE_REPORT.md)

## 完了したもの

- 新ヘルパー: [scripts/v016_versioned_evidence_report.py](../scripts/v016_versioned_evidence_report.py)
- 合成テスト: [scripts/v016_versioned_evidence_report_test.py](../scripts/v016_versioned_evidence_report_test.py)
- 既存の研究CIに新ヘルパーとテストのpath trigger、新テストstepを追加。
- 実装commit: `e5060216f6e3b15af7074b7aa0343c3b2722ba75`
- [PR #13](https://github.com/daisuke05221995-cpu/BOAT-AI/pull/13): mainへmerge済み。
- merge commit: `21b0fe25d347feffefbb42b8b9a4cb55dec16171`
- CI Run [38069413037](https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/38069413037): **SUCCESS**。synthetic-validationのJSON検証、既存テスト、新テストの全step成功を確認。

確認開始時mainは `9cee852e7b1afa99013462021d0e7feb96403cdd`。CURRENT_STATUS.md、DEVELOPMENT_ROUTING.md、OPERATION_REVIEW_20261011.md、v0.18.8 handoff、凍結評価器・protocolを確認して実装した。

## 集計の意味

| sourceAppVersionの値 | 集計先 |
|---|---|
| フィールドなし / null / 空文字 / 空白のみ | sourceAppVersion=null、bucketType=legacy_unversioned |
| 空白のみではない文字列 | その文字列をそのまま使う独立したversioned bucket |
| 数値・boolean・object・array | 型不正として中断。版への変換や推測はしない |

バックアップ全体のappVersionは出力のprovenanceに保存するだけで、行の帰属には使わない。`0.18.7`、`0.18.8`、`0.18.9`等はそれぞれ別のbucketにする。前後に空白のある非空文字列も勝手に正規化・統合しない。表示順は版不明が先、その後は文字列順であり、版の新旧を示す順序ではない。

新規作成・再評価時に保存された行のsourceAppVersionを読む。元のcreatedAt、エクスポート時刻、リリース日から初回作成版・実機導入日時を推測しない。版不明の旧行をv0.18.8へ補完しない。

### 出力

`allRecords`に全体、`versionBuckets`に各版と版不明の同じ指標を出す。

| フィールド | 内容 |
|---|---|
| predictionCount | asOfJst以前の予想行数。SKIP・未settled・旧strategyも含む |
| exportedPredictionCount / excludedFuturePredictionCount | 入力の総予想行数 / 基準日より未来の日付の予想行数 |
| firstRaceDateJst / lastRaceDateJst | 対象予想のdateの最小・最大。createdAt順やBUYだけの日付範囲ではない |
| audit.liveBuyCount | 凍結ルールのsettled・evaluationEligible・recommended・value-v1候補数 |
| audit.auditedBuyCount / incompleteCount | 監査合格BUY数 / 監査不足BUY数 |
| audit.completenessPercent / failureCounts | 監査済み数÷候補数×100 / 重複を許す理由別件数 |
| auditedMoney | 監査済みBUYのみの件数・的中数・投資・払戻・損益・ROI等 |

BUY候補0件の完備率はnull、投資0円のROIもnull。100%や黒字実績として扱わない。予想件数は行数で、監査候補のレース重複は凍結評価器の一意キーで拒否する。

dateはAndroidのJSTレース日として読む。全予想行のdateが正しいYYYY-MM-DDであることをレポート作成に必要とし、不正なら中断する。これは日付範囲を作るための入力検証であり、凍結監査条件の追加ではない。

### 凍結評価器との関係

先にバックアップ全体を既存の`evaluate()`へ渡し、版をまたぐ重複BUYやbetsの不正を検出する。その後、元の予想行を版別に分け、同じ評価器へ渡す。正規化、候補条件、監査条件、会計を複製・変更しない。

`reconciliation.status=PASS`は、版別の予想数・候補数・監査済み数・不足数・理由別件数・金額・的中数を合計した結果と全体が一致し、日付の最小・最大も一致したことを示す。率を足したり単純平均したりしない。運用継続や利益のPASSではない。

`formalEvaluation`の目標は既存protocolから読む**全体360監査済みBUY**のまま。残数=max(0,360−全体監査済みBUY)。各版で360件にリセットせず、360到達で本番採用を自動許可しない。既存のdiagnostics statusとproductionPromotion=falseを維持する。

実購入betsは全体入力の整合性検証だけに使い、予想の版へ帰属させない。実購入の会計は従来の凍結評価器の別系列を確認する。

## テスト結果

Python 3.12.14で次を実行:

```bash
python3 scripts/v016_versioned_evidence_report_test.py -v
python3 scripts/v016_live_money_eval_test.py -v
```

- 新規16テスト: **全件成功**。
- 既存18テスト: **全件成功**。
- CIはPython 3.12で同じ2系列とprotocol/golden JSONを検証しSUCCESS。
- 旧・null・空白の分離、版文字列の保持、入力非破壊、版別合計の照合、複数買い目の払戻、監査不足の除外、既存defaultsとの一致、跨版重複、未来日除外、実購入分離、359/360境界、CLI保存と原本上書き拒否を確認。
- 使用したのは合成fixtureと既存の公開synthetic golden fixtureのみ。**私有ユーザーバックアップは使用・commitしていない**。

次のGit blob SHAが元のままであることを検証した:

| ファイル | SHA |
|---|---|
| scripts/v016_live_money_eval.py | cc30da96ab6fb087a8dc280956d42b7b32d54382 |
| data/v016_live_money_protocol.json | ba140d90dd296299e84250053f315f7f2a8e6c2a |
| scripts/v016_live_money_eval_test.py | 159f6df8f7ca800648fff59490425d1a7772aa72 |
| data/v016_live_money_golden_backup.json | bb87022fa2f2dfdd48a16193481efc35ca10da76 |

## 次の私有バックアップでの使い方

mainを取得した研究環境で実行する。以下のパスとYYYY-MM-DDを実際の私有ファイルの場所・JST評価基準日に置き換える。

```bash
python3 scripts/v016_live_money_eval.py /private/BOAT-AI-backup.json \
  --as-of YYYY-MM-DD --output /private/frozen_live_money_result.json

python3 scripts/v016_versioned_evidence_report.py /private/BOAT-AI-backup.json \
  --as-of YYYY-MM-DD --output /private/versioned_evidence_report.json
```

`--as-of`省略時は既存評価器と同じJSTの今日。再現確認には同じ明示日付を両コマンドへ渡す。出力先は入力と別の場所にする。原本・出力とも自動で公開・commitする処理はない。

通常チャットで確認する順序:
1. 全体の監査済み件数・残数と、版別合計の照合結果を確認。
2. legacy_unversioned、0.18.7、0.18.8、以後の各版を分けて監査完備率・不足理由・金額・日付範囲を比較。
3. 「v0.18.8以降」をまとめる場合は版の大小を文字列比較せず、該当する正式版を確認して件数・金額を加算し、率を分母から再計算する。未知の版表記を推測で含めない。
4. 日別欠損や朝の公開遅延復旧は[OPERATION_REVIEW_20261011.md](OPERATION_REVIEW_20261011.md)の別手順で確認。版別集計だけでは終日無欠損を証明できない。
5. 実データの結果は新しい日付の報告へ保存し、凍結ルールによる次の判断へ渡す。

今回の作業は研究用集計・合成テスト・研究CI・本引き継ぎ。Android app/、versionCode/versionName、Release workflow、モデル・BUY/SKIP条件・配分、本番統合は変更していない。

**現在の実測基準は引き続き223/360R、残り137R。今回の合成検証で実運用件数は増えていない。次はv0.18.8以降の実評価行を含む私有バックアップでこのヘルパーを実行する。**
