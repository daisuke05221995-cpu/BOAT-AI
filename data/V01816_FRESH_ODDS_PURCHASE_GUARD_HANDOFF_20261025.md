# BOAT AI v0.18.16 — 保存済みBUYの安全な再確認

Date: 2026-10-25

## 変更理由

v0.18.15の同日2回目以降の高速起動では、端末に保存したBUY/SKIPと選択オッズをネットワーク取得より先に復元する。これは表示速度を改善するが、投票画面へ進むために使う判定が再起動前の倍率である可能性があった。

## 実装

- `AverageRoiReferenceStrategy.restore()` で復元した判定を**再評価待ち**として扱う。保存済み選択は引き続き画面の即時表示に使用できる。
- `PredictionEngine.hasAverageRoiSelection()` は今回のプロセスでライブオッズを評価済みの判定だけにtrueを返す。
- 購入可能レースで保存済み判定のみの場合はBUY扱いにせず、再取得待ちの文言を出す。
- 一括/個別購入準備 `purchasePicksFor()`、予想画面からの `preparePredictionsPurchase()` を再評価待ち中はブロックする。
- 公式オッズ、または既存の有効な120通りfallbackが取得できて現行の購入ポリシーを再評価した後にブロックを解除する。新しい評価はBUYとは限らずSKIPも正常。
- オッズ再取得に失敗した場合はブロックを残す。実購入の登録やアプリ内履歴は削除しない。

## リスク境界

- Model Aの着順予測、合成オッズ3.00倍ゲート、AI期待値閾値、配分の数値は一切変更しない。
- 凍結済み343件の評価・旧360件ゲート・履歴の計算に変更を加えない。
- 自動投票・外部投票送信機能は加えない。最終購入は本人操作。
- 旧版の判定はそもそも現行版の高速表示に復元しない。v0.18.16で新規保存される判定も再起動後は再評価待ちに戻る。

## 検証

- 回帰テスト: 保存済みBUYを表示できても購入可能判定には使用しない、ライブ再評価後に最新のBUY/SKIPへ置換、別版の保存判定を現在版に読み込まない。
- 修正コミット: `d6c96d3636b6e927bc0d2df432354fb81f938dd2`、テスト修正 `1cf59249065bcb734021b67a10c797530dad24d4`。
- Debug validation Run: [`40203167129`](https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/40203167129) **SUCCESS**（API schema、unit、lint、Debug APK、artifactアップロードすべて成功）。初回テストの誤ったBUY固定期待を修正したRunであり、初回Run `40202910316` の失敗を隠さない。
- Release commit: `b4a17be69191ec324a7f8b33bb15315ba5ffbe3f`。
- Debug Run [`40203588010`](https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/40203588010): **SUCCESS**。
- Signed Release Run [`40203588039`](https://github.com/daisuke05221995-cpu/BOAT-AI/actions/runs/40203588039): **SUCCESS**。Release用unit/lint/署名APK/署名検証/公開がすべて成功。
- GitHub Release: [`v0.18.16`](https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.18.16) / Release ID `423463887`。
- APK `BOAT-AI-v0.18.16.apk`: `13,760,958` bytes。SHA-256 `238f589f9c4ff53f0e51f0fdcb3d1070f7b9f04239f98fef1eb1519513fbb77c`。

## 実機確認

1. 旧アプリをアンインストール・データ削除せずv0.18.16を**上書き**導入。
2. 同日2回目の起動で一覧が早く表示されることを確認。
3. 保存済みBUYがある購入可能なレースを開き、再取得前は購入準備できないことを確認。
4. 最新オッズの再判定終了後、BUYなら買い目/金額を確認して購入準備可能、SKIPなら購入推奨なしとなることを確認。
5. オッズ通信エラー時は過去BUYのまま購入準備できないことを確認。
6. 実機から次の私有バックアップをエクスポートし、`sourceAppVersion=0.18.16` をv0.18.15以前と区別して前向き評価。

## 関連計画

`data/REAL_OPERATION_PLAN_20261025.md`。Workへの指示は現時点でなし。新規実機バックアップ解析が必要になれば具体的な研究指示を別途用意する。
