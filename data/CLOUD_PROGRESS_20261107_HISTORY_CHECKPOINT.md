# BOAT AI クラウド履歴保存 再開チェックポイント — 2026-11-07 JST

## 開始時点

- main: `c489d8a092c6d866b89f3d25460bd394c65e3264` (PR #44 merged)。Android 0.18.25のまま。
- main `42260490428` Cloud contract、`42260490413` Cloudflare deploy、`42260490473` Android buildはすべてSUCCESS。
- Work PR #42はopen。利用許諾・T-8展示/120オッズのソースは未確定。本PRでWorkのファイルを変更しない。
- Model A固定実履歴の最終日: **2026-09-23**。以降の生結果を検証なしに埋めない。

## 追加実装

1. `model-a-history-codec.mjs`: Android `ModelAHistoryStateCodec.kt` と同じBAH1の書き出し。固定実アセット**4,222,646バイトの完全一致**・SHA-256一致。日付/統計/出走数/着順フラグの矛盾を拒否。
2. `migrations/0004_model_a_history_generations.sql`: immutable世代、最大512KiB原バイトのbase64チャンク、CAS用のactiveポインタを追加。既存レース・結果・Android購入記録を変更しない。
3. `model-a-history-store.mjs`: `sealAndroidHistoryBase`（固定アセットSHA検証）、`sealReconciledHistoryDay`、`stageHistoryCheckpoint`（全件1バッチ）、`loadVerifiedHistoryCheckpoint`（チャンク・全体SHA・内部状態照合）、`activateVerifiedHistoryCheckpoint`（直前世代との連続性とCAS）を追加。
4. 故障テスト: チャンク破損・重複ステージング失敗・日付飛び/再適用を拒否し、直前の有効履歴が残ることを実SQLiteでテスト。4.22MBの実履歴のD1チャンク再構築もバイト一致。
5. 展開は**保存契約のみ**。本番Cronからこれらの関数を呼ばず、2026-09-23履歴で11月予想を作らない。

## 制約・未完了

- 実際の全国の全開催・6艇結果・当時の選手/展示/STなどの前日履歴を供給する信頼可能なデータパイプラインがない。日別照合は「提供された最終マニフェストに対する完全性」を判定するだけで、情報源自体の全国網羅性を保証しない。
- D1無料版の上限: 最大データベース500MB、行/文字列最大2,000,000バイト、1Worker実行50クエリ。512KiBチャンクで1行サイズを避けるが、**世代の毎日永続保持**では容量上限に到達する。実運用の履歴世代アーカイブ・保持方針が必要。無断で旧世代を削除しない。
- 本番Workerのモデルアセット（3本約2.59MB）配置、history generation read、実レースパリティ、BUY/SKIP連携はまだ行わない。
- ST/気象不足でも展示完備として通る既存の取得ゲートは別修正が必要。Work調査の知見を製品側で実装する。

## 次にすること

1. 9/24〜前日までの**許諾・出典時刻付き**履歴取得元を検証。選手ID・6艇着順・開催母数・事前展示/STの完全性の証拠を取る。欠損日があれば日別確定を止める。
2. 既存の正規化入力契約に沿った履歴取得アダプターを準備し、検証失敗・リトライ・日付境界をテスト。ソースが未確定なら人工fixtureの契約テストに限定。
3. 監査済みの実日別結果から `reconcileModelAHistoryDay` → `sealReconciledHistoryDay` → stage → validate → activate の順に、元状態を保持したまま接続する。
4. Workerへの固定モデルのハッシュ付き配置、実レース120確率のAndroid/Python比較。許諾済みライブ展示・オッズが揃うまでBUY/SKIPは無効。

**本工程のテスト成功は実データ取得成功・運用ROI・実購入可能性の証拠ではない。**
