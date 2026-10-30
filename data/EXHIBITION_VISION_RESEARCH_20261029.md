# BOAT AI — 展示映像AI 研究用フレームワーク（2026-10-29）

## 目的と現在の位置

出足・行き足・伸び足・回り足・ターン性能を、許諾済みの展示映像から同一レース6艇を比較できる数値へ変換する。将来的にModel Aと別のModel Bとして評価し、前向き独立検証を通過した場合だけアプリの予想に統合する。

**現段階で動作するもの:** 映像検出器による較正済みの艇軌跡（m/秒・走行区間ラベル）から7つの物理的測定値を算出する試作、測定値の妥当性チェック、5項目の仮スコア(0〜100)、6艇順位付け、欠損・低画質・締切後リークの検出、許可済み提供元のJSONフィード自動巡回インターフェース、テスト/Actions。

**まだ動作しないもの:** BOATCAST映像の自動取得、実映像の艇検出・追跡、カメラ較正、実映像からの物理測定値算出、全国24場の常時運用、Androidへの表示・Model Aとの融合。これらを完了したとは主張しない。

## 計測項目（研究用仮説）

| 画面表記 | detector出力 | 単位 | 指数の方向 |
|---|---|---|---|
| 出足 | `exit_acceleration_mps2` — ターン出口の加速度 | m/s² | 大きい方が上 |
| 行き足 | `runup_acceleration_mps2` — 進入・助走時の加速度 | m/s² | 大きい方が上 |
| 伸び足 | `straight_speed_mps` — 直線中の速度 | m/s | 大きい方が上 |
| 回り足 | `turn_speed_mps` — ターン区間の速度 | m/s | 大きい方が上 |
| ターン性能 | 旋回時間40% + 最低速度維持35% + マークへの近さ25% | 仮合成指数 | 大きい方が上 |

ターン性能は `turn_time_s`（小さい方が上）、`turn_min_speed_retention`（0〜1、大きい方が上）、`turn_marker_clearance_m`（小さい方が上）から合成する。**配点の根拠はまだ実戦結果で検証していない。** 公式の展示タイムを出足・回り足と呼び替えたものではない。必要な映像座標はカメラの射影変換で実距離へ較正し、観測区間の定義を固定しなければならない。

指数は同じレース6艇の平均と、各指標の最小有意スケールで正規化した **相対比較指数**。レースをまたぐ絶対能力や1着確率ではない。同点/微小差は同順位にできる。各指標と全体指数を必ず分けて保存し、後から的中した艇を見て配点を調整しない。

`scripts/exhibition_vision/kinematics.py` は、外部の映像AIから提供された較正済みの各艇軌跡 `t, x_m, y_m, phase`（`runup` / `straight` / `turn` / `exit`）を受け取って上記7計測値に変換する。座標値は必ずm。画素をmと偽って投入できないよう、インターフェースを分けている。ただしフェーズ認識、カメラ較正、遮蔽・コース深度の補正自体は未実装で、物理量の妥当性は実映像でまだ検証していない。

## データ契約

`scripts/exhibition_vision/scoring.py` に入力するJSONは以下の形。`boats` は1〜6号艇をすべて収録する。

```json
{
  "schema_version": 1,
  "race": {"date": "2026-10-29", "venue": 23, "number": 9, "deadline": "2026-10-29T15:30:00+09:00"},
  "capture": {
    "source_id": "approved-example", "permission_reference": "verified-license-identifier",
    "video_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "detector_version": "detector-1", "calibration_version": "venue23-camera1-v1",
    "captured_at": "2026-10-29T15:20:00+09:00", "analyzed_at": "2026-10-29T15:23:00+09:00"
  },
  "boats": [
    {"lane": 1,
     "quality": {"track_coverage": 0.98, "detector_confidence": 0.97, "calibration_error_m": 0.25},
     "measurements": {
       "exit_acceleration_mps2": 1.5, "runup_acceleration_mps2": 1.4,
       "straight_speed_mps": 20.0, "turn_speed_mps": 12.8,
       "turn_time_s": 5.5, "turn_min_speed_retention": 0.78,
       "turn_marker_clearance_m": 1.2
     }}
  ]
}
```

例は1艇分のみで、実際の入力には必ず6艇を用意。名前、選手ID、後日の確定着順、払戻、オッズは不要・禁止。品質条件は追跡率90%以上、艇検出信頼度85%以上、較正誤差1.0m以下。品質不十分な艇が1艇でもあれば、誤った順位を出さずレース全体を `UNUSABLE` とする。

## 全自動取得へ向けた契約

`scripts/exhibition_vision/worker.py` は、事前に利用が承認された提供元の **測定値フィード** を自動巡回する。無許可で公式配信のストリームURLを解析・抽出しない。

1. 運用者が映像・自動解析の許可を確認し、提供元ID/権利記録/HTTPSホストを登録。
2. 許可済み映像提供元と、別途実装する物体検出・追跡・カメラ較正サービスが、レース番号別に上記JSONを生成。
3. 承認済みフィードが次のマニフェストを配信。workerは許可ホストに限りHTTPSで取得し、リダイレクトと1MB超のJSONを拒否する。

```json
{
  "schema_version": 1,
  "source_id": "approved-example",
  "permission_reference": "verified-license-identifier",
  "entries": [
    {"date": "2026-10-29", "venue": 23, "number": 9,
     "measurement_url": "https://approved.example/exhibition/20261029-23-09.json"}
  ]
}
```

4. 生成されたスコアは `SHADOW_READY`（締切前に解析完了）、`RESEARCH_ONLY_LATE`（解析が締切後）、`UNUSABLE`（品質/来歴/取得時点が不適格）に区分し、どれもAndroidの予想・購入処理には渡さない。
5. GitHub Actionsの研究用ポーリングは15分おきのベストエフォート。`EXHIBITION_AI_FEED_URL` と `EXHIBITION_AI_ALLOWED_HOSTS` を**権利確認後に**設定しない限り外部取得処理は起動しない。数値Artifact公開も `EXHIBITION_AI_ALLOW_ARTIFACTS=true` を別途設定しない限り無効。締切前の安定運用には専用workerが必要。

**注意:** 権利IDを書いたJSONだけでは実際のライセンス成立を証明できない。管理者が許可内容・保存可能範囲・アクセス頻度を個別に確認する。配信URLが閲覧可能なだけでは映像の継続自動取得権限を意味しない。

## テスト

```bash
PYTHONPATH=scripts python3 -m unittest discover -s scripts/exhibition_vision -p 'test_*.py' -v
PYTHONPATH=scripts python3 -m exhibition_vision.scoring licensed_detector_output.json --output shadow_rank.json
PYTHONPATH=scripts python3 -m exhibition_vision.worker --output-dir /tmp/exhibition-shadow
```

3番目のコマンドは提供元未設定なら `SKIPPED_NO_APPROVED_PROVIDER` と出力して通信しない。

## 2026-10-29 追加調査: オリジナル展示データとの照合

- BOAT RACE公式/各開催場は、従来の展示タイムとは別に **一周・まわり足・直線** のオリジナル展示計測値を一部会場で公開している。項目や保存期間・取得方式は開催場に依存する。
- JLC BPSは特定開催において映像とは別に艇の位置・瞬間速度を計測している。現時点で全国全レースの利用可能なAPIとして扱わない。
- `scripts/exhibition_vision/reference.py` を追加。許可された正規の数値取得元から6艇分の計測値を用意できた場合、AI映像指数との順位一致度（Spearman）を検証する。
- 検証対応: 直線タイム↔伸び足、まわり足タイム↔回り足/ターン性能、一周タイム↔総合指数。**出足・行き足については単独で直接対応する公式値が無いため、別の物理計測が必要。**
- 公式計測値が締切後に取得された場合は比較対象から除外。数値の照合はあくまで計測精度の研究であり、予想精度やROIの向上を証明しない。

## 公開リアルタイムCSVの自動取得（映像ではない別系統）

問い合わせを行わず、公開のHTTPSダウンロード仕様が明記された [BoatraceCSV](https://boatracecsv.github.io/) のCSVを研究用に使う。プロジェクトREADMEは **MIT License** を表明し、機械学習・Agent利用向けのCSV URLと約5分間隔の更新を公開している。**ただしMITの表記だけで元の配信映像の著作権や利用許可まで得たことにはならない。映像は取り込まない。**

`scripts/exhibition_vision/public_feed.py` は当日分の以下の4本の公開CSVだけを最大1回ずつ取得する（無限クロール・ストリームURL抽出・外部サイトへの自動問い合わせはしない）。リダイレクト禁止、1本2MiB上限、UTF-8検証、レースコード照合あり。

| パス | 取得項目 | 目的 |
|---|---|---|
| `data/previews/original_exhibition/YYYY/MM/DD.csv` | 一周／半周ラップ・まわり足・直線 | 公表実測タイムの6艇順位、映像AIとの将来照合 |
| `data/previews/tkz/YYYY/MM/DD.csv` | 展示タイム・チルト | 予想候補となり得る既存の直前データ |
| `data/previews/stt/YYYY/MM/DD.csv` | 進入コース・スタート展示ST | 進入隊形、展示スタート |
| `data/previews/sui/YYYY/MM/DD.csv` | 風速・波高 | 気象条件の研究 |

- 2026-10-29の公開実データで `original_exhibition` は108レースを確認。3項目・2項目・半周ラップの会場差あり。江戸川のようにオリジナル展示のない会場でも、その他のソースだけでレースを残せる。
- `retrieved_at` は **我々の取得時刻**、`source_captured_at` は **配信元の収集時刻**。両方が締切前のものだけ `PRE_CLOSE_OBSERVED` とする。締切後に昔のCSVを読んだだけなら必ず `ARCHIVE_ONLY`。締切を過ぎた原始ソースは欠損扱い。
- `original_ranks` は公表タイムに基づく単純な順位（小さい順）で、**動画解析の5性能指数ではない**。出足・行き足・ターン性能は未測定、値は `null`。一周タイムと半周ラップも区別する。オッズ・着順・払戻は入力しない。
- GitHub Actionsの公開CSV巡回はJST 08:00〜22:59に対応するUTC cronで約5分間隔の研究ジョブ。取得した締切前の数値JSONだけを3日保存（Actions Artifact）。GitHub Actionsの起動遅延・CSV公開ラグにより、締切前取得を保証できない。**scheduleイベントはワークフローがデフォルトブランチに取り込まれるまで起動しない。**
- 既存の許可制「映像測定値プロバイダ」workerとは独立。映像権利の確認なしで公開CSVを映像AI扱いにしない。Androidの予想・購入フローも変更しない。

単発で公開CSVを研究用に取り込むコマンド：

```bash
PYTHONPATH=scripts python3 -m exhibition_vision.public_feed --output-dir /tmp/exhibition-public --live-only
```

**次の研究:** 実行ログに締切前取得がどの程度あるかを集計し、その上で元のModel Aと対照比較できる「公開数値を追加したModel B（未本番）」の固定プロトコルを事前登録する。BOATCAST等の映像自動取得と物体検出は、このCSV取込とは別の未実装課題。

## 2026-10-30: Model B研究の入力だけ固定

- `data/EXHIBITION_PUBLIC_MODEL_B_PROTOCOL_20261030.json` に、事前登録のデータ境界、締切前監査、最初の360レース取得健全性監査、後の独立評価条件を保存。既存2025年Q4最終holdoutは開かない。
- `scripts/exhibition_vision/features.py` は `PRE_CLOSE_OBSERVED` の公開数値だけを処理し、各時間項目と展示タイム/スタート展示ST/チルトの**同一レース6艇平均との差**を出す。欠損は `null` とmask。行き足など映像でしか測れない指標を推定したふりはしない。着順・払戻・オッズは出力しない。
- GitHub Actionsの定期収集後、同じ実行の締切前JSONをこのfeature workerに渡し、公開数値のfeature Artifactを3日保持。**Model Bの重み学習、予想出力、Androidの表示やBUYは一切追加しない。**
- 取得健全性の最低条件: 締切前に実取得できた360レース以上、5日以上に分散。モデル候補の予測比較にはさらに1,000レース以上・14日以上の同一レース前向きデータが必要。各期の条件を勝手に緩めない。

## 2026-10-30: 定期収集が起動しない場合の切り分け

- 初回main導入後約2時間、GitHub Actionsの `schedule` による本ワークフロー実行が確認できなかった。GitHub公式仕様でもcron起動は遅延・省略され得る。
- cron表記を `*/5 23,0-13 * * *` に更新し、GitHub上の定期実行設定を再登録する。日本時間08:00〜22:59を意図した5分刻み。
- **本番mainへの研究コードpushでも公開CSV巡回を一度走らせる**スモークテストを追加。これで取得失敗・通信拒否・保存失敗と、単にcronイベント自体が来ない問題を区別する。PR内では取得せずテストのみ。
- 5分間隔が実際に持続する保証ではない。cronが引き続き発火しない場合、別の専用スケジューラによる運用が必要で、運用先・費用・利用権限の範囲は別途確定する。

## 実装ロードマップと採用ゲート

1. **映像取得権利・方式を確認:** 公式または許可された契約提供元。承認不能な場合は動画全自動取得を停止し、合法に利用できる数値情報のみ続行。
2. **単一会場PoC:** 100レース程度の展示映像を正規の方法で用意。艇の識別とカメラ変化、重なり、欠損を検証。5項目の映像実測と専門家の採点の一致度を確認する。
3. **完全自動処理:** 展示公開→映像取得→検出/追跡→較正→5項目→順位の遅延と成功率を記録。締切前に終わらなかったデータはリアルタイム候補に使わない。
4. **予測の独立評価:** 日付順にModel A単独とModel A+展示AIを同一レースで比べる。Top1/Top4/Top8、LogLoss、Brier、校正値、欠損率、締切前の取得率を測る。展示スコアの5重みは開発期間でしか決定しない。
5. **Android統合:** 独立検証と最低限の前向き運用ゲートを満たした後だけ、別バージョンのModel Bとして導入。BUY/SKIPと回収率はさらに独立の監査が必要。旧343件や既存2025年Q4の研究結果を調整用に再利用しない。

過去実績を上げるための後付け調整、既存Model Aの無断変更、払い戻しや結果の動画事前特徴への混入を禁止する。
