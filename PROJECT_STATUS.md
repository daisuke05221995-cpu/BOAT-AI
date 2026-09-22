# BOAT AI 引継ぎメモ

## 現在の状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- Current version: `0.8.0`
- Android package: `jp.boatai.app`
- Release workflow: `.github/workflows/release.yml`
- Update source: GitHub Releases

## 実装済み

- 予想・結果・損益の3タブ
- 開催場カード、場別・AI期待度別一括購入記録
- 3連単4点予想、購入記録、結果照合、日別仮想収支
- PC版/スマホ版の二系統オッズ取得と60秒自動更新
- 欠落結果の公式結果ページ補完
- 会場×艇番勝率を継続学習する端末内学習プロファイル
- 会場×風速帯×実進入コースの継続学習と予想補正
- 進入変化・強風を含む外れ理由表示
- 過去日の当時予想・的中率・仮想収支
- 署名固定の自動Releaseとアプリ内更新

## 学習仕様

結果取得前（または学習反映前）に予想を保存してから結果を学習する。結果を予想に混ぜない。
端末内のSharedPreferences `boat_ai_learning` に、学習済みレースID、会場×艇番の出走・1着回数、会場×風速帯×実進入コースの出走・1着回数を保存。
風速帯は0〜2m / 3〜4m / 5m以上。同条件4件未満では追加補正を行わない。
`PredictionEngine.installLearningProfile` で次回予想の選手スコアへ補正する。
旧v0.7以前の学習JSONに新フィールドが無くても空Mapとして読み込み互換性を維持する。

## 続きの始め方

新しいチャットで「GitHubの `daisuke05221995-cpu/BOAT-AI` と `PROJECT_STATUS.md` を確認して続けて」と依頼する。
実機不具合は、バージョン番号・場名・レース番号・画面スクリーンショットを添える。

## 今後の候補

- 学習データのエクスポート/インポート
- オッズ取得元ごとの整合性チェックと取得診断画面
- 月別・会場別・AIランク別の収支グラフ
