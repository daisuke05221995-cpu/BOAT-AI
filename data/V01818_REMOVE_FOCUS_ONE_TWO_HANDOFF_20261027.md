# BOAT AI v0.18.18 — フォーカス予想 / 1→2鉄板廃止

Date: 2026-10-27

## User request

- `フォーカス予想` は不要。
- `1→2鉄板` は不要。
- ユーザーはv0.18.18へのGitHub反映、検証、更新版公開を承認済み。

## Implementation

- Remove the 4/5-focus race detail card and the 1→2 dedicated prediction list mode/purchase entry point.
- Stop generating new automated Focus and 1→2 predictions in the tracking service, and stop the extra one-two odds-refresh loop in the ViewModel.
- Keep normal Model A forecast, 120-way live-odds BUY/SKIP, actual and virtual purchase accounting, results, and profit unchanged.
- Preserve legacy Focus/1→2 history stores and settlement/retry recovery, including old strategy IDs. No uninstall or data reset.

## Verification and release

- Version: versionCode 64, versionName 0.18.18.
- Diff/reference checks locally; Android Gradle is unavailable in this runner.
- GitHub Actions Debug test/lint/build must pass before publishing from `main`.
- Signed Release test/lint/APK/signature verification must pass before announcing publication.
- Verify on device that three prediction list modes remain (`開催一覧` / `締切順` / `推奨数順`), Focus card is gone, BUY/SKIP and background recording still operate, and historical purchases remain intact.
