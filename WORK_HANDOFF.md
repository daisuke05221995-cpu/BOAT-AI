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
10. `data/strategy_v13_multiyear.json` が存在すれば確認

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

データ品質（実際の予測レースへ一致した事前指標coverage）:
- 2023: 97.75%
- 2024: 98.03%
- 2025: 97.68%
- 平均ST coverage: 約99.96%
- 展示タイム coverage: 100%

したがって旧年の不振はパーサ不足ではなくv12戦略側の問題と判断。

v12旧年運用成績:
- 2023: ROI 72.0%, 7,381購入, 0/5月プラス
- 2024: ROI 45.5%, 867購入, 0/5月プラス
- 2025: ROI 56.3%, 1,326購入, 0/5月プラス

`releaseCandidate=false`。v12は正式Releaseしない。

重要: 2023〜2025はこの結果を既に確認済みなので、今後は完全未使用holdoutではなく**開発データ**として扱う。

### v13 研究版（現在進行中）

新規:
- `scripts/validate_multiyear_strategy_v13.py`
- `.github/workflows/strategy-v13-research.yml`

v13方針:
- AI/市場ブレンド係数alphaをROIで選ばない。
- alphaは過去月の正解3連単に対するlog-lossだけで校正。
- alpha候補に0.0（市場単独）も含む。
- 買い条件（minEV/minProbability/maxOdds/maxPoints/資金配分）は2〜4月で1回だけ選択。
- 5〜9月は買い条件を固定。
- 毎月変えてよいのはalphaだけで、対象月より前の結果しか使わない。
- 2023〜2025は開発データなので、v13が良くてもそれだけでReleaseロックを解除しない。

現行v13 Run:
- **35823941965**
- head commit: `3c87cc756d1911dec20439af2ed1a924d62fe838`
- 2023/2024/2025を並列実行。
- 最新確認時: 3年とも `Run v13 research` 本計算中。
- 完了後 `data/strategy_v13_multiyear.json` をcommitする。

### Android側

Value Strategy統合済み:
- 公式3連単120通り取得
- Value StrategyでBUY/SKIP確定
- SKIP時に旧4点へ自動フォールバックしない
- 個別/一括/履歴が同じ確定買い目を使用
- 購入時に再予想しない
- SKIP履歴は仮想投資0円
- 手動でSKIPを買う場合のみmanual override
- BUY/SKIP、120通り、最大10点、1200円配分、Python parity、判定凍結/復元Unit testあり

最新Android Build確認済み:
- Run `35817872634`: SUCCESS
- Unit tests / lint / Debug APKすべてSUCCESS

### 月別バックテスト表示

v0.15用UIは新Value Strategy表示へ修正済み。
- 1〜4月は学習・校正期間。
- 5〜9月を運用検証として表示。
- 2026だけではRelease判定しない旨を明示。

ただし最終採用戦略がv13以降へ変わる場合、表示JSON/説明も最終戦略へ合わせて再更新すること。

### 昇格・Release安全ロック

既存 `promote-value-model.yml` / `export_value_strategy_model.py` はv12用独立検証ゲートを要求しているため、現在は昇格不能で正しい。

最終戦略を採用する場合は:
1. 最終戦略を固定。
2. 可能な限り未使用期間または厳格な時系列外検証を実施。
3. Android/Python parityを確認。
4. Releaseゲートを最終戦略用へ更新。
5. asset生成。
6. Android Build/Unit test/lint成功。
7. `versionCode 18`, `versionName 0.15.0`へ変更。
8. signed Release APKと署名検証を通してGitHub Release公開。

現在:
- versionCode 17
- versionName 0.14.1

## 次の具体的な1手

1. **Run 35823941965** を確認。
2. 成功なら `data/strategy_v13_multiyear.json` を確認し、2023/2024/2025各年・合計ROI、プラス月数、最悪月、選ばれたalpha/固定買い条件を確認。
3. v13が改善しない場合、基準を緩めず、AI確率と市場確率の比をbin/isotonic等で校正する次方式へ進む。
4. v13が安定して改善した場合、設定を固定して2026を確認し、Android ValueStrategyModelへ同じ計算を実装してparity testを追加。
5. Release条件を満たすまではv0.15.0を公開しない。

## 通常チャット復帰文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
