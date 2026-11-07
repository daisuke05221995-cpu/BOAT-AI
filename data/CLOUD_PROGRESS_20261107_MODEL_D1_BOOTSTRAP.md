# BOAT AI 固定Model Aクラウド配置 — 2026-11-07

## 目的

Android v0.18.25に同梱された固定3本のLightGBMテキストモデルを、Cloudflare D1へハッシュ検証付きで安全に保存し、次の実レース・Android確率パリティ試験の準備をする。**モデル保存は本番自動BUY/SKIPの起動を意味しない。**

## 既存資産と固定値

| Stage | バイト数 | SHA-256 | 特徴量 |
| --- | ---: | --- | ---: |
| 0 | 870,836 | `ee67bc585ad4b19904d64ea8c77e25964ed41887b58e94a425bbd10c1d5a1a45` | 545 |
| 1 | 866,899 | `ad8425277311dd7080b0a05f719a322632d5993ab4382cadc721f152ddcfb1e7` | 715 |
| 2 | 847,788 | `23e78898a8229794d5c1b819297d2cb77d23ec07edeb4ab6cb07a7d5758eac8a` | 885 |

固定bundle ID（上記マニフェストのSHA-256）：`c6d44a4bc9e2f27a4066c25ef0d375ec47055c566695ebfc30043c90433a4f2e`。

## 保存・再検証の仕組み

- 追加テーブルはPR #48で導入済み。Cloudflare本番D1のmigration成功を確認済み。
- `Stage frozen Model A assets in D1` はmainブランチの手動workflowのみ。PRや通常Androidビルドでは資産投入しない。
- D1の100KB SQL文上限を守るため、256KiBの物理チャンクを64KiB以下のSQL行にしてappend。`length(base64_data)` を再試行用の条件とし、再実行時に二重連結しない。中断時の部分保存は後続のSHA検証で拒否され、予想に使えない。
- GitHub Actionsだけで元の3モデルSHA・サイズ・LightGBM構造を検証→SQL作成→D1へ保存→D1から再取得→全12チャンクと全3ファイルのSHA・構造を検証する。
- セキュリティ：既存Cloudflare API tokenはSecretsから使用し、モデルデータの一時SQL・D1 readbackはGitHub runnerの一時領域のみ。外部への送信・公開APIの変更・新たな認証情報の設定は行わない。

## 引き続きブロックするもの

- Android固定の選手履歴は2026-09-23まで。別の研究用rolling履歴には2026-11-06までの日付表示があるものの、日別の全国レース欠損照合が未完了で、代用しない。
- Cloudflareで6艇の展示/ST/気象/3連単120オッズを締切前に観測できる、許諾・時刻証跡付きの自動取得元は未確定。Androidの従来の個人利用オッズ取得処理は変更しない。
- D1にモデルが格納されても、実レース入力と日別連続履歴の整合性確認が済むまでは `MODEL_A_HISTORY_STALE`、`UNAVAILABLE` を解除せずBUY/SKIPを作らない。
