# CODEX FOLLOW-UP — 2026-10-11 — Minimal background UI / actionable error UX

## Goal
Review the latest main after the user's operational preference change: background automation should stay invisible during normal operation.

## Required UX
- Do not show background scheduling, retry, exact-alarm, recovery-mode, or internal tracking status in normal settings.
- Keep user-facing settings limited to:
  - purchase recommendation notification ON/OFF
  - AI purchase preparation ON/OFF
  - backup/data controls
- Normal successful data acquisition should show no diagnostic card.
- Show a compact issue card only when data is WAITING/WARNING/ERROR.
- That card must explain:
  - what happened;
  - whether automatic retry will occur;
  - what the user can do now.
- Avoid duplicate error cards for the same acquisition failure.
- Today's publication WAITING remains non-fatal; red error styling is reserved for actual ERROR.
- Do not alter hidden background retry behavior, prediction thresholds, stakes, or formal evaluation rules.

## Review targets
- app/src/main/java/jp/boatai/app/NotificationSettingsCard.kt
- app/src/main/java/jp/boatai/app/SettingsScreen.kt
- app/src/main/java/jp/boatai/app/DataDiagnosticsCard.kt
- app/src/main/java/jp/boatai/app/DataIssuePresenter.kt
- app/src/main/java/jp/boatai/app/MainActivity.kt
- app/src/test/java/jp/boatai/app/DataIssuePresenterTest.kt

## Checks
1. Healthy diagnostics render nothing.
2. WAITING renders retry guidance but not fatal error styling.
3. ERROR tells user to check connectivity and exposes immediate retry.
4. Background logic remains active even though UI details are hidden.
5. No stale "background processing stopped" text remains.
6. Run unit tests, lint, Debug APK build.
7. Write a dated handoff under data/ with findings and Run IDs.
