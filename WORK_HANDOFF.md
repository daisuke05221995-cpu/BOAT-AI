# BOAT AI Work 引き継ぎ・復帰ルール

更新日: 2026-09-23

Repository: `daisuke05221995-cpu/BOAT-AI`
Branch: `main`
安定公開版: `v0.15.0`

## Work上限・停止時の最重要ルール

Workの使用上限、タイムアウト、コンテキスト不足などで継続できなくなりそうな場合は黙って終了しない。
終了前に必ず有効な変更をcommit/pushし、このファイルへ現在位置・Run ID・次の具体的1手を保存する。
その後ユーザーへ通常チャットへ戻るよう案内する。

復帰案内:
> Workの上限に近づいたためGitHubへ状態を保存しました。通常チャットに戻って「BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて」と送ってください。

## v0.15.0 公開完了

- versionCode: 18
- versionName: 0.15.0
- Release commit: `c17a63ba6f6ec620ffd44fdec82d8559ee50a611`
- Release Run: `35840056796`
- Release: `https://github.com/daisuke05221995-cpu/BOAT-AI/releases/tag/v0.15.0`
- APK: `BOAT-AI-v0.15.0.apk`
- APK SHA-256: `34540587dcb9913369d006a50cea5f89070f67baec1faaad869b36a91d34d7e4`

Release WorkflowでUnit test / lint / signed APK / signature verify / GitHub Release公開まで成功。

## 本番へ入れたもの

- 予想 / 結果 / 損益 3タブ
- 一括 / 個別購入記録
- 購入推奨 / 見送り
- 結果・払戻・仮想損益・実購入損益
- 今日 / 7日 / 今月 / 全期間集計
- 2026年月別 / 年合計バックテスト
- GitHub Releases自動更新
- 既存履歴保持

月別バックテストは研究用v12ではなく、現行本番ロジックの `data/historical_backtest_2026.json` を表示する。
締切時3連単オッズを過去データから再現できないため、その最終オッズ判定は参考バックテストに含まない旨をUIへ表示済み。

## 研究モデルは本番へ入れていない

`app/src/main/assets/value_strategy_model.json` は存在しない。
したがって、複数年で再現性を確認できなかったValue Strategy / race-softmax研究モデルはv0.15.0で有効化されない。

主な不採用結果:
- v12: 2026 ROI117.3%だが、2023 72.0% / 2024 45.5% / 2025 56.3%
- rich race-softmax Run `35839229134`: 2024 ROI90.1%、2025固定ROI59.2%

2025-10-01〜2025-12-31 Q4最終holdoutは未開封。

## 次の具体的1手

完成後の次作業は以下。

1. ユーザー実機でv0.15.0をインストール/更新
2. 予想・結果・損益・月別バックテスト・更新機能を実機確認
3. 不具合があればv0.15.xで修正
4. 予想精度改善はv0.16以降の別フェーズ
5. 新モデル候補を完全固定するまではQ4 holdoutを開かない

## 再開文

`BOAT AIの続き。GitHubのPROJECT_STATUS.md、NEXT_WEEK_HANDOFF.md、WORK_HANDOFF.mdを確認して、進行中Runも確認して続けて。`
