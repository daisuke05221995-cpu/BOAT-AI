# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`
安定公開版: `v0.14.1`
次期候補: `v0.15.0`（未Release）

## 作業開始時に必ず確認

1. `PROJECT_STATUS.md`
2. `NEXT_WEEK_HANDOFF.md`
3. `WORK_HANDOFF.md`
4. 最新commit / GitHub Actions
5. 本ファイル記載の進行中Run

## Work上限・停止時の最重要ルール

Workの使用上限、タイムアウト、コンテキスト不足などで継続できなくなりそうな場合は黙って終了しない。
終了前に必ず有効な変更をcommit/pushし、このファイルへ現在位置・Run ID・次の具体的1手を保存する。
その後ユーザーへ通常チャットへ戻るよう案内する。

復帰案内:
> Workの上限に近づいたためGitHubへ状態を保存しました。通常チャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて」と送ってください。

## Release原則

- 成績を良く見せるために検証基準を緩めない。
- 不合格戦略を正式Releaseしない。
- 2025-10-01..2025-12-31は最終ホールドアウト。候補を完全固定するまで絶対に開かない。
- Q4を一度開いた後は、その結果を見て再調整した戦略に対してQ4をholdoutとは呼ばない。

## 確定済み

### Android側

Value Strategy統合済み:
- 公式3連単120通り取得
- BUY/SKIP確定
- SKIP時に旧4点へ自動fallbackしない
- 個別/一括/履歴が同じ凍結買い目を利用
- purchase時に再予想しない
- SKIP履歴は仮想投資0円
- manual override分離
- 120通り、最大点数、1200円配分、Python parity、判定凍結/復元Unit testあり

Android Buildは継続して成功。Release asset exporter/promote workflowは安全ロック中。
現在 versionCode17 / versionName0.14.1。

### v12まで

2026開発ではv12がROI117.3%だったが、独立旧年評価で失敗:
- 2023 ROI72.0%
- 2024 ROI45.5%
- 2025 ROI56.3%
よってv12は不採用。

公式B/K旧年データ品質:
- program metric coverage 2023 97.75%, 2024 98.03%, 2025 97.68%
- 平均ST 約99.96%
- 展示タイム100%

### 直前情報アーカイブの追加

`BoatraceOpenAPI/previews` が2023-05-01以降利用可能と確認。
以下を歴史検証へ復元済み:
- 展示進入コース
- 展示ST
- 展示タイム
- 風速/風向
- 波高

追加:
- `scripts/historical_preview_overlay.py`
- `scripts/build_preview_enhanced_signal_cache.py`

feature parityのため歴史側learningBonusは0固定。

Preview cache Runs:
- 2023 research/cache: `35830131609` SUCCESS
- 2024/2025 cache: `35830207608` SUCCESS

Artifacts:
- 2023 `preview-enhanced-2023-research`
- 2024 `preview-enhanced-signal-cache-2024`
- 2025 `preview-enhanced-signal-cache-2025`

### 棄却済みPreview戦略

1. 階層市場校正（単年2024校正）
- 2024 May-SepではEV>=1.00候補がほぼ0。

2. pooled階層校正
- 2023 May-Sep + 2024 Feb-Aprの34,927 racesでも2024 May-SepのEV>=1候補0。

3. 2023 Jul-Sep校正→2024移植
- Run `35832317543` SUCCESS
- 2024 May-Sep購入候補0。

4. stable structural cells
- Run `35832714141` SUCCESS
- `data/stable_market_cells_2023_2025.json`
- selectedCellCount=0。

結論: calibrated-EV / fixed-cell路線を閾値緩和で救済しない。

## 現在の本命: 非線形Market Residual

追加:
- `scripts/search_nonlinear_market_residual_2023_2025.py`
- `.github/workflows/nonlinear-market-residual-2023-2025.yml`

方式:
- 2023 May-Sep preview-enhanced combo dataで、正則化の強い `HistGradientBoostingClassifier` を1本だけ学習。
- 入力はpre-raceのみ: market/model probability, odds, model/market rank, ratio, trifecta lane structure。
- venue/month IDは使わない。
- 2024 May-Sepではモデルを再学習せず、marketへ戻すbetaをlog-lossだけで選択。
- ticket gridも小さく固定。
- 完全固定して2025 May-Sepへ評価。
- 2025 Oct-Decはこのスクリプトでは読まない。

進行中Run:
**`35833143407`**
workflow: `BOAT AI nonlinear market residual 2023-2025`
直近状態: cache取得/Q4保護チェック成功、`Train 2023 residual model, design 2024, frozen-evaluate 2025` が実行中。

## このRun完了後の具体的な次の1手

1. Run `35833143407` の結果確認。
2. `data/nonlinear_market_residual_2023_2025.json` を読む。
3. 確認項目:
   - 2024 market log-loss vs adjusted log-loss
   - selected beta
   - basicVolumeFeasible
   - 2024 design total/月別
   - 2025 frozen total/月別
   - largestHitShare
   - `readyForFinalHoldout`
4. `readyForFinalHoldout=false`ならQ4は開かず、モデル本体の次改善へ進む。
5. `readyForFinalHoldout=true`ならモデル・beta・ticket条件をimmutableに固定し、**初めて2025 Oct-Decを一度だけ評価**。
6. Q4も合格した場合のみ:
   - 2026同一定義で整合確認（再調整禁止）
   - Kotlin実装
   - Python/Kotlin parity test
   - promotion/export gate更新
   - model asset生成
   - Android Unit/lint/build/signature
   - versionCode18/versionName0.15.0
   - GitHub Release公開
   - `PROJECT_STATUS.md` / 本ファイル完成更新

## 通常チャット復帰文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
