# BOAT AI v0.3.0

BOAT RACEの実データを取得し、予想・購入記録・結果照合・収支をまとめるAndroidアプリです。

## v0.3.0

- アプリ起動時にGitHub Releasesの最新版を自動確認
- 新版がある場合は「更新があります」を表示
- 「更新する」でAPKをアプリ内取得
- Android 8以降で必要な「この提供元のアプリを許可」画面へ誘導
- 許可後、Android標準のインストール確認画面を自動起動
- Androidの仕様上、最後の「インストール」タップだけはユーザー操作が必要
- 更新APKは毎回同じ署名鍵で作るRelease workflowを用意
- Releaseタグと`versionName`が一致しない場合は公開を停止

## 自動更新の公開先

アプリは次の公開GitHubリポジトリのLatest Releaseを確認します。

`daisuke05221995-cpu/BOAT-AI`

このリポジトリはAPK配布用に**Public**である必要があります。ソースコードのビルド元はPrivateでも構いません。

## 署名

GitHub ActionsのReleaseビルドでは以下のSecretsを使用します。

- `BOAT_AI_KEYSTORE_BASE64`: PKCS12/JKS署名鍵をBase64化した値
- `BOAT_AI_SIGNING_PASSWORD`: keystoreとalias `boatai`のパスワード

署名鍵を変えるとAndroidは既存アプリへの上書き更新を拒否するため、初回公開から同じ鍵を保持してください。
