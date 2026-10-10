# BOAT AI v0.18.8 — Quiet UI / Versioned Live Evidence Handoff

Date: 2026-10-11

## Release
- versionName: 0.18.8
- versionCode: 54
- release target: `1aee55cdb35c9138e41971789401b10158e8bd0a`
- Debug validation Run: `38066405772` SUCCESS
- Signed Release Run: `38066405759` SUCCESS
- GitHub Release ID: `409055038`
- APK: `BOAT-AI-v0.18.8.apk`
- APK SHA-256: `c97bf6310fd9cb30d939500410d53d956c658439aaafa79a3df0ae1963714867`

## Quiet normal UI

Normal operation remains intentionally quiet:
- OK-only data diagnostics are hidden.
- Background tracking/retry internals are not shown.
- The app-update card is hidden when the installed version is already current.
- The update card appears only when an update is available, downloading, or update-check failure requires attention.

## Actionable automation requirement

The prediction screen now shows a device-setting card only when:
- there is at least one currently purchasable race, and
- Android exact-alarm access is not available.

The card explains that near-close execution may be delayed and offers a direct "端末設定を開く" action.

When exact-alarm access is healthy or there are no active races, the card renders nothing.

This does not expose general background status or scheduling details.

## Versioned prediction evidence

New/updated PredictionRecord rows now store:
- `sourceAppVersion = BuildConfig.VERSION_NAME`

Serialization:
- nonblank sourceAppVersion is exported in PredictionRecord JSON.
- old/legacy records with no field deserialize to null.
- no old record is guessed to belong to v0.18.8 from the backup envelope version.

This allows future private-backup analysis to separate actual v0.18.8+ evidence from pre-versioned rows.

The frozen v016 live-money evaluator/protocol was not changed.

## Tests

Added/extended tests cover:
- PredictionRecord sourceAppVersion JSON round-trip.
- legacy missing sourceAppVersion stays null.
- exact-alarm issue stays hidden when healthy.
- exact-alarm issue stays hidden with no active races.
- exact-alarm issue becomes actionable when active races exist and access is missing.

CI:
- Debug Run `38066405772`: schema check, unit tests, lint, Debug APK, artifact upload SUCCESS.
- Signed Release Run `38066405759`: tests/lint/release build, signature verification, GitHub Release publication SUCCESS.

## Workflow

Codex is suspended from the normal project workflow.
Normal ChatGPT owns Android implementation/CI/release.
Work is used only for research/evidence tasks.

Current Work assignment:
- `data/WORK_ASSIGNMENT_20261011_VERSIONED_EVIDENCE_REPORT.md`

It prepares a sidecar report that groups the next private backup by sourceAppVersion without changing the frozen evaluator.

## Next real-device step

Install v0.18.8 over the existing app without uninstalling or clearing data.

From that point forward:
- newly evaluated prediction records can be identified as v0.18.8;
- legacy records remain unversioned;
- the app remains quiet when healthy;
- only actual acquisition/configuration issues surface guidance.
