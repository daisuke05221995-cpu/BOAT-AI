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
- CORE r4「2025年中心・選手ID×コース×展示反応」も不採用確定。本番へ統合しない。

r3 2024通年 place-small:
- Q1 ROI 136.67%、9購入、1的中、Q1 calibration gate FAIL。
- 年間 ROI 258.54%だが、24購入・3的中のみ。
- 最大1的中依存 59.63%。
- 最大1的中除外ROI 104.38%。
- 年間gate FAIL。
- Decision: `reject_r3_place_small`。

r4 2025年7〜8月開発評価:
- Run `35940833546`: SUCCESS。protocol事前登録→選手履歴→feature cache→3モデル比較→固定2policy検証まで完了。
- core: 7,265購入 / 581的中 / ROI 81.12% / 損益 -1,646,180円 / 最大1的中除外ROI 80.57%。
- reaction: 2,888購入 / 230的中 / ROI 82.05% / 損益 -622,160円 / 最大1的中除外ROI 80.68%。
- 予測期待ROIは約134%だったが、実績ROIとの差が約52〜53ptあり、価値推定が大きく過大評価。
- 履歴追加はlogloss上の増分改善を確認したが、購入収益gateは両policyともFAIL。
- 2025年9月は候補なしで未評価、2025年10〜12月final holdoutは未開封。
- LONGSHOT未着手、本番変更なし。

見かけの高ROI・部分指標だけでは昇格させず、購入件数・的中数・最大1的中依存・校正・ROIをまとめて判断する。

**2025-10-01〜2025-12-31 final holdoutは未開封のまま維持。**

## 次の研究

r1〜r4のminEV・展示z・各閾値を後付けで微調整して救済しない。

次のCORE仮説は「選手履歴の増分を使う、時系列out-of-fold予測に基づく市場差の校正/選別」。

- 最初に新protocolで2025年1〜6月内のforward-only分割manifestを事前登録する。
- 選別器学習に使うModel A予測は、必ず対象レースより前のデータだけで作る。
- r4のtrain feature cacheを再利用する。
- 2025年7〜8月を追加学習へ混ぜない。
- 市場情報は最終選別器でのみ利用する。
- 結果を見て閾値を合わせる探索はしない。
- 候補完全固定前に2025年9月/Q4を開かない。
- COREが基準を満たすまでLONGSHOTへ進めない。
- 採用候補でも通常チャット側の最終確認まで本番統合・Releaseしない。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、`data/v016_r4_report.md`、最新main、進行中Actionsを確認する。
