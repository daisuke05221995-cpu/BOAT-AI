# BOAT AI Cloud 定期取得監査 — 2026-11-07

## 目的・スコープ

モデルの保存成功と、締切前展示・オッズ・結果を実際に取得できているかを別々に評価する。Cloudflare Workerの既存 `/v1/audit?date=YYYY-MM-DD` を読み取り専用で参照し、毎日2回GitHub Actionsに監査記録を残す。**取得元への無断アクセス、モデル再学習、予想の事後生成、D1への書込みは実施しない。**

## 自動処理

- Workflow: `.github/workflows/cloud-daily-operational-audit.yml`
- JST: 毎日11:15（開催・Cron観測）、翌01:10（前日結果回収観測）、mainの本workflowまたは集計コード更新時にも実行
- 対象: 前日と当日。実行日JSTを基準に算定
- 出力: `boat-ai-cloud-operational-audit` という30日保存のJSON artifact、GitHub Actions Summaryの日別比較表
- 異常系: API不通・スキーマ変化・結果数矛盾・BUY/SKIP数矛盾はjobを失敗させる。正常な空レース・未取得のための `UNAVAILABLE` では緑になっても**取得成功扱いにしない**

## 判定

1. D1日別開催数と `daily_import` 件数
2. Cronの開始・終了状態
3. T-8/T-5試行数と出典・時刻・120オッズ等の条件を満たした記録数
4. `BUY/SKIP` と未取得`UNAVAILABLE`を分離（未取得を的中率分母に含めない）
5. 結果締切20分後以降の回収率。通常・返還不成立・順延・中止と未解決を分離
6. 研究用BAH1の同日出走数÷6とD1の成立結果件数を**件数だけ**比較。研究履歴は国全体の網羅性・事前情報の許可を示さず、差分解消後も独立証拠がない限り本番昇格を禁止

## 初回本番観測（Run 42359413922、2026-11-07 18:21 JST）

- 11/06: `scheduled=156`、`results.due=156`、`recorded=156`（`legacy_settled=144`、`postponed=12`）、締切前の完全取得0件。Cronは前日分なので `STALE` 表記だが最終完了記録あり。
- 11/07: `scheduled=132`、観測時点の `deadlines_passed=117`、T-8=118件/T-5=118件。締切前完全取得0件、失敗 `PREVIEW_PROVIDER_NOT_CONFIGURED` 236件。結果 `due=115`、`recorded=114`、`unresolved_due=1`（`RESULT_NOT_FINAL`）。当日Cronは `ACTIVE`。
- 両日クラウドのAI `BUY=0`、`SKIP=0`。未取得をSKIP数・的中率分母へ入れていない。
- 研究用 `model_a_recent_history.bin` は11/06までの出走回数から**11/06の132レース更新**を示す。D1で成立として扱われた144レースと**12件差**。確定不能や欠落など原因未確定のため、日付を最新として昇格しない。差分は件数監査の対象であり、独立した全国網羅性の証明ではない。

## 次のゲート

- 初回本番監査Runの数値を確認し、Workerで今どの収集が動いていてどれが未設定なのかを明示する。
- 9/24から前日までの独立した全国出走予定・全6艇結果・欠損/重複を日別に照合し、合格日のみ履歴更新。欠損日は停止。
- Work PR #42の許諾済み直前取得元が確定し次第、レースID/時刻/120オッズの前向き完備率を検証し、合格まではクラウドBUYを有効化しない。
