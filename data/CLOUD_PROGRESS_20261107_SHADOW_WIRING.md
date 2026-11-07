# 2026-11-07 Cloud Worker: 固定Model A 120確率のshadow実行接続

## 今回の統合

- `model-a-live-input.mjs` の厳格ゲートをCron T-8/T-5に接続。出走元 `ROSTER_API_URL` を追加し、preview/oddsと同様にHTTPS・同一レースID・観測時刻を要求。日付フィードの候補出走表では代用しない。
- `MODEL_A_APPROVED_SOURCES_JSON` は明示的に照会・承認済みの出走/展示/気象/オッズ source IDの配列を要求。自己申告や架空の `licensed` 値だけでは認可しない。
- D1の `model_a_history_active` と `model_a_frozen_bundle` に対し、全アセットのSHA・当日ではなく前日までの履歴日付・LightGBM3本を確認した場合だけ120通り確率を計算。
- 固定モデル bundle SHA: `c6d44a4bc9e2f27a4066c25ef0d375ec47055c566695ebfc30043c90433a4f2e`。
- `0010_model_a_shadow.sql` へT-8/T-5別に `FORECAST_ONLY` / `UNAVAILABLE` と安全理由を記録。Android向け `/v1/forecasts` は一切変更せず、集計のみ `/v1/model-a-shadow?date=...` を追加。
- 同じCron内のレース間でモデル・履歴の検証ロード結果を共有。失敗時・締切後・2分期限切れでは確率を残さない。
- 実購入・AI仮想購入・BUY/SKIP、旧Android公式オッズ、2025 Q4 holdout、研究用BAH1、学習パラメータには触れない。

## 検証

- `cd cloud/forecast-worker && npm test`: 117/117成功（新規に入力統合→推論→120確率、履歴期限切れ・未認証元拒否・D1 shadow保存制約・公開API情報最小化を追加）。
- 未実施：利用許可済み4元による実レースshadow、当日前日履歴の連続昇格、実レースのAndroid完全一致、クラウドBUY/SKIP。テストの有効入力は人工fixtureでありライブ的中率を示さない。

## 次に進める工程（WorkのPR #42とは分担維持）

1. 2026-09-24以降の全国全開催分を、日付・全6艇結果・欠場等の理由付きで監査し `model_a_history_active` を**欠損日なく**前日まで進める。研究用 `data/model_a_recent_history.bin` を証跡なしに採用しない。
2. 許諾確認と観測時刻・120オッズと出走登録番号の整合性が取れた実フィードを4sourceとして登録し、Cronの `FORECAST_ONLY` 完備率を集計。
3. 同じライブ入力をAndroidとWorkerへ与え、各120確率を比較。実購入推奨・仮想収支への昇格はその後の独立評価で行う。
