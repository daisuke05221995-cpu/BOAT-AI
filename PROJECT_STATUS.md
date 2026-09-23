# BOAT AI 引継ぎメモ

更新日: 2026-09-24

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.11`
- versionCode: 29 / versionName: 0.15.11
- Release commit: `ed72d4bc74e4aa95d722b95b96736dbbcd63861b`
- Signed Release Run: `35934156174`
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.11`
- APK SHA-256: `d3e7f57450c67d80a0bd2ab322fabc886eb365e4899bf00576321062079727ae`
- 復旧モード / `CrashRecoveryStore` は維持。ユーザーデータ削除・アンインストールは禁止。

## Android v0.15.11 完了内容

- 独立SettingsScreen追加。
- 右上⚙から専用設定画面へ接続し、損益画面内の旧設定欄を分離。
- Android戻るキー階層制御を追加。設定→元画面、レース詳細→場一覧、場一覧→予想ホーム、購入/結果/損益→予想ホーム。予想ホームでは戻るキーで終了しない。
- 全通知をvisual-only化。新しいchannel IDを使用し、`setSound(null,null)` / `enableVibration(false)` / notification builder `.setSilent(true)` を適用。
- Background hardeningを追加。Receiver/ForegroundService/Alarm登録失敗を非致命ログへ隔離。
- Android 15対策としてBOOT_COMPLETEDやExact Alarm許可変更BroadcastからdataSync FGSを直接起動しない。
- purchase alert背景処理をhardening済み状態で再有効化。
- PredictionTracking Service/Receiver/BootReceiverもhardening済み状態で再有効化。
- MainActivity通常起動時にPredictionTracking Alarmを安全に再予約。
- 最終構成の Build and verify Run `35933816561` は Unit test / lint / Debug APK 全SUCCESS。
- Signed Release workflowで testReleaseUnitTest / lintRelease / assembleRelease / APK署名検証 / GitHub Release公開までSUCCESS。

## 本番予想ロジック

研究用v0.16は本番未統合。現行安定ロジックを継続。

- CORE r1旧144条件: 2024通年で合格0。再探索しない。
- CORE r2: 6モデル全不採用。
- CORE r3 walk-forwardも2024通年で不採用確定。

r3 2024通年 place-small:
- Q1 ROI 136.67%、9購入、1的中、Q1 calibration gate FAIL。
- 年間 ROI 258.54%だが、24購入・3的中のみ。
- 最大1的中依存 59.63%。
- 最大1的中除外ROI 104.38%。
- 年間gate FAIL。
- Decision: `reject_r3_place_small`。

見かけの高ROIでも購入件数・的中数・最大1的中依存・校正条件を満たさないため、本番昇格しない。

**2025-10-01〜2025-12-31 final holdoutは未開封のまま維持。**

## 次の研究

r1/r2/r3の同系統閾値調整は繰り返さない。次のCORE BUY仮説は別構造から設計する。候補は展示タイム差、展示ST、進入変化、1号艇信頼度低下、モーター/選手相対差などを組み合わせた別モデル。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main、進行中Actionsを確認する。
