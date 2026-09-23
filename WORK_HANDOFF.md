# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

このファイルは、ChatGPT Workと通常チャットを往復してもBOAT AI開発を同じ位置から再開するためのチェックポイントです。

## 作業開始時に必ず確認

1. Repository: `daisuke05221995-cpu/BOAT-AI`
2. Branch: `main`
3. `PROJECT_STATUS.md`
4. `NEXT_WEEK_HANDOFF.md`
5. `WORK_HANDOFF.md`
6. 最新commit
7. 進行中GitHub Actions
8. `data/strategy_search_2026.json`
9. `data/multiyear_validation.json`
10. v14以降の研究結果JSONがあれば確認

## Workでの基本ルール

- ユーザーへ細かい確認を繰り返さず、既存方針に沿って完成まで進める。
- 検証条件は成績を良く見せるために勝手に緩めない。
- 不合格戦略を正式Releaseしない。
- GitHub Actions失敗時はログを確認し、原因を直して再実行する。
- 長時間処理でも重要な節目ごとにcommitし、次回再開可能な状態を保つ。
- ユーザーには長時間無言にせず、短い進捗を返す。

## 上限・停止・タイムアウト対策（最重要）

Workの使用上限、時間上限、コンテキスト上限、ツール制限などで完成まで継続できなくなりそうな場合は、黙って終了しない。

終了前に必ず:
1. 有効な変更をGitHubへcommit/push。
2. `PROJECT_STATUS.md` とこのファイルへ現在位置を保存。
3. 進行中Run ID、status、失敗ならjob/stepを保存。
4. 次に実行すべき具体的な1手を保存。
5. ユーザーへ通常チャットへ戻るよう案内。

復帰案内:
> Workの上限に近づいたため、続きが消えないようGitHubへ状態を保存しました。通常のチャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて」と送ってください。

## 現在の作業地点

安定公開版: `v0.14.1`
次期候補: `v0.15.0`（未Release）

### 2026 v12

2026年5〜9月の開発結果:
- ROI 117.3%
- 損益 +498,780円
- 2,407購入推奨レース
- プラス月 4/5
- 最悪月ROI 94.7%
- `historicalCriteriaMet=true`

ただし2026は繰り返し開発へ使ったため、この結果単独ではReleaseしない。

### v12 複数年検証結果

公式B/Kファイルからリークなしで2023〜2025を復元し、過去3連単オッズと結合して完走済み。

データ品質:
- 2023 program metric coverage: 97.75%
- 2024: 98.03%
- 2025: 97.68%
- 平均ST coverage: 約99.96%
- 展示タイム coverage: 100%

v12旧年運用成績:
- 2023: ROI 72.0%, 7,381購入, 0/5月プラス
- 2024: ROI 45.5%, 867購入, 0/5月プラス
- 2025: ROI 56.3%, 1,326購入, 0/5月プラス

`releaseCandidate=false`。v12は正式Releaseしない。
2023〜2025年5〜9月は既に結果を見ているため今後は開発データ扱い。

### v13 結果

`validate_multiyear_strategy_v13.py` で、alphaをROIではなくlog-lossだけで校正し、買い条件を2〜4月で固定する方式を試した。

Run: `35823941965`
結果: 2023/2024/2025すべて同じ理由でresearch step failure。
原因: `no v13 ticket configuration met calibration-volume guard`。
つまり確率精度を優先して市場側へ縮めると、minEV >=1.02で十分な購入件数を作れる設定が無かった。
無理にalphaを上げて買わせる方向には進めない。

### v14（現在進行中）

新規:
- `scripts/build_market_signal_cache.py`
- `.github/workflows/build-market-signal-cache.yml`
- `scripts/search_multiyear_strategy_v14.py`

v14方針:
- モデル確率 / 市場確率のlog-ratioを固定binへ分類。
- 過去の実績から各binの市場比勝率multiplierを推定。
- multiplierは固定prior=100で市場(1.0)へ縮約、0.50〜1.75にcap。
- bin境界/prior/capは結果を見て探索しない。
- 2023年5〜9月だけでticket条件を設計。
- ticket条件を凍結し、2024/2025年5〜9月へそのまま適用。
- 2024/25の結果を見てticket条件を変更しない。

重い公式B/K復元を毎回繰り返さないため、3年分の120通りAI確率・市場確率・オッズ・結果をNPZへキャッシュ中。

現行キャッシュRun:
- **35824767175**
- workflow: `Build archived market signal caches`
- 2023/2024/2025を並列生成中。
- 成功したらArtifactのrun-id 35824767175をv14研究Workflowから再利用する。

### 最終ホールドアウト（絶対に先に開かない）

**2025年10月1日〜12月31日をv14以降の最終ホールドアウトとして予約。**

重要ルール:
- 今までの予想戦略検証は基本的に9月末までで、2025年10〜12月の戦略成績はまだ見ていない。
- v14のアルゴリズム・bin・prior・cap・ticket条件を完全固定するまで2025年10〜12月を評価しない。
- v14が2023設計＋2024/2025年5〜9月の固定条件評価で十分安定した場合のみ、一度だけ2025年10〜12月を開く。
- 2025年10〜12月を見た後に条件を変更したら、その期間は以後holdoutとは呼ばない。
- 最終Release判断ではこのルールを必ず保持する。

### Android側

Value Strategy統合済み:
- 公式3連単120通り取得
- Value StrategyでBUY/SKIP確定
- SKIP時に旧4点へ自動フォールバックしない
- 個別/一括/履歴が同じ確定買い目を使用
- 購入時に再予想しない
- SKIP履歴は仮想投資0円
- manual overrideを分離
- BUY/SKIP、120通り、最大10点、1200円配分、Python parity、判定凍結/復元Unit testあり

最新Android Build確認済み:
- Run `35817872634`: SUCCESS
- Unit tests / lint / Debug APKすべてSUCCESS

現Android `ValueStrategyModel` は静的alpha/config前提。最終戦略がv14方式になった場合は empirical bin multiplier を実装し、Python/Kotlin parity testを追加する必要がある。

### Release安全ロック

現在 `promote-value-model.yml` / `export_value_strategy_model.py` は旧v12独立検証ゲートでロックされており、assetは生成不能。これは意図どおり。

最終Release工程:
1. 最終戦略を固定。
2. 予約済み2025年10〜12月holdoutを一度だけ評価。
3. 合格なら2026整合性確認。
4. Python/Kotlin parity。
5. Releaseゲートを最終戦略用へ更新。
6. model asset生成。
7. Android Unit test/lint/Build成功。
8. 月別損益UI/説明を最終戦略へ更新。
9. versionCode 18 / versionName 0.15.0。
10. signed Release APK・署名検証・GitHub Release公開。
11. `PROJECT_STATUS.md` とこのファイルを完成状態へ更新。

現在:
- versionCode 17
- versionName 0.14.1

## 次の具体的な1手

1. **Run 35824767175** の3年signal cache完了を確認。
2. Artifactが揃ったらv14研究Workflowを作成し、そのrun-idからcacheを取得。
3. v14で2023 design / 2024・2025 May-Sep frozen-config評価。
4. 結果が不安定なら2025 Oct-Decは開かず、開発期間だけでv15以降へ改善。
5. 結果が十分安定した時だけアルゴリズムを完全固定して2025 Oct-Dec holdoutを一度だけ評価。
6. Release条件を満たすまではv0.15.0を公開しない。

## 通常チャット復帰文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
