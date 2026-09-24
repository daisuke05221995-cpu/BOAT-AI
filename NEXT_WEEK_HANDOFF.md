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

r1/r2/r3は本番不採用。Work側ではr4「2025年中心・選手ID×コース×展示反応」を別系統で研究中。本番アプリ/UI/Releaseへは自動統合しない。

最終2025 Q4 holdoutは候補完全固定まで未開封を維持する。最新の研究Run/進捗は `WORK_HANDOFF.md` と `data/v016_r4_*` を確認する。

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main、進行中Actionsを確認する。
