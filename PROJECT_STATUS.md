# BOAT AI 引継ぎメモ

更新日: 2026-09-25

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: **v0.16.2**
- versionCode: **37** / versionName: **0.16.2**
- Release target commit: `256659979f3c4433eb077d534426a7871eb1f69d`
- Build Run: `36080778668` SUCCESS
- Signed Release Run: `36080778686` SUCCESS
- Release ID: `396199078`
- Release asset: `BOAT-AI-v0.16.2.apk` (13,662,586 bytes)
- APK SHA-256: `5230d5b61e1d9227a554834ef73018a40e76013588acc0dafd7061d674562622`
- 復旧モード / `CrashRecoveryStore` は維持。ユーザーデータ削除・アンインストールは禁止。

## Android v0.16.2

市場非入力のforecast-only **Model A** を本番予想へ統合したv0.16系を継続。

- 3段 conditional grouped-softmax LightGBM / temperature 1.0。
- 本番予想順位はオッズを入力に使わない。
- 120通り3連単確率を生成。
- 手動購入導線は利用可能。
- **自動BUY推奨はOFFのまま。**
- Model A asset/historyが欠損・古い場合はfail-closedし、v0.15.16純AIforecastへfallback。

### v0.16.2の主変更: 過去30日Model A仮想成績の可変化

固定4点×300円を廃止し、過去レースの参考表示を以下へ変更。

- strategy: `model-a-retro-flex-v2`
- 4〜8点で可変。
- 1レース総額1,000〜3,000円。
- 100円単位。
- 2・3着候補を広げる設計を優先し、6〜8点パターンも明確に増加。
- 対象日の予想は対象日前日までの履歴だけで再現。同日/未来結果リークなし。
- 結果は買い目/金額決定に使用しない (`resultUsedForSelection=false`)。
- 終了後オッズは可変配分の**回顧分析**にのみ使用 (`postRaceOddsAllocation=true`)。
- `preCloseOddsClaim=false`。締切前に同価格で買えたことを示すROIではない。
- 過去表示は直近約1か月。

2026-08-26〜2026-09-24の30日集計:
- races: 4,189
- hits: 1,389
- hit rate: 33.16%
- stake: 6,304,200円
- payout: 5,219,660円
- profit: -1,084,540円
- ROI: 82.80%
- average points: 5.37
- average stake: 1,505円
- 点数分布: 4点 1,538 / 5点 1,029 / 6点 661 / 7点 437 / 8点 524。
- 点数別ROI: 4点 78.50% / 5点 93.49% / 6点 90.99% / 7点 61.01% / 8点 83.24%。

点数別ROIは診断値。30日結果を見て点数を後付け選択する用途には使わない。

## Model A検証

固定Model A:
- train through 2025-05-31。
- validation / early stopping / temperature through 2025-06-30。
- Model Run `35940833546` / Artifact `10784912368`。

### 2025年9月 独立holdout

Run `35993900879` SUCCESS / 3,956 races / coverage 99.9242%。
- first Top1 55.308% vs baseline 44.085%。
- first Top2 75.126% vs 66.785%。
- trifecta Top4 27.856% vs 18.579%。
- Top8 43.453% vs 30.713%。
- LogLoss 3.844202 vs 4.225358。
- Brier 0.963136 vs 0.978731。
- Decision `PASS_FORECAST_HOLDOUT`。

### 2025年10〜12月 Q4 final holdout

Protocol commit `3a56378244dd1f3621f862ac89cea3db8ccea6af` をQ4初回アクセス前に固定。
Run `36004272796` SUCCESS / 11,896 races / coverage 99.9412% / leak0 / duplicates0。
- first Top1 57.8093% vs 46.1500%。
- first Top2 76.5467% vs 67.6278%。
- trifecta Top1 10.6254% vs 5.9011%。
- trifecta Top4 30.6153% vs 19.3763%。
- trifecta Top8 46.7384% vs 31.9519%。
- LogLoss 3.761125 vs 4.181624。
- Brier 0.957727 vs 0.976797。
- Decision `PASS_Q4_FINAL_FORECAST`。

## Android parity / 性能

Dedicated parity Run `36001980730` SUCCESS。
- Python LightGBM 4.6.0 vs Kotlin raw score: 3,072 rows PASS。
- 実pre-race 64 races ×120 probability chain PASS。
- player/course history parity PASS。
- compact history byte parity PASS。
- CI JVM smoke: forecast median 6.212ms / P95 7.806ms。

## 購入AI

本番昇格禁止を継続。

- 歴史オッズ監査: `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`。
- 締切前/T-5取得時刻を証明できない。
- v0.16.2の過去可変損益は回顧診断であり、実現可能な購入ROIではない。
- r1〜r4 / OOF購入policyは不採用。
- **自動BUYはOFF。**

## Release検証

Release target `256659979f3c4433eb077d534426a7871eb1f69d`。

- Build `36080778668`: live API schema / Unit test / lint / Debug APK / upload 全SUCCESS。
- Signed Release `36080778686`: Release test / lint / signed APK / signature verify / GitHub Release publish 全SUCCESS。

## 次の作業

1. v0.16.2を実機へ上書き更新し、過去レースの可変4〜8点・金額表示・損益カード・点数別診断を確認する。
2. 次の未使用期間で5〜6点が高ROIという傾向を再検証し、30日結果への後付け最適化を避ける。
3. 実運用forecast結果、history catch-up、fallbackを監視する。
4. 購入AIは監査可能な締切前オッズ基盤を新設してから別研究として再開する。
