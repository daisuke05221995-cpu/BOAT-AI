# 2026-11-08 23:56 JST Androidオッズの取得範囲の分類（研究）

## 前回からの差分

前回の本人購入後の履歴照合（研究用152テスト）を繰り返さず、既存Android `OddsFetchResult` の**取得範囲と推定値を区別する純粋関数**を追加。

- `scripts/android_odds_coverage_classifier.mjs` は `result.odds/source/diagnostics/fetchedAt` と**呼び出し側が実際に要求した組番リスト**を照合する。
- `ANDROID_120_VALUES_UNATTESTED` は公式PC/スマホというラベルかつ全120種類が要求・返却された場合のみ。実測オッズの利用許諾/元観測時刻の独立証明とは別。
- `ANDROID_SELECTED_ONLY` は3〜6点など要求された組番のみ。120通りと偽らない。
- `BOATRACE_CSV_ESTIMATE` は推定フォールバック。120個揃っていても実オッズとみなさない。
- 欠損/余計な組番/不正なオッズ/未知ソース/要求リスト不正は `UNAVAILABLE`。いずれも `eligible_for_forecast=false` / `eligible_for_buy=false` / `eligible_for_skip=false`。元観測時刻を捏造しない。値をログ出力しない。
- 外部アクセス/Android編集/購入操作/holdoutアクセスなし。研究コードと回帰テストだけ。

## コミットと検証

- 実装 `aa519d40e292bc8ee03e3039dd4b917f3f9c4182`
- テスト（18件追加） `07bd079f05325c210053162ab190e85e89277664`
- CI変更 `ec51c5bace42bf1073b98bc5e730fa28dcf6038f`
- GitHub Actions研究用Run `42492317995`：**起動確認、結果は確認待ち**。従来Run `42487299471` 成功は旧コミットの結果であり、新テストの成功とはしない。
- 実機120件・T-8のソース元観測時刻・許諾・再配信可否は未測定/未確認。

## 重要な既存文書の食い違い

`PROJECT_STATUS.md` に2025Q4の最終評価 `PASS_Q4_FINAL_FORECAST` とRun `36004272796` が既に記録されている。一方で今回の依頼文は「Q4未開封」。**新たなQ4取得・閲覧・再学習は一切実施せず**、既存記録の真偽・時系列の調査は別の非holdout作業に切り分ける。未開封だったと断定しない。

## ブロッカーと次の一手

1. PR #42 の提供元許諾/観測時刻真正性/T-8成功は未確認。認可を得るまでは取得・再配信しない。
2. Android担当が実際の `OddsFetchResult` と要求した組番の対応を端末内だけで検証し、ソースラベルだけでBUY/SKIPへ昇格させない。
3. 公式アプリの自動投票は利用規約・提供元許諾が未確認のため有効化しない。本人の公式アプリ手動購入と履歴照合を優先。
4. CI Run `42492317995` の終了結果/テスト件数を確認してPRへ追記。

変更禁止領域 `app/**`、本番Worker、Model A、本番設定、APK、購入履歴、2025Q4 holdoutは触っていない。
