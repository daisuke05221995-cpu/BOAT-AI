# Model A forecast-only Android deployability監査

- 判定: **FORECAST_READY_FOR_INTEGRATION_DESIGN_PENDING_HOLDOUT**。独立holdout待ち、Android搭載・本番昇格は未実施。
- モデルArtifact: Run 35940833546 / ID 10784912368 / ZIP digest `sha256:58b845fa8d07efe258b08a23ac6caafab2e4854ce4b84618fb4af6ae3f3687fe`。manifest `d39ebab7549689d71f715daee174ec62257f9f9ddbe29f7667256eba8b148da2`。
- 履歴state: 1,670選手、87,491レース更新、2025-08-31まで。これはライブ時点のstateではない。
- 1レースあたり条件付きモデル評価: 1着6行 + 2着30行 + 3着120行 = **156行**。LightGBM 3モデル（[870836, 866899, 847788] bytes）、履歴state 46,888,026 bytes。

## 必要な入力と計算

- 出走表: 選手登録番号、級別、下記のprogram特徴。直前情報: 展示タイム、展示ST、進入コース、風速・波高・気温・水温・風向。場・R番号を使用。レース結果、払戻、実ST/実進入、市場オッズは推論入力にしない。
- boat/current (30): racer_national_top_1_percent, racer_local_top_1_percent, racer_national_top_2_percent, racer_local_top_2_percent, racer_national_top_3_percent, racer_local_top_3_percent, racer_assigned_motor_top_2_percent, racer_assigned_motor_top_3_percent, racer_assigned_boat_top_2_percent, racer_assigned_boat_top_3_percent, racer_average_start_timing, racer_flying_count, racer_late_count, racer_age, racer_weight, racer_exhibition_time, racer_start_timing, racer_course_number, racer_tilt_adjustment, racer_weight_adjustment, class_1, class_2, class_3, class_4, course_changed, ex_rank, preview_st_rank, ex_gap_best, ex_gap_worst, ex_gap_lane1。
- history (32): player_count, player_win, player_top2, player_top3, course_count, course_win, course_top2, course_top3, player_ex_mean, player_ex_sd, player_preview_st_mean, player_preview_st_sd, course_ex_mean, course_ex_sd, course_preview_st_mean, course_preview_st_sd, w30_count, w30_win, w30_top2, w30_top3, w60_count, w60_win, w60_top2, w60_top3, w90_count, w90_win, w90_top2, w90_top3, w180_count, w180_win, w180_top2, w180_top3。
- reaction (20): ex_delta_self, ex_z_self, st_delta_self, st_z_self, ex_delta_course, ex_z_course, st_delta_course, st_z_course, fast_count, fast_win, fast_top2, fast_top3, good_st_count, good_st_win, good_st_top2, good_st_top3, changed_count, changed_win, changed_top2, changed_top3。
- 登録番号は履歴テーブルのキーのみ。2024 seed→日単位に全レースの特徴量snapshotを先に生成→当日の確定結果をまとめて履歴へ反映する。同日の他レース結果を混ぜない。30/60/90/180日窓とglobal/course/class→player→player-courseの縮約を再現する。
- 数値欠損は既存のNaN特徴・LightGBM欠損分岐で扱う。ただし登録番号/6艇/展示・ST/進入コースの必須入力がない場合はModel A予想を出さず、別途承認後に既存予想へフォールバックする。
- Android側はLightGBMのテキストツリーを互換に評価する実装または検証済み変換形式が必要。現在のAndroidで3モデルのパーサ・156行推論・性能・メモリ・端末差は未実装/未計測。
- 推論時に3つのモデルSHA、schema SHA、r4 protocol SHA、履歴state SHA、特徴量計算コード版を検証する。120通り確率和と1着周辺確率和=1を確認する。2025-08-31後のライブ履歴再生は独立holdout方針が確定してから設計する。
- r4モデルと履歴stateの研究用bundle Artifactを保存する。app/へコピーしない。

## 未解決の実装事項

- 再現可能なAndroid推論エンジンと端末ベンチマーク。
- 更新遅延/結果訂正/中止・返還と日次state versionの運用設計。
- 独立した未開封期間でforecast精度を検証した後、通常チャット側で統合判断。
