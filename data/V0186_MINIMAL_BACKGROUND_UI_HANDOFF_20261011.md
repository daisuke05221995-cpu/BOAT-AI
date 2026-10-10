# BOAT AI v0.18.6 — Minimal Background UI / Actionable Data Errors

Date: 2026-10-11

## Release
- versionName: 0.18.6
- versionCode: 52
- release target: `e3c4db8e1659333b9e2bbf19874b636c0d416d30`
- Debug validation Run: `38064026654` SUCCESS
- Signed Release Run: `38064026632` SUCCESS
- GitHub Release ID: `409036258`
- APK: `BOAT-AI-v0.18.6.apk`
- APK SHA-256: `977d29afad170937da21738ec0c88fc7af76b35e88ab38838794b59d38a24fa5`

## User-facing policy

Background automation is an implementation detail during normal operation.

Normal state:
- no background-tracking status card;
- no exact-alarm status card;
- no recovery-mode card;
- no successful data-diagnostics card;
- prediction tracking, retries, settlement, and audit capture continue silently.

Settings remain focused on user choices:
- purchase recommendation notifications ON/OFF;
- AI purchase preparation ON/OFF;
- backup/data controls.

## Data issue UX

The data diagnostic surface now appears only when at least one source is WAITING, WARNING, or ERROR.

WAITING:
- title: data preparation;
- explains that automatic retry will occur;
- provides "今すぐ再取得";
- does not use fatal error styling.

WARNING:
- explains partial data is unavailable;
- automatic re-check continues;
- provides immediate retry.

ERROR:
- tells the user to check connectivity and retry;
- provides immediate retry;
- uses error styling.

Healthy OK-only diagnostics render nothing.

Duplicate fatal data cards were removed so one acquisition failure produces one actionable surface.

## Background behavior retained

No hidden automation was disabled:
- same-day program publication retry from v0.18.5 remains active;
- near-close prediction capture remains independent of BUY notification setting;
- settlement and audit capture remain active;
- no prediction threshold, stake, or formal-evaluation rule changed.

## Parallel review

Work:
- no new assignment required for this UI-only follow-up;
- existing `data/OPERATION_REVIEW_20261011.md` remains the continuity plan for the next private backup.

Codex follow-up:
- `data/CODEX_FOLLOWUP_20261011_MINIMAL_BACKGROUND_UI.md`
- review healthy-hidden state, WAITING/WARNING/ERROR guidance, lack of stale recovery text, and CI.

## Real-device verification

Install v0.18.6 over the existing app without uninstalling or clearing data.

Expected:
1. normal successful acquisition: no diagnostics card;
2. unpublished daily data: a single non-fatal preparation/retry card;
3. actual fetch error: a single actionable error card with immediate retry;
4. Settings does not expose background scheduling/recovery internals;
5. hidden background prediction capture continues.
