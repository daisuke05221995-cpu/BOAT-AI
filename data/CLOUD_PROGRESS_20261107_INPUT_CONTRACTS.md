# BOAT AI 直前・過去日入力契約の追加 — 2026-11-07 JST

## 再開基点

- main: `783097cc0bb19ca4f491887e4b2d9d8b865c320e`（PR #45）。Cloudflare D1世代保存migration、cloud contract、Android buildはいずれもSUCCESS。
- Workの直前情報取得元調査PR #42はopen。本PRは調査報告・監査スクリプトに触れず、通常チャット担当の製品入力契約だけ変更。
- 固定Android履歴は2026-09-23まで。実レースの履歴をまだ1日も更新していない。モデルを再学習しない。

## 今回の実装

1. **直前展示ゲートの修正**: `preclose.mjs` の6艇展示/進入チェックに、6艇の展示STと事前気象（風速・風向・波高・気温・水温）を追加。気象には展示とは独立した`weather_source`と`weather_observed_at`が必要。いずれも締切前かつ2分以内の実観測でなければ取得完了にしない。
   - `0005_weather_provenance.sql` で気象の出典・観測時刻をD1の別列に保存し、公開read-only APIでも追跡可能にする。古いレコードの気象観測時刻を現在時刻で埋めることはしない。
2. **過去日データの非通信正規化**: `model-a-historical-normalizer.mjs`。公開されている`boatraceopenapi` v1のスキーマに相当する入力を、Model Aの事前特徴量形式に変換する。出走表/展示/結果のレースID、全6艇の登録番号と着順、展示ST・進入・事前気象を確認。結果側の気象・本番ST・本番進入を事前特徴量に使わない。
3. **例外処理**: `place_number>=7`、同着、欠場、レースID・選手ID不一致、展示欠損、結果欠損を拒否。中止は`day_number_source`に明記された`中止`/`順延`のみ受け付け、履歴へ架空の成績を加えない。
4. **監査ステータス**: 正規化出力は`SOURCE_COVERAGE_UNVERIFIED`。入力は非公式かつ完全性非保証で、全国の全開催レースの網羅性・上流の再利用許諾・実際の締切前観測時刻を**独立に証明していない**。Cron/D1履歴有効化には接続していない。
5. テストは実データをダウンロードせず人工fixtureのみ使用。2025年Q4の検証用データや購入履歴にもアクセスなし。

## 調査した一次資料

- `https://github.com/boatraceopenapi/api/blob/gh-pages/README.md`：非公式、約10分更新と10〜20分反映遅延、正確性・完全性を保証しない旨が明記。
- `https://github.com/boatraceopenapi/api/blob/gh-pages/docs/v1/schema.md`：出走表・直前・結果の項目、中止/同着/返還・欠損値、スタート展示と本番STの違いを明記。過去日のpreviewは再取得後の最終値で、実際の締切前観測と異なる可能性がある。

上記の公開コードがMIT表記であることを、上流の全データのクラウド再配信許諾と同一視しない。

## 次の実装順

1. 許諾が明確な過去結果データ源と**独立の全国開催母数**を確定する。それまでは`SOURCE_COVERAGE_UNVERIFIED`から`VALIDATED_AGAINST_SUPPLIED_MANIFEST`へ自動昇格させない。
2. 観測時刻・出典の証拠を持つ実日次バッチについて、9/24から前日まで日付順に`reconcileModelAHistoryDay`→D1のstage→全ハッシュ検証→CAS有効化する。欠損日では停止。旧履歴は保持。
3. 直前展示/オッズ許諾とModel A実レースパリティが成立するまで、WorkerのクラウドBUY/SKIPを有効にしない。

**ここでの契約テスト成功はライブAPIの取得成功率・実レースでの予想精度・ROIの証拠ではない。**
