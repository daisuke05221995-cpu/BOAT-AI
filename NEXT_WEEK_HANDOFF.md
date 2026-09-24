# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-24

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: `v0.15.12` / versionCode 30
- Release target commit: `107764f8df759c2b522ddec582b7d58d4c8120a8`
- Debug Run: `35940412039` SUCCESS
- Signed Release Run: `35940412081` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.12`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.12/BOAT-AI-v0.15.12.apk`
- APK SHA-256: `a008e5aac7ae99bafa331693e5ed0dff1111d614f9c5fd630c0debcc86331f61`

## Android v0.15.12

購入金額の手動増減時に差額が本線だけへ寄る挙動を修正。

- 初期AI推奨配分は総額未変更なら保持。
- 総額変更後は全買い目へ100円単位で均等再配分。
- 端数100円のみ予想順位の高い買い目から順に配る。
- 4点: 1300円=`400/300/300/300`、1400円=`400/400/300/300`。
- 減額して戻した場合も同じ均等ルールで再計算する。
- 新しいUnit testで増額/減額を検証済み。
- Build Run `35940412039`: API schema / Unit test / lint / Debug APK / upload SUCCESS。
- Signed Release Run `35940412081`: Release test / lint / signed APK / signature verify / Release publish SUCCESS。

## v0.15.11から継続

- 右上⚙→独立設定画面。
- Android戻るキー階層制御。
- 通知は全て画面表示のみ、音・振動なし。
- Receiver / FGS / Alarm失敗を非致命ログへ隔離。
- Android 15のBOOT_COMPLETEDからdataSync FGSを直接起動しない。
- purchase alert / PredictionTracking背景処理をhardening済み状態で有効化。
- `RecoveryActivity` / `CrashRecoveryStore` を維持。

実機確認時はアンインストールやデータ消去をせず、v0.15.12へ上書き更新する。

## v0.16研究

r1/r2/r3/r4は本番不採用。研究結果はAndroidへ自動統合しない。

r4「2025年中心・選手ID×コース×展示反応」は検証完了:
- Run `35940833546`: SUCCESS。
- protocol事前登録→選手履歴→feature cache→3モデル比較→固定2policy検証まで完了。
- core: 7,265購入 / 581的中 / ROI 81.12% / 損益 -1,646,180円。
- reaction: 2,888購入 / 230的中 / ROI 82.05% / 損益 -622,160円。
- 両policyともROI105%未達かつ最大1的中除外ROI100%未達。
- 予測期待ROI約134%に対して実績は約81〜82%で、価値推定を約52〜53pt過大評価。
- 個人履歴追加は確率品質の改善を確認したが、収益gateはFAIL。
- 2025年9月は候補なしで未評価。
- 2025年10〜12月final holdoutは未開封。
- LONGSHOT未着手、本番変更なし。

次のCORE研究はr1〜r4の閾値再調整ではなく、新仮説「選手履歴増分＋時系列out-of-fold予測による市場差の校正/選別」。

開始時は:
- 2025年1〜6月内のforward-only分割manifestを新protocolで事前登録。
- Model A予測は対象レース以前の学習データだけで生成。
- r4 train feature cache再利用。
- 7〜8月を追加学習へ混ぜない。
- 市場情報は最終選別器でのみ使用。
- 結果を見て閾値を合わせない。
- 候補完全固定まで9月/Q4を開かない。
- CORE合格前にLONGSHOTへ進まない。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、`data/v016_r4_report.md`、最新main、進行中Actionsを確認する。
