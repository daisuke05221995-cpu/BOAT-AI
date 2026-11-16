# BOAT AI 前日予想 note 販売仕様（2026-11-16）

前日23:10と23:40 JSTに翌日の全開催から予想を作成する。毎朝の直前情報を待たない。

## 予想モデル
- note-sales/day_ahead.py を追加。歴史的な枠番・選手成績・モーターの評価ロジックを再利用し、2025年末までの固定履歴を利用する。
- 当日の風、波、展示ST、展示タイム、直前オッズ、確定着順は使わない。新しい販売用の前日方式なので、過去の34.0%を前日方式の成績として宣伝しない。
- 出走表に6艇が全て揃うレースのみ処理。選定スコア80以上の全国最大5レース、1レース固定4点、参考配分500/400/200/100円。
- 選定スコアは的中確率や期待回収率ではない。オッズがないためEV・BUYの判定も行わない。
- note無料部分に旧方式の過去検証実績を参考として表示し、「当日展示を使った別方式のため前日版の的中率ではない」と併記する。

## データ源
- 公式BOATRACEの翌日開催情報の公開は通常18時頃、サマー20時頃、ナイター22時頃から。
- そのまま商用で取得・転載できるという意味ではない。商用利用権のある出走表JSONの取得元を確認・契約する必要がある。
- 入力は programs.stadiums 形式で、開催日、締切予定時刻、各レース6艇の national_win_rate / local_win_rate / motor_top_2_percent / boat_top_2_percent / average_start_timing が必要。出走表が欠けていれば予想を作らない。

## GitHub Actions
- 新規 .github/workflows/note-sales-day-ahead.yml を前日23:10/23:40 JSTに定期起動。
- 従来の日中 note-sales-daily.yml は手動のみ、日中定期処理を停止。
- 本番を有効にするGitHub Actions Variables:
  - NOTE_DAY_AHEAD_ENABLED=true
  - BOAT_AI_COMMERCIAL_SOURCE_APPROVED=true （商用利用を確認済みのときだけ）
  - BOAT_AI_DAY_AHEAD_PROGRAM_URL=承認済みHTTPS JSONのURL（{date}又は{compact_date}を含められる）
  - BOAT_AI_DAY_AHEAD_SOURCE_ID=取得元識別名
  - NOTE_AUTO_PUBLISH_ENABLED=true （実note画面をテストしてから）
  - NOTE_BROWSER_UI_VERIFIED=true （有料エリア境界を確認してから）
- Secret: NOTE_SESSION_STATE_B64（本人の認証済みブラウザ状態。チャットに貼らない）
- 自動生成・自動公開は現在初期OFF。商用データ元とnoteアカウントの接続・有料ライン実画面テスト完了前には有効にしない。
- 投稿前の公開メタデータclaim、投稿後の匿名購入画面確認、二重投稿停止ルールは継続。

## 旧実績について
2026年5月の的中559 / 1,644レース（34.0%）は旧条件の過去検証であって、今回の新方式の正確性を示す数字ではない。

## 参考
BOATRACEの更新時刻: https://boatrace.jp/owpc/pc/extra/about.html
note設定の残作業: note-sales/GO_LIVE_ja.md
