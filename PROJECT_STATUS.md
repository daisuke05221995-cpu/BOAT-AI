# BOAT AI 引継ぎメモ

更新日: 2026-09-24

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 復旧公開版: `v0.15.10`
- versionCode: 28 / versionName: 0.15.10
- Release commit: `a6062755ac65a2b4048c6ad3a122ccf30524ddb0`
- Signed Release Run `35884992894`: SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.10`

## 実機復旧状況

ユーザー実機でv0.15.10の「BOAT AI 復旧モード」が正常に開くことを確認。復旧画面から通常モードを起動後、直前まで再現していたクラッシュは現時点で再発していない。

`CrashRecoveryStore` / `RecoveryActivity` は維持し、ユーザーデータを削除しない。バックグラウンドService/Receiverは原因切り分けのためManifestで一時無効化中。アンインストール・アプリストレージ消去は禁止。

## Android進行中

- 独立SettingsScreen追加: commit `128df8339ff0a1aebb2124a3767ec7e58698449e`, Run `35899813231` SUCCESS。
- 右上⚙→専用SettingsScreen、損益内設定を分離: commit `6b921df387b6e4160dcb0df261c00034c9eae84f`, Run `35931513963` SUCCESS（Unit/lint/Debug APK）。
- Android戻るキー階層制御: commit `35bf1b9057e3f8dfe3ff6848e0e39e0dfef2d46d`, Run `35932095259` SUCCESS（Unit/lint/Debug APK）。設定→元画面、レース詳細→場一覧、場一覧→予想ホーム、購入/結果/損益→予想ホーム、予想ホームでは終了しない。
- 完全無音・無振動通知: commit `d4f4ae7d791a8fe7f00116780ac2e742184a2db9` で全通知チャンネルを新しい visual-only IDへ変更。generic通知にも `.setSilent(true)`、全channelで `setSound(null,null)` / `enableVibration(false)`。現在Build/Unit/lint検証待ち。

次:
1. 通知変更のBuild/Unit/lint成功確認。
2. background Receiver/Serviceへ例外隔離を追加。
3. Android 15 boot時の直接dataSync FGS起動を避け、Alarm再予約中心へ変更。
4. background componentsを段階的に再有効化し、その都度Build検証。
5. すべて成功後のみ次版署名Release。

## 本番予想ロジック

研究用v0.16は本番未統合。現行安定ロジックを継続。

- CORE r1旧144条件: 2024通年で合格0。十分な件数の最高ROI 94.081871%。再探索しない。
- CORE r2: 6モデル全不採用。fundamental-small/mediumは2024 ROI 79.93/80.12%。residual-smallは139.79%だが47購入・3的中、最大1的中除外ROI82.55%。placeは購入0。

**2025-10-01〜2025-12-31 final holdoutは未開封。**

## CORE r3 walk-forward

r3 chronology guard Run `35926042062`: SUCCESS。
walk-forward本計算 Run `35931987036`: SUCCESS。買い方はr2固定（1200円、最大3点、minEV1.10、minP0.01、最大40倍）で後付け調整なし。

2024 Q2-Q4部分結果:
- residual-small: ROI 91.62%、541購入、27的中、最大1的中除外ROI 91.62%。WF logloss 3.750245、static r2 3.749849、market 3.757604。市場には勝つがstatic r2より悪化し、校正gate FAIL。
- place-small: ROI 331.67%だが15購入・2的中 בלבד。WF logloss 3.754098、static r2 3.754326、market 3.757604で校正gate PASS。ただし購入件数不足が極端で収益モデルとしては未合格。

Q1はpre-2024 sidecar不足のためBLOCKED。0購入扱いせずannualPass=false。r3事前登録ルール上はplace-smallの校正改善が残ったため、次は不足sidecarを作れるか検証してQ1を埋める。最終Q4 2025は開けない。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main commit、進行中Actionsを確認。Androidと研究ファイルを競合編集しない。
