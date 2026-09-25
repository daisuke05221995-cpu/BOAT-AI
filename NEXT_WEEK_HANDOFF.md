# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-25

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: **v0.16.3 / versionCode 38**
- Release target: `7a3ffe365707c7a1a99b790b3c8eb0aabb45c4de`
- Build Run `36101879628`: SUCCESS
- Signed Release Run `36101879634`: SUCCESS
- Release ID `396356442`
- APK: `BOAT-AI-v0.16.3.apk`
- APK size: 13,678,970 bytes
- APK SHA-256: `f054736d1e83a6abb7f50cfb2e5a58f5ac6c41507d1adaad0b9efe1be6316c51`

## v0.16.3

- 市場非入力Model Aを本番forecastに継続使用。
- Model Aの予想順位・120通り確率にはオッズを入力しない。
- 現在の公式3連単120通りライブオッズを別レイヤーで取得し、購入推奨 / 見送りを判定する。
- 4〜8点 / 1,000〜3,000円 / 100円単位。
- BUYは、Model A確率×現在オッズによる期待対数効用が「買わない」より高く、モデル上の期待回収率が100%超の場合のみ。
- ライブオッズ未取得、直前情報不足、購入時間外はSKIP。
- ライブ購入モード中は旧confidence BUYへフォールバックしない。
- 選択中の購入可能レースは60秒ごとにオッズを再取得・再判定。
- 一覧/一括用には購入可能かつ直前情報が揃ったレースを順次評価。
- AI SKIP時の手動購入候補はAI仮想損益・購入推奨のみ一括選択へ混ぜない。
- 外部投票の自動実行はしない。最終購入操作はユーザーが行う。

安全経路修正後CI Run `36101624563`: live API / Unit test / lint / Debug APK / upload 全SUCCESS。

## 過去30日Model A参考表示

v0.16.2で追加した `model-a-retro-flex-v2` を継続。

- 4〜8点 / 1,000〜3,000円 / 100円単位。
- 結果は選択に使わず、対象日前日までの履歴だけで予想を再現。
- 終了後オッズは回顧配分のみ。`preCloseOddsClaim=false`。

30日集計（2026-08-26〜2026-09-24）:
- 4,189 races / 1,389 hits / hit rate 33.16%。
- stake 6,304,200円 / payout 5,219,660円 / profit -1,084,540円 / ROI 82.80%。
- 平均5.37点 / 平均1,505円。
- 4点 1,538 / 5点 1,029 / 6点 661 / 7点 437 / 8点 524。
- ROI: 4点78.50 / 5点93.49 / 6点90.99 / 7点61.01 / 8点83.24%。

このROIは回顧診断であり、v0.16.3ライブ購入判定の実現可能ROIではない。

## Model A forecast検証

September holdout Run `35993900879`: PASS。
Q4 final holdout Run `36004272796`: PASS。
- Q4 first Top1 57.8093% vs baseline 46.1500%。
- trifecta Top4 30.6153% vs 19.3763%。
- LogLoss 3.761125 vs 4.181624。

Android parity Run `36001980730`: SUCCESS。

## 購入判定の検証上の注意

- historical odds verdict: `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`。
- 過去オッズは締切前取得時刻を証明できないため、本番購入ROIの根拠にしない。
- `RELEASE_QUALIFIED=false` / `HISTORICAL_ROI_APPLIES_TO_CURRENT=false`。
- v0.16.3は実運用時に取得した現在の公式オッズを使うライブ推奨レイヤー。

## Release gate

- Build `36101879628`: live API / Unit test / lint / Debug APK / upload 全SUCCESS。
- Signed Release `36101879634`: version check / signing / test / lint / signed APK / signature verify / GitHub Release publish 全SUCCESS。
- Release ID `396356442` / APK SHA-256 `f054736d1e83a6abb7f50cfb2e5a58f5ac6c41507d1adaad0b9efe1be6316c51`。

## 次に確認すること

1. v0.16.3へ上書き更新。アンインストール・データ消去はしない。
2. 当日Model A forecast表示とfallbackを確認。
3. 展示・進入が揃った購入可能レースで120通りオッズ取得後、購入推奨 / 見送り・4〜8点・金額を確認。
4. 詳細画面を開いた購入可能レースの60秒再評価を確認。
5. ライブ購入推奨の実績を蓄積し、過去30日回顧ROIとは分離して評価する。
