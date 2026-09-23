# BOAT AI 引継ぎメモ

更新日: 2026-09-24

## 現在の最重要状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 緊急復旧公開版: `v0.15.9`
- Android package: `jp.boatai.app`
- versionCode: `27`
- versionName: `0.15.9`
- Release target commit: `0a704cd541b673821dac2b3d3481145987c334fe`
- Debug validation Run: `35883594459` SUCCESS
- Signed Release Run: `35883594737` SUCCESS
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.9`
- APK: `BOAT-AI-v0.15.9.apk`
- APK SHA-256: `3ee4aa5bd4e06dcf4a4b5f8f5888144561b050c4f480d74f9d91566666cd2c80`
- Direct APK: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/download/v0.15.9/BOAT-AI-v0.15.9.apk`

## v0.15.8 実機クラッシュ回帰

2026-09-24 00:30頃、ユーザー実機でv0.15.8を約5分操作後に突然アプリが終了した。その後は起動しようとしても一瞬で閉じる状態になった。

クラッシュログは未取得のため根本原因は未確定。v0.15.8で変更した範囲は主に以下。

- 独立した右上設定画面
- Compose `BackHandler` による戻るキー制御
- 通知チャンネルIDの全面更新
- 通知Builderの無音・無振動指定強化
- PredictionTrackingの通知チャンネル変更

コード監査では `BoatViewModel.loadDate()` の通信成功後処理や `BoatAiApplication` / AlarmManager登録などに未捕捉例外でプロセス終了し得る箇所も確認しているため、v0.15.8変更だけを原因と断定しない。

## v0.15.9 緊急復旧方針

ユーザーデータ保全を最優先し、v0.15.8で変更したAndroid実行時コードを、実機で動作していたv0.15.7相当へ正確にロールバックした。

ロールバック対象:
- `MainActivity.kt`
- `CompactDashboardScreens.kt`
- `NotificationScheduler.kt`
- `PredictionTrackingScheduler.kt`
- `SettingsScreen.kt` を削除

研究ファイル・v0.16 Work成果・本番予想ロジック・購入履歴等の保存形式は変更していない。

v0.15.9はv0.15.8よりversionCodeを上げているため、**アンインストールせずAPKを上書きインストールする**。アンインストール・アプリストレージ消去は、端末内の購入履歴/予想履歴を失う可能性があるため行わない。

### v0.15.9 検証

Debug Run `35883594459`: SUCCESS
- Live race API schema
- Unit tests
- Android lint
- Debug APK build
- APK artifact upload

Signed Release Run `35883594737`: SUCCESS
- release version確認
- signing secrets確認
- Unit test / lint / signed APK build
- APK署名検証
- GitHub Release公開

## v0.15.7相当へ一時的に戻ったUI仕様

復旧確認までは以下を一時的にv0.15.7仕様へ戻している。

- 設定は損益画面内の折りたたみ
- 端末戻るキーの新制御は未適用
- v0.15.8の新通知チャンネルは未使用

これらはv0.15.9で起動安定を実機確認後、クラッシュ隔離・例外保護を追加した上で再実装する。

## 現行主要機能

- 下部4タブ: `予想 / 購入 / 結果 / 損益`
- 一括購入: BOAT AIで買い目固定 → 公式シンプル投票サイト → BOAT AIへ戻る → 実際に投票できたレースだけ実購入確定
- 完全自動投票は未実装
- 全レース事前予想トラッカーは購入推奨通知ON/OFFと独立して動作
- BUY/SKIPを締切前に保存し、結果確定後settle
- Exact Alarmはユーザー実機で設定済み確認あり

## 本番予想ロジック

研究用v0.16モデルは本番へ未統合。現行安定ロジックを継続使用。

過去不採用:
- v12: 2026年5〜9月 ROI117.3%だが旧年 2023 72.0% / 2024 45.5% / 2025 56.3%
- rich-feature race-softmax: 2024設計 ROI90.1%、2025固定 ROI59.2%
- v0.16 CORE r1 144条件: 2024通年でROI105%以上の通過候補0、十分な件数を持つ最高ROI94.081871%

**2025-10-01〜2025-12-31 Q4 final holdoutは候補完全固定前に開かない。**

Work側は別仮説のv0.16 CORE r2研究を継続。最新詳細は `WORK_HANDOFF.md` を必ず確認する。本番アプリ/UI/Releaseは通常チャット側が担当し、研究結果を自動昇格しない。

## 次の最優先手順

1. ユーザーはv0.15.9 APKを**アンインストールせず上書きインストール**する。
2. 起動できるか確認する。
3. 10〜15分程度、予想/購入/結果/損益を切り替えて安定性を確認する。
4. 起動直後または数分後に再クラッシュする場合、保存データを消さず、クラッシュ保護・端末内クラッシュログ保存を実装した次版へ進む。
5. 安定したら、独立設定ボタン・戻るキー制御・完全無振動通知を一つずつ再導入し、各段階で実機確認する。

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
