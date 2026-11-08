# 2026-11-08 18:04 JST — 重複購入の再実行防止（研究専用）

`scripts/purchase_replay_guard.mjs` を新規実装。レース日・場・R・買い目と100円単位の金額から、順序に依存しないSHA-256計画指紋を生成。**永続化された試行ジャーナルが欠損・破損・過大なら拒否**し、同一指紋にPREPARED/SUBMITTING/UNKNOWN/CONFIRMED/REJECTEDのどれかが残っている場合、タイムアウト経過後でも再試行を自動許可しない。外部受付結果が不明なときの二重投票を防ぐためのfail-closed設計。金額・買い目・日付の不正値や同一買い目の重複も拒否。どの入力でも`allowed_for_live_submission=false`であり、**本番購入機能には未接続**。

追加テストは`scripts/purchase_replay_guard.test.mjs`の15ケース（うち状態別5ケース）。既存46件と合わせて**計61件のオフラインテスト対象**。実装commit `cde789502efed4bc90a4dfaf4e7caa7253d68d09`、テストcommit `50b9a840a607b9ba6f3bf904f1975ad80294eb5a`、CI最終修正 `708dbfc79494c325f0fecb3d58f277483f884208`。Run `42465496308` **SUCCESS：61件成功／失敗0件**。ジョブログで `# tests 61 / # pass 61 / # fail 0` を確認。

次は実機の受付番号を確認できないUNKNOWN状態の再送防止をAndroid担当へ引き継ぐ。本番への自動投票接続や公式画面操作はしない。

元観測時刻・利用許諾が独立に検証された直前展示/120オッズ提供元は依然0件。T-8実ライブ計測なし。2025Q4 holdout未開封、Model A/本番Worker/Androidファイル/Release不変更。
