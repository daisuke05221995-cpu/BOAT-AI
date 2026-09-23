# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-24

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.11` / versionCode 29
- Release commit: `ed72d4bc74e4aa95d722b95b96736dbbcd63861b`
- Signed Release Run: `35934156174`
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.11`
- APK SHA-256: `d3e7f57450c67d80a0bd2ab322fabc886eb365e4899bf00576321062079727ae`

## Android v0.15.11

完了:
- 右上⚙→独立設定画面。
- 損益画面から設定欄を分離。
- Android戻るキーを画面階層に合わせて制御。予想ホームでは誤って終了しない。
- 通知は全て画面表示のみ。音・振動なし。
- Receiver / FGS / Alarm失敗を非致命ログへ隔離。
- Android 15のBOOT_COMPLETEDからdataSync FGSを直接起動しない。
- purchase alert背景処理を再有効化。
- PredictionTracking背景処理を再有効化。
- 通常起動時にPredictionTracking Alarmを安全に再予約。
- `RecoveryActivity` / `CrashRecoveryStore` は維持。
- 最終Debug検証 Run `35933816561`: Unit test / lint / APK build SUCCESS。
- Signed Release Run `35934156174`: Release unit test / lint / signed APK / signature verify / GitHub Release publish SUCCESS。

実機確認時はアンインストールやデータ消去をせず、v0.15.11へ上書き更新する。もしクラッシュした場合は復旧モードへ戻り、保存されたクラッシュ情報を確認する。

## v0.16研究

r1/r2/r3はすべて本番不採用。

r3 place-small 2024通年:
- Q1 ROI 136.67%、9購入、1的中、Q1 calibration FAIL。
- 年間 ROI 258.54%、24購入、3的中。
- 最大1的中依存 59.63%。
- 最大1的中除外ROI 104.38%。
- 年間gate FAIL。
- `reject_r3_place_small`。

最終2025 Q4 holdoutは未開封。

次は同じ閾値調整を繰り返さず、展示タイム差・展示ST・進入変化・1号艇信頼度低下・モーター/選手相対差などを用いた別構造のCORE BUY仮説へ進む。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main、進行中Actionsを確認する。
