# BOAT AI 次回引き継ぎチェックポイント

更新日: 2026-09-27

## 最初に読むもの

1. `CURRENT_STATUS.md`
2. `PROJECT_STATUS.md`
3. 最新Release / 最新main / 最新・進行中Actions
4. 必要に応じて最新のversion-specific handoff

`WORK_HANDOFF.md` は研究履歴を含むため、古い記述が現在状態を上書きしないよう注意する。

## 現在地

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- 公開版: **v0.16.5 / versionCode 40**
- Release target: `a401530f1e697c0ae86adac95dcc5b320cdf4ce1`
- Build Run `36238671361`: SUCCESS
- Signed Release Run `36238671351`: SUCCESS
- Release ID `397209702`
- APK: `BOAT-AI-v0.16.5.apk`

## 製品の最優先目的

BOAT AIは「細かな予想理由を説明するアプリ」ではなく、次の2点を最優先する。

1. AI推奨を購入した場合にお金が増えているか減っているか
2. 今日から全期間までの累計成績がどうなっているか

ユーザー向け画面では、細かなモデル説明より次を優先する。

- BUY / SKIP
- 買い目
- 各購入金額
- 合計購入額
- 累計購入額
- 累計払戻額
- 累計損益
- ROI
- 的中数 / BUY数 / 的中率

## 成績は3系統を絶対に混ぜない

1. **AIライブ仮想成績** — 正式なライブBUYを全部購入した想定
2. **実購入成績** — ユーザーが実際に購入した金額と払戻
3. **回顧・研究成績** — 過去データのbacktest / retrospective診断

特にライブ実績と回顧ROIを混ぜない。

## v0.16.5で完成済みの中核

- Model A production forecast
- 現在の公式3連単120通りオッズを使うライブBUY/SKIP
- 4〜8点 / 1,000〜3,000円 / 100円単位配分
- ライブオッズ取得時刻 / source / 取得件数 / selected-pick odds の永続保存
- 実ライブ成績と回顧成績の分離
- `LiveAuditedPerformance`
- 損益画面の「ライブ監査済みAI購入推奨」
- build / signed release / APK publication

## 次に進める順番

### Phase 1 — v0.16.5実運用の信頼性完成
- 実機へ上書き更新。アンインストール・データ消去は禁止
- 実開催でBUY/SKIPを蓄積
- Resultsとライブ監査済みProfit件数を照合
- 監査不足BUYの原因を画面で診断可能にする
- 未settled記録更新時に初回`createdAt`を維持
- background / restart / update後も記録を失わない

### Phase 2 — 累計損益をアプリの中心にする
- 今日 / 7日 / 30日 / 月 / 年 / 全期間
- 購入額 / 払戻 / 損益 / ROIを大きく表示
- AIライブ仮想成績と実購入成績を簡単に比較
- 詳細分析は必要なときだけ開く

### Phase 3 — 購入操作を簡単にする
- 一括購入候補
- 個別購入
- 金額確認・調整
- 合計予定購入額
- 公式購入画面への導線
- 実購入記録

### Phase 4 — 実ライブデータ蓄積
- 監査済みBUYの累計収支を評価
- お金が増減する原因分析はモデル改善用として裏側で行う

### Phase 5 — Model B / C研究
- Model Aを壊さず別候補として研究
- out-of-sampleと実ライブ運用で評価

### Phase 6 — LONGSHOT
- 通常BUY / LONGSHOT BUY / SKIP
- LONGSHOT単独と全体累計を別々に保存

## 最新研究処理

Scheduled `Refresh 2026 historical backtest` Run `36252954413` は 2026-09-27 時点で **SUCCESS**。

研究結果は本番ライブ実績と混ぜず、モデル改善候補として扱う。

## 再開時の基本ルール

新しいチャットでは、古い会話内容よりGitHubの現在状態を優先する。

ユーザーが「BOAT AI続きから」と言った場合は、まず `CURRENT_STATUS.md`、`PROJECT_STATUS.md`、最新Release、最新Actionsを確認してから作業を続行する。
