# BOAT AI 引継ぎメモ

更新日: 2026-09-24

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.12`
- versionCode: 30 / versionName: 0.15.12
- Release target commit: `107764f8df759c2b522ddec582b7d58d4c8120a8`
- Debug validation Run: `35940412039` SUCCESS
- Signed Release Run: `35940412081` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.12`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.12/BOAT-AI-v0.15.12.apk`
- APK SHA-256: `a008e5aac7ae99bafa331693e5ed0dff1111d614f9c5fd630c0debcc86331f61`
- 復旧モード / `CrashRecoveryStore` は維持。ユーザーデータ削除・アンインストールは禁止。

## Android v0.15.12 変更

購入画面でユーザーが購入総額を変更した時の金額配分を修正。

- AI/上流が出した初期推奨金額は、総額を変更していない限りそのまま保持する。
- ユーザーが +100円 / -100円などで総額を変更した時は、差額を本線だけへ加算・減算しない。
- 変更後は選択中の全買い目へ100円単位でできるだけ均等に再配分する。
- 100円単位で割り切れない余りだけ、予想順位の高い買い目から順に100円ずつ配る。
- 4点の例: 1300円=`400/300/300/300`、1400円=`400/400/300/300`、再び1300円=`400/300/300/300`。
- この挙動を `BetStrategyTest` に追加し、増額・減額の往復をテスト済み。
- Debug Run `35940412039`: live API schema / Unit test / lint / Debug APK build / artifact upload 全SUCCESS。
- Release Run `35940412081`: Release unit test / lint / signed APK / APK signature verify / GitHub Release publish 全SUCCESS。

## v0.15.11から継続する安定化

- 独立SettingsScreen追加。
- 右上⚙から専用設定画面へ接続し、損益画面内の旧設定欄を分離。
- Android戻るキー階層制御。設定→元画面、レース詳細→場一覧、場一覧→予想ホーム、購入/結果/損益→予想ホーム。予想ホームでは戻るキーで終了しない。
- 全通知をvisual-only化。新しいchannel IDを使用し、`setSound(null,null)` / `enableVibration(false)` / notification builder `.setSilent(true)` を適用。
- Background hardening。Receiver/ForegroundService/Alarm登録失敗を非致命ログへ隔離。
- Android 15対策としてBOOT_COMPLETEDやExact Alarm許可変更BroadcastからdataSync FGSを直接起動しない。
- purchase alert背景処理、PredictionTracking Service/Receiver/BootReceiverをhardening済み状態で有効化。
- MainActivity通常起動時にPredictionTracking Alarmを安全に再予約。
- `RecoveryActivity` / `CrashRecoveryStore` を維持。

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

Work側でr4「2025年中心・選手ID×コース×展示反応」を研究中。Android本番/UI/Releaseとは分離する。最新状態・Run IDは `WORK_HANDOFF.md` と `data/v016_r4_*` を確認する。本番へ自動昇格しない。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main、進行中Actionsを確認する。
