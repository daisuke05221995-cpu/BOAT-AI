# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-25

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: **v0.16.2 / versionCode 37**
- Release target: `256659979f3c4433eb077d534426a7871eb1f69d`
- Build Run `36080778668`: SUCCESS
- Signed Release Run `36080778686`: SUCCESS
- Release ID `396199078`
- APK: `BOAT-AI-v0.16.2.apk`
- APK size: 13,662,586 bytes
- APK SHA-256: `5230d5b61e1d9227a554834ef73018a40e76013588acc0dafd7061d674562622`

## v0.16.2

- 市場非入力Model Aを本番forecastに継続使用。
- 自動BUYはOFF。
- 過去30日Model A仮想成績を固定4点×300円から可変方式へ変更。
- `model-a-retro-flex-v2`: 4〜8点 / 1,000〜3,000円 / 100円単位。
- 2・3着候補を広げ、6〜8点パターンも増やす。
- 結果は選択に使わない。対象日前日までの履歴で予想を再現。
- 終了後オッズは回顧配分のみ。`preCloseOddsClaim=false`。
- 過去表示は直近約1か月。

現在の30日集計（2026-08-26〜2026-09-24）:
- 4,189 races / 1,389 hits / hit rate 33.16%。
- stake 6,304,200円 / payout 5,219,660円 / profit -1,084,540円 / ROI 82.80%。
- 平均5.37点 / 平均1,505円。
- 4点 1,538 / 5点 1,029 / 6点 661 / 7点 437 / 8点 524。
- ROI: 4点78.50 / 5点93.49 / 6点90.99 / 7点61.01 / 8点83.24%。

点数別ROIは診断値であり、30日結果を見て後付けで点数を選ぶためには使わない。

## Model A forecast検証

September holdout Run `35993900879`: PASS。
Q4 final holdout Run `36004272796`: PASS。
- Q4 first Top1 57.8093% vs baseline 46.1500%。
- trifecta Top4 30.6153% vs 19.3763%。
- LogLoss 3.761125 vs 4.181624。

Android parity Run `36001980730`: SUCCESS。

## 購入AI

- historical odds verdict: `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`。
- 締切前取得時刻を証明できないため購入ROIで本番昇格しない。
- 自動BUY OFFを維持。

## Release gate

- Build `36080778668`: live API / Unit test / lint / Debug APK / upload 全SUCCESS。
- Signed Release `36080778686`: test / lint / signed APK / signature verify / GitHub Release publish 全SUCCESS。

## 次に確認すること

1. v0.16.2へ上書き更新。アンインストール・データ消去はしない。
2. 過去レース詳細で可変4〜8点と各点金額を確認。
3. 損益画面で30日全体と点数別診断を確認。
4. 次の未使用期間で5〜6点優位が再現するか検証する。
5. 実運用forecast/history catch-up/fallbackを監視する。
