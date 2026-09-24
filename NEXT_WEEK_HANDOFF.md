# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-24

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: **v0.16.0 / versionCode 35**
- Release target: `ef87c862a79bce0fbb68e5399798b215e5914ae7`
- Build Run `36006839510`: SUCCESS
- Signed Release Run `36006839426`: SUCCESS
- Release ID `395728675`
- APK: `BOAT-AI-v0.16.0.apk`
- APK size: 13,662,586 bytes
- APK SHA-256: `78da792f0f577a67ed0c8610f08fbc61c4fc838f9d418e2c79618b7de83e5a10`

## v0.16.0 forecast

- 市場非入力Model Aを本番forecastへ統合。
- 3段conditional grouped-softmax LightGBM / temperature 1.0。
- 120通り3連単確率から上位4点表示。
- 予想順位にオッズを使わない。
- 手動購入は利用可能。
- **自動BUYはOFF継続。**
- Model A asset/historyが欠損・古い場合はv0.15.16純AIforecastへ安全にfallback。

## 最終検証

### September independent holdout
Run `35993900879` SUCCESS / 3,956 races。
- first Top1 55.308% vs baseline 44.085%。
- trifecta Top4 27.856% vs 18.579%。
- LogLoss 3.844202 vs 4.225358。
- Decision `PASS_FORECAST_HOLDOUT`。

### Q4 final holdout
Protocol commit `3a56378244dd1f3621f862ac89cea3db8ccea6af` をQ4初回アクセス前に固定。
Run `36004272796` SUCCESS / 11,896 races / coverage 99.9412% / leak0 / duplicates0。
- first Top1 **57.8093% vs 46.1500%**。
- first Top2 **76.5467% vs 67.6278%**。
- trifecta Top1 **10.6254% vs 5.9011%**。
- trifecta Top4 **30.6153% vs 19.3763%**。
- trifecta Top8 **46.7384% vs 31.9519%**。
- LogLoss **3.761125 vs 4.181624**。
- Brier **0.957727 vs 0.976797**。
- LogLoss差 day-block bootstrap 95% CI **[-0.440041,-0.402842]**。
- Decision **`PASS_Q4_FINAL_FORECAST`**。

## Android parity / deployment

Parity Run `36001980730` SUCCESS。
- 3,072 raw-score rows PASS。
- 64 actual races ×120 probabilities PASS。
- player history parity PASS。
- compact state parity PASS。
- forecast median 6.212ms / P95 7.806ms on CI JVM smoke。

Deployment Run `36005654248` SUCCESS / Artifact `10810058921`。
- history through 2026-09-23。
- updateRaces 141,542。
- players 1,726。
- compact history 4,222,646 bytes。
- history SHA `a180aa722ad0520b5d86705bac742ff588309e72a49bed373eabf102f257acc3`。
- 起動時に前日まで日次catch-up。同日結果混入なし。

## 購入AI

- 歴史オッズ判定 `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`。
- 締切前取得時刻を証明できないためROIによる本番昇格を停止。
- r1〜r4 / OOF購入候補は不採用。
- Model AのPASSはforecast品質だけで、購入ROIを意味しない。
- 監査可能な締切前オッズ基盤ができるまで自動BUYを再開しない。

## Release gate

- Final pre-version Run `36006480052`: live API / Unit test / lint / Debug APK / upload 全SUCCESS。
- v0.16.0 Build `36006839510`: 全SUCCESS。
- Signed Release `36006839426`: Release test / lint / signed APK / signature verify / GitHub Release publish 全SUCCESS。

## 次に確認すること

1. v0.15.16からv0.16.0へ上書き更新する。アンインストール・データ消去はしない。
2. 実機でModel Aの予想上位4点表示を確認。
3. 手動購入、結果、損益、更新機能が従来どおり動くか確認。
4. 日次history catch-upが失敗した場合はfallbackすることを確認。
5. forecast実運用データを蓄積する。
6. 購入AI研究は新しいpre-close odds基盤から別途再開する。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`data/v016_q4_forecast_decision.json`、`data/v016_release_readiness.md`、v0.16.0 Release、最新main、最新Actionsを確認する。
