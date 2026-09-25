# BOAT AI 引継ぎメモ

更新日: 2026-09-25

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: **v0.16.3**
- versionCode: **38** / versionName: **0.16.3**
- Release target commit: `7a3ffe365707c7a1a99b790b3c8eb0aabb45c4de`
- Build Run: `36101879628` SUCCESS
- Signed Release Run: `36101879634` SUCCESS
- Release ID: `396356442`
- Release asset: `BOAT-AI-v0.16.3.apk` (13,678,970 bytes)
- APK SHA-256: `f054736d1e83a6abb7f50cfb2e5a58f5ac6c41507d1adaad0b9efe1be6316c51`
- 復旧モード / `CrashRecoveryStore` は維持。ユーザーデータ削除・アンインストールは禁止。既存アプリへ上書き更新する。

## Android v0.16.3

市場非入力の **Model A forecast** を本番予想に継続使用し、現在の公式3連単ライブオッズを別レイヤーで組み合わせる **購入推奨 / 見送り判定** を追加した。

- 3段 conditional grouped-softmax LightGBM / temperature 1.0。
- Model Aの予想順位・120通り確率はオッズを入力に使わない。
- 購入判定時だけ現在の公式3連単120通りオッズを取得する。
- 4〜8点、1レース総額1,000〜3,000円、100円単位で配分する。
- BUY条件は、Model A確率×現在オッズを使った期待対数効用が「買わない」より高く、かつモデル上の期待回収率が100%を超えること。
- 条件を満たさない場合はSKIP。
- 120通りオッズ未取得、展示・進入など直前情報不足、締切後/購入時間外は安全側でSKIP。
- ライブ購入判定が有効な間は旧confidence BUYへフォールバックしない。
- 詳細画面で選択中かつ購入可能なレースは60秒ごとにライブオッズを再取得して再判定する。
- 一覧/一括選択用には、購入可能かつ直前情報が揃ったレースを順次120通りオッズ評価する。
- AIがSKIPしたレースでも手動購入用候補の表示は可能だが、AI仮想損益や「購入推奨のみ」一括選択には混ぜない。
- **外部投票の自動実行はしない。** 最終購入操作はユーザーが行う。
- Model A asset/historyが欠損・古い場合はfail-closedし、forecast側は既存fallbackを維持する。

### v0.16.3で修正した重要な安全経路

購入推奨をONにした直後、ライブオッズ評価前のレースが旧ロジックのBUYへ落ちる経路が残っていたため修正した。

- `PredictionEngine.recommendation()` はライブModel A購入モード中、キャッシュ済みライブ判定がない場合に旧BUYロジックへ進まない。
- ライブオッズ評価待ちはSKIPとして扱う。
- `ModelAProductionReleaseGateTest` を現仕様へ更新。
- `RecommendationDecisionTest` に「強いレースでもライブオッズ未評価なら旧BUYしない」回帰テストを追加。
- 修正後CI Run `36101624563` は live API / Unit test / lint / Debug APK / upload 全SUCCESS。

## 過去30日Model A参考表示

v0.16.2で導入した回顧表示はv0.16.3でも継続。

- strategy: `model-a-retro-flex-v2`
- 4〜8点で可変。
- 1レース総額1,000〜3,000円。
- 100円単位。
- 対象日の予想は対象日前日までの履歴だけで再現。同日/未来結果リークなし。
- 結果は買い目/金額決定に使用しない (`resultUsedForSelection=false`)。
- 終了後オッズは可変配分の**回顧分析**にのみ使用 (`postRaceOddsAllocation=true`)。
- `preCloseOddsClaim=false`。締切前に同価格で買えたことを示すROIではない。

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

この30日ROI・点数別ROIは回顧診断値で、v0.16.3のライブ購入判定の実現ROIを示すものではない。

## Model A forecast検証

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

## 購入判定の検証上の位置付け

v0.16.3ではライブの購入推奨機能を提供するが、**過去ROIで本番性能を保証したものではない**。

- 歴史オッズ監査: `ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST`。
- 過去データでは締切前/T-5取得時刻を証明できない。
- したがって過去の最終-likeオッズを使ったROIをライブ政策の実現可能ROIとして扱わない。
- `RELEASE_QUALIFIED=false` / `HISTORICAL_ROI_APPLIES_TO_CURRENT=false` を維持。
- r1〜r4 / OOFの過去購入policyをそのまま本番採用したわけではない。
- v0.16.3の購入推奨は、実運用時点で取得した現在の公式オッズを用いる独立したライブ判定レイヤー。

## Release検証

Release target `7a3ffe365707c7a1a99b790b3c8eb0aabb45c4de`。

- Build `36101879628`: live API schema / Unit test / lint / Debug APK / upload 全SUCCESS。
- Signed Release `36101879634`: version check / signing secrets / Release test / lint / signed APK / signature verify / GitHub Release publish 全SUCCESS。
- Release `v0.16.3`: ID `396356442`。
- APK `BOAT-AI-v0.16.3.apk`: 13,678,970 bytes。
- SHA-256: `f054736d1e83a6abb7f50cfb2e5a58f5ac6c41507d1adaad0b9efe1be6316c51`。

## 次の作業

1. v0.16.3を実機へ**上書き更新**する。アンインストール・データ消去はしない。
2. 当日レースでModel A予想が従来どおり市場非入力で表示されることを確認する。
3. 展示・進入が揃った購入可能レースで、公式120通りオッズ取得後に購入推奨 / 見送りと4〜8点・各金額が表示されることを確認する。
4. 詳細を開いた購入可能レースで60秒再評価が行われることを確認する。
5. ライブ運用データを蓄積し、購入推奨の実績は回顧ROIと分離して評価する。
