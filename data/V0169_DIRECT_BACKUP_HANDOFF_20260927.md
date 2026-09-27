# BOAT AI v0.16.9 Direct Backup Handoff

Date: 2026-09-27

## Release

- Version: v0.16.9
- versionCode: 44
- Release target: `446d84f1a57c4e9a489492fdf3ed2edbf9dff84b`
- Signed Release Run: `36318605815` SUCCESS
- Debug validation Run: `36318605810` SUCCESS
- Pre-release source validation Run: `36318440533` SUCCESS
- GitHub Release ID: `397639019`
- APK: `BOAT-AI-v0.16.9.apk`
- APK SHA-256: `c701984ab8410e696e3e3d39d34491fb47722fbcc78d9fc66da5822422ab3426`

## What changed

### Direct real-device backup export

The Settings > Data management card now has a primary button that launches Android's document-save UI with the filename `BOAT-AI-backup.json`.

The user can save the evaluator input directly to Downloads, Drive, or another document-provider location without first choosing a share target.

The previous backup-share action remains available separately.

### Backup schema remains unchanged

Direct file export uses the existing `DataBackupManager.backupJson()` payload.

The backup still contains:

- `schemaVersion`
- `appVersion`
- `exportedAt`
- `bets`
- `predictions`
- `learning`
- `historicalBaselineMigratedThrough`

This preserves compatibility with the frozen live-money evaluator and keeps actual-purchase and AI-live accounting separated.

### Privacy cue

The Settings card explicitly warns that the backup contains actual purchase history and should not be uploaded to a public location.

### CI hardening

A validation run failed before source compilation because `gradle wrapper --gradle-version 8.10.2` performed a remote validation request to `services.gradle.org` and that request failed.

The project already provisions Gradle 8.10.2 through `gradle/actions/setup-gradle`, so both Debug and Release workflows now execute the provisioned `gradle` binary directly and no longer generate a Wrapper on each run.

This removes that unnecessary external failure point while keeping the build version fixed at Gradle 8.10.2.

## Validation

### Direct backup source validation

Run `36318440533` SUCCESS:

- live race API schema verification
- unit tests
- Android lint
- Debug APK build
- artifact upload

### v0.16.9 signed Release

Run `36318605815` SUCCESS:

- release version validation
- signing-secret validation
- signing-key restore
- release unit tests
- release lint
- signed Release APK build
- APK signature verification
- GitHub Release publication

### v0.16.9 Debug validation

Run `36318605810` SUCCESS:

- live race API schema verification
- unit tests
- Android lint
- Debug APK build
- artifact upload

## Real-device update rule

Install `BOAT-AI-v0.16.9.apk` over the existing app.

Do not uninstall BOAT AI and do not clear app data before updating. Actual-purchase records, audited prediction records, and learning state are local app data.

## Next real-device step

After overwrite-updating to v0.16.9:

1. Open Settings.
2. Open Data / Backup.
3. Tap `BOAT-AI-backup.json をファイルに保存`.
4. Save the file on the device.
5. Provide that private file for frozen-evaluator analysis; do not commit it to the public repository.

The evaluator can then report cumulative stake, payout, profit, ROI, hit rate, drawdown, audit completeness, and period totals for AI-live and actual purchases separately.

There is still no factual claim that the live strategy is profitable until a real-device backup with enough audited live BUY records is evaluated.
