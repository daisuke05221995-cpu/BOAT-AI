# BOAT AI v0.18.4 — Background Tracking / Notification / Purchase Preparation Handoff

Date: 2026-10-10

## Release
- versionName: 0.18.4
- versionCode: 50
- release target: 611541d8901afd9b9a1f3c6ffcfd341a21b63236
- Debug validation Run: 38062106818 SUCCESS
- Signed Release Run: 38062106863 SUCCESS
- GitHub Release ID: 409020260
- APK: BOAT-AI-v0.18.4.apk
- APK SHA-256: 9d23f52891d602bbfc167cdbbdfb194aefc1abbf2843502364074c166c330e87

## Background tracking
- Fresh installs now default to normal mode; recovery mode is entered only after an actual crash disables normal boot.
- Any normal app process start self-heals the prediction tracking daily bootstrap.
- Tracking reschedules after:
  - BOOT_COMPLETED
  - MY_PACKAGE_REPLACED
  - TIME_SET
  - TIMEZONE_CHANGED
  - DATE_CHANGED
- Notification ON/OFF does not control prediction tracking.
- The notification evaluation path now persists the full OddsFetchResult so fetch time/source/120-way count/pick odds are not discarded.
- Provisional unsettled records remain eligible for near-close replacement; settled records stay immutable.

Android limitation:
- after a brand-new installation Android still requires one user launch before the package can reliably receive background work;
- an explicit Android Force stop also blocks alarms/background starts until the user launches the app again.
Do not claim those OS restrictions are bypassed.

## Notification control
Settings > automatic prediction/notification card now exposes a direct notification Switch.
- ON: BUY alert notifications are allowed (subject to Android notification permission).
- OFF: alerts are disabled, but automatic pre-race prediction recording continues.

Exact-alarm permission remains separate and is recommended for near-close timing.

## AI purchase preparation
A second switch enables automatic purchase preparation.
When enabled:
- a background BUY can automatically create a local pending-purchase draft;
- new BUY races are appended without deleting an unresolved existing draft;
- duplicate race IDs are not duplicated;
- the feature works through the always-on prediction tracker even when BUY notifications are OFF.

It does NOT submit an external wager. Final submission remains user-confirmed on the official service.

Regression tests cover pending-session merge behavior.

## Formal evaluation progress
Frozen target: 360 fully audited value-v1 BUY races.
The Profit screen now uses the all-time audited ledger and displays:
- current audited BUY count
- target 360
- remaining audited BUY count

At the first real evaluation:
- current = 223
- target = 360
- remaining = 137

After updating, the displayed remaining number changes automatically as newly settled audited BUYs accumulate.

## Work / Codex routing
Persistent routing:
- data/DEVELOPMENT_ROUTING.md

Current assignments:
- Work: data/WORK_ASSIGNMENT_20261010_LIVE_EVIDENCE.md
- Codex: data/CODEX_ASSIGNMENT_20261010_BACKGROUND_RELIABILITY.md

Normal chat remains integration/release owner. Work owns research/evidence by default. Codex owns isolated engineering review/tests by default.

## Update rule
Install v0.18.4 over the existing app.
Do not uninstall or clear app data because the live prediction ledger is local data.
