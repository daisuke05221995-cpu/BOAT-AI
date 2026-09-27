# BOAT AI v0.16.8 Purchase Safety Handoff

Date: 2026-09-27

## Release

- Version: v0.16.8
- versionCode: 43
- Release target: `e58fd4393d9928949484b75092ca5690ece58de4`
- Signed Release Run: `36317879182` SUCCESS
- Debug validation Run: `36317879225` SUCCESS
- GitHub Release ID: `397634824`
- APK: `BOAT-AI-v0.16.8.apk`
- APK SHA-256: `c575743718eceb3f38539e1a69db6103d50507855585b1a6935a445f917a4ea3`

## What changed

### Pending purchase card

The pending-purchase card now separates the full candidate set from the races currently selected for actual purchase.

It displays:

- candidate race count / ticket count / total stake
- selected race count / selected ticket count / selected total stake
- a full-width official-purchase button containing the selected race count and selected stake
- Select all
- Clear all

The official-purchase button is disabled when zero races are selected.

### Official handoff safety

`OfficialBetLauncher` refuses to open the official purchase surface when no race is selected.

Only selected races are copied to the clipboard. Unit tests cover selected-only clipboard output and the zero-selection case.

### Prevent pending-session overwrite

`BoatViewModel.savePendingPurchase()` now checks for an existing unresolved pending-purchase session before creating another one.

If a pending session exists, BOAT AI keeps the existing session and asks the user to either confirm it as an actual purchase or discard it before making a new purchase session.

This prevents a second purchase action from silently replacing an unresolved official-purchase handoff.

### Pending card on Prediction screen

The Prediction screen now also shows `PendingPurchaseCard` whenever a pending session exists.

After returning from the official purchase screen, the user can immediately:

- adjust which races were actually purchased
- confirm them as actual purchases
- or discard the pending session

without first navigating to another tab.

## Validation

### Initial selected-total / empty-selection safety

Commit: `1619f2db7f3249d510cb52ac5bb05851567b4ed1`

Run `36317240148` SUCCESS:

- live race API schema verification
- unit tests
- Android lint
- Debug APK build
- artifact upload

### Pending-session overwrite prevention

Source commit: `4ab0e85b4a7ea246e4eb597abf5b64a2ca6fb73a`

Pre-commit validation Run `36317673303` passed patch verification, unit tests, lint and Debug APK build before committing the source changes.

### v0.16.8 release

Release commit: `e58fd4393d9928949484b75092ca5690ece58de4`

Signed Release Run `36317879182` SUCCESS:

- release version validation
- signing-secret validation
- signing-key restore
- release unit tests
- release lint
- signed APK build
- APK signature verification
- GitHub Release publication

Debug validation Run `36317879225` SUCCESS:

- live race API schema verification
- unit tests
- Android lint
- Debug APK build
- artifact upload

## Real-device update rule

Install `BOAT-AI-v0.16.8.apk` over the existing app.

Do not uninstall BOAT AI and do not clear app data before updating. Actual-purchase records and audited prediction records are stored locally.

## What remains

The biggest unresolved product question is still cumulative real-money performance, not purchase-flow mechanics.

Real-device/live evidence is still required to determine:

- whether AI-live BUY recommendations are profitable over a meaningful sample
- cumulative stake / payout / profit / ROI
- hit rate and drawdown
- comparison between AI-live virtual performance and actual user purchases

A real device `BOAT-AI-backup.json` should be evaluated with the frozen evaluator. Do not commit that backup to the public repository because it may contain actual purchase history and learning state.
