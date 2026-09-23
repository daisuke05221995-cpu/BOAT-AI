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

v0.15.10ではユーザーデータを削除せず、`CrashRecoveryStore` がuncaught exceptionを端末内に保存する。クラッシュ時は次回起動を復旧画面へ戻す。Launcherは`RecoveryActivity`、`MainActivity`は通常モード専用。

原因切り分けのためバックグラウンドService/ReceiverはManifestで一時無効化中。したがって「クラッシュが消えた」だけで根本原因が確定したとは扱わない。自動予想追跡・Alarm/通知を一度に復帰させない。

## Android進行中

独立 `SettingsScreen.kt` は復旧安全版へ再追加済み。commit `128df8339ff0a1aebb2124a3767ec7e58698449e`、Build/Unit test/lint Run `35899813231` SUCCESS。

右上設定ボタンから専用SettingsScreenへ接続し、損益画面内の旧設定折りたたみを外す変更を commit `6b921df387b6e4160dcb0df261c00034c9eae84f` で適用。Build Run `35931513963` は Unit test / lint / Debug APK まで SUCCESS。

Android戻るキーの画面階層制御を commit `35bf1b9057e3f8dfe3ff6848e0e39e0dfef2d46d` で追加済み。設定→元画面、レース詳細→場一覧、場一覧→予想ホーム、購入/結果/損益→予想ホーム、予想ホームでは終了しない。現在この状態をBuild/Unit test/lintで検証する。復旧モードとクラッシュ記録は維持。

以降の順番:
1. 戻るキー制御を検証
2. 完全無音・無振動通知
3. バックグラウンドReceiver/Serviceは最後に、例外隔離を追加して段階復帰

署名ReleaseはAndroid検証成功時のみ。アンインストール・アプリデータ消去は禁止。

## 本番予想ロジック

研究用v0.16は本番未統合。現行安定ロジックを継続。

- CORE r1旧144条件: 2024通年で合格0。十分な件数の最高ROI 94.081871%。再探索しない。
- CORE r2: 6モデル全不採用。fundamental-small/mediumは2024 ROI 79.93/80.12%。residual-smallはROI139.79%だが47購入・3的中、最大1的中除外ROI82.55%で不採用。placeは購入0。
- r2校正監査Run `35876699180`: SUCCESS。residual/placeは市場loglossを僅かに改善したが、固定買い方で収益再現性を満たさない。

**2025-10-01〜2025-12-31 final holdoutは未開封のまま維持する。**

## CORE r3

`data/v016_r3_protocol.json` を事前登録。旧閾値gridの繰り返しではなく、r2で市場logloss改善が確認できた residual-small / place-small を対象に、各評価四半期より前のデータだけで再学習するwalk-forward仮説を検証する。

買い方はr2から固定（1200円、最大3点、minEV1.10、minP0.01、最大40倍）。ROIを見て閾値を後付け調整しない。年次ゲートもROI105%以上・360購入以上・30的中以上・最大1的中依存25%以下・最大1的中除外ROI100%以上を維持。

r3 chronology guard workflow Run `35926042062` SUCCESS。walk-forward本計算 workflow Run `35931987036` を開始済み。2024 Q2-Q4を residual-small / place-small の6並列で評価し、静的r2・市場とのlogloss比較も行う。Q1はpre-2024 feature sidecar不足のため BLOCKED とし、0購入扱いしない。2025 Q4は未開封。

## 再開時に必ず確認

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main commit、進行中Actions。Androidと研究ファイルを同時に競合編集しない。
