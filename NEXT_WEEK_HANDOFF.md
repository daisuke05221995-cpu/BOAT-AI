# BOAT AI 次週引き継ぎチェックポイント

更新日: 2026-09-24

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 復旧公開版: `v0.15.10`
- versionCode: 28 / versionName: 0.15.10
- Release commit: `a6062755ac65a2b4048c6ad3a122ccf30524ddb0`
- Signed Release Run `35884992894`: SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.10`

## 実機状態

ユーザー実機でv0.15.10復旧モードが正常起動。復旧画面から通常モードへ入った後も、直前まで再現していたクラッシュは現時点で再発していない。

`CrashRecoveryStore` と `RecoveryActivity` は維持し、ユーザーデータを削除しない。アンインストール・アプリストレージ消去は禁止。

クラッシュ原因切り分けのためバックグラウンドService/ReceiverはManifestで一時無効化中。自動予想追跡・Alarm/通知は一度に戻さない。

## Android再実装状況

独立 `SettingsScreen.kt` は復旧安全版へ再追加済み。commit `128df8339ff0a1aebb2124a3767ec7e58698449e`、Build/Unit test/lint Run `35899813231` SUCCESS。

2026-09-24 08:00 JST時点、右上設定ボタンとSettingsScreen接続を段階導入中。損益内の旧設定折りたたみは専用設定画面へ移す。これがBuild/Unit test/lint成功後にのみ、戻るキー制御へ進む。

次の順番:
1. 右上設定ボタン/SettingsScreen接続を検証
2. Android戻るキーの画面階層制御
3. 完全無音・無振動通知
4. バックグラウンドReceiver/Serviceを例外隔離付きで段階復帰

署名ReleaseはAndroid検証成功時のみ。復旧モードとクラッシュ記録を削除しない。

## 継続機能

- 4タブ `予想 / 購入 / 結果 / 損益`
- 半自動一括公式投票ハンドオフ
- BUY/SKIP履歴と結果settle
- 実購入/AI仮想損益
- GitHub Releases更新

## v0.16研究

CORE r1旧144条件は2024通年で不採用確定。十分な件数の最高ROI 94.081871%。同じ閾値gridを再探索しない。

CORE r2は6モデル全不採用。fundamental-small/mediumは2024 ROI 79.93/80.12%。residual-smallはROI 139.79%だが47購入・3的中、最大1的中除外ROI 82.55%で不採用。placeは購入0。校正監査Run `35876699180` SUCCESS。

`data/v016_r3_protocol.json` を事前登録済み。r3は旧閾値調整ではなく、residual-small / place-smallを各評価四半期より前だけで再学習するwalk-forward仮説。買い条件は1200円、最大3点、minEV 1.10、minP 0.01、最大40倍に固定し、ROIを見て後付け変更しない。

r3 chronology guard Run `35926042062` SUCCESS。次はwalk-forward本計算実装。

年間ゲートはROI>=105%、360購入以上、30的中以上、最大1的中依存<=25%、最大1的中除外ROI>=100%。

**2025-10-01〜2025-12-31 final holdoutは未開封。候補を完全固定するまで開かない。**

## 再開時

`PROJECT_STATUS.md`、`NEXT_WEEK_HANDOFF.md`、`WORK_HANDOFF.md`、最新main commit、進行中Actionsを必ず確認。Androidと研究ファイルを同時に競合編集しない。
