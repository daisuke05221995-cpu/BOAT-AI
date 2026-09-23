# BOAT AI 引継ぎメモ

更新日: 2026-09-24

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開中復旧版: `v0.15.10` / versionCode 28
- Release commit: `a6062755ac65a2b4048c6ad3a122ccf30524ddb0`
- Signed Release Run `35884992894`: SUCCESS
- 復旧モード / `CrashRecoveryStore` は今後の版でも維持する。
- ユーザーデータ削除・アンインストールは禁止。

## Android段階復帰

完了済み:
- 独立SettingsScreen: Run `35899813231` SUCCESS。
- 右上⚙→専用設定画面、損益内設定を分離: Run `35931513963` SUCCESS。
- Android戻るキー階層制御: Run `35932095259` SUCCESS。予想ホームでは戻るキーで終了しない。
- 全通知visual-only化: Run `35932491385` SUCCESS。新しいchannel ID、sound=null、vibration=false、通知Builder silent。
- Background hardening: commit `285e9303f5e3a0909ef9fb7c60d8726fe135259f`。Receiver/FGS/Alarmの例外を非致命ログへ隔離。BOOT_COMPLETEDからdataSync FGSを直接起動しない。Run `35932850869` はUnit/lint/Debug APKまで成功確認済み。

段階再有効化:
- purchase alert側 `AlertEvaluationService` / `BoatNotificationReceiver` / `ExactAlarmPermissionReceiver` / `BoatAlertBootRecoveryReceiver` を commit `8cc93456935b69beff81b544f247102bb669d119` で再有効化。
- PredictionTracking側はまだManifest disabledのまま。
- 現在 purchase alert再有効化後のBuild/Unit/lint/Debug APK検証を行う。

次:
1. purchase alert再有効化後のBuild成功確認。
2. PredictionTracking Service/Receiverをhardening済みコードで再有効化。
3. MainActivity通常モード起動時にtracking Alarmを安全に再予約。
4. 再度Build成功確認。
5. version bumpしてsigned Release。実機ではRecoveryActivityを経由するため、再クラッシュ時はログを残してsafe modeへ戻る。

## 本番予想ロジック

研究用v0.16は本番未統合。現行安定ロジックを継続。

- CORE r1旧144条件: 2024通年で合格0。十分な件数の最高ROI 94.081871%。再探索しない。
- CORE r2: 6モデル全不採用。fundamental-small/mediumは2024 ROI 79.93/80.12%。residual-smallは139.79%だが47購入・3的中、最大1的中除外ROI82.55%。placeは購入0。

**2025-10-01〜2025-12-31 final holdoutは未開封。**

## CORE r3 walk-forward

Guard Run `35926042062`: SUCCESS。
本計算 Run `35931987036`: SUCCESS。買い方はr2固定（1200円、最大3点、minEV1.10、minP0.01、最大40倍）、後付け調整なし。

2024 Q2-Q4:
- residual-small: ROI 91.62%、541購入、27的中。WF logloss 3.750245 vs static r2 3.749849 → calibration FAIL。
- place-small: ROI 331.67%だが15購入・2的中。WF logloss 3.754098 vs static 3.754326 / market 3.757604 → calibration PASS。ただし件数不足で収益モデル未合格。

Q1はpre-2024 sidecar不足でBLOCKED。0購入扱いしない。事前登録ルールに従い、place-smallのQ1用2023 Q4 sidecarを作成可能か検証し、年次判定へ進む。最終2025 Q4は開けない。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main、進行中Actionsを確認する。
