# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-24

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開中復旧版: `v0.15.10` / versionCode 28
- 復旧モードと `CrashRecoveryStore` は維持。ユーザーデータ削除・アンインストールは禁止。

## Android段階復帰

完了済み:
- 独立SettingsScreen追加: Run `35899813231` SUCCESS。
- 右上⚙→専用設定画面、損益内設定を分離: Run `35931513963` SUCCESS。
- Android戻るキー階層制御: Run `35932095259` SUCCESS。予想ホームでは戻るキーで終了しない。
- 全通知を新しいvisual-only channel IDへ変更し、channelでsound=null/vibration=false、通知Builderでもsilent指定: Run `35932491385` SUCCESS。

背景クラッシュ対策 commit `285e9303f5e3a0909ef9fb7c60d8726fe135259f`:
- ReceiverからForegroundServiceを起動できない場合を捕捉し、プロセスを落とさず非致命ログへ保存。
- ServiceのstartForeground失敗と処理中例外を捕捉。
- AlarmManager登録失敗を捕捉。
- Android 15対策としてBOOT_COMPLETEDからdataSync FGSを直接起動せず、次回Alarm再予約だけ行う。
- Exact Alarm許可変更BroadcastからもdataSync FGSを直接起動しない。
- `CrashRecoveryStore.recordNonFatal()` を追加。

現在: 上記background hardening状態のUnit test / lint / Debug APK検証を実行する。Manifestの背景Service/Receiverはまだdisabledのまま。検証成功後に段階的に再有効化する。

再有効化順:
1. 購入通知 `AlertEvaluationService` / `BoatNotificationReceiver` / ExactAlarm receiver / boot recovery。
2. Build成功確認。
3. 事前予想 `PredictionTrackingService` / receiver / boot receiver。
4. MainActivity通常起動時に安全なtracking再予約を追加。
5. Build成功後のみversion bump & signed Release。

## v0.16研究

r1/r2は不採用固定。最終2025 Q4 holdoutは未開封。

r3 walk-forward Run `35931987036` SUCCESS。固定買い方の2024 Q2-Q4結果:
- residual-small: ROI 91.62%、541購入、27的中、WF logloss 3.750245 vs static r2 3.749849 → calibration FAIL。
- place-small: ROI 331.67%だが15購入・2的中、WF logloss 3.754098 vs static 3.754326 / market 3.757604 → calibration PASSだが件数不足で収益モデル未合格。

Q1はpre-2024 sidecar不足でBLOCKED。0購入扱いしない。事前登録ルールに従い、place-smallのQ1を評価できるデータを構築可能か確認してからr3年次判定を行う。買い条件は後付け変更しない。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main、進行中Actionsを確認する。
