# BOAT AI 引継ぎメモ

## 現在の状態

- Repository: `daisuke05221995-cpu/BOAT-AI`
- Branch: `main`
- Current version: `0.7.0`
- Android package: `jp.boatai.app`
- Release workflow: `.github/workflows/release.yml`
- Update source: GitHub Releases

## 実装済み

- 予想・結果・損益の3タブ
- 開催場カード、場別・AI期待度別一括購入記録
- 3連単4点予想、購入記録、結果照合、日別仮想収支
- PC版/スマホ版の二系統オッズ取得と60秒自動更新
- 欠落結果の公式結果ページ補完
- 会場×コース勝率を継続学習する端末内学習プロファイル
- 外れ理由表示、過去日の当時予想・的中率・仮想収支
- 署名固定の自動Releaseとアプリ内更新

## 学習仕様

結果取得前（または学習反映前）に予想を保存してから結果を学習する。結果を予想に混ぜない。
端末内のSharedPreferences `boat_ai_learning` に、学習済みレースIDと会場×コースの出走・1着回数を保存。
`PredictionEngine.installLearningProfile` で次回予想の選手スコアへ補正する。

## 続きの始め方

新しいチャットで「GitHubの `daisuke05221995-cpu/BOAT-AI` と `PROJECT_STATUS.md` を確認して続けて」と依頼する。
実機不具合は、バージョン番号・場名・レース番号・画面スクリーンショットを添える。

## 今後の候補

- 学習データのエクスポート/インポート
- 会場×風速×進入変化まで含む学習特徴量
- オッズ取得元ごとの整合性チェックと取得診断画面
- 月別・会場別・AIランク別の収支グラフ
