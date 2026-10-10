# CODEX ASSIGNMENT — 2026-10-11 — Deadline UI and publication-wait reliability review

## Goal
Review the latest main changes for the prediction screen and background program-data acquisition.

## User-requested behavior
- Remove the large "一括購入の対象" choice menu; user only uses recommendation-only bulk selection.
- Deadline mode must show one race per row, globally sorted by deadline from top to bottom.
- Do not show 24 "開催なし" tiles while today's source data is merely unpublished.
- Today's HTTP 404 must be treated as publication WAITING, not a fatal red error.
- Background tracking should retry same-day bootstrap when morning data is still unavailable.

## Review targets
- app/src/main/java/jp/boatai/app/MainActivity.kt
- app/src/main/java/jp/boatai/app/PredictionListOrder.kt
- app/src/main/java/jp/boatai/app/BoatRaceRepository.kt
- app/src/main/java/jp/boatai/app/ProgramDataAvailability.kt
- app/src/main/java/jp/boatai/app/BoatViewModel.kt
- app/src/main/java/jp/boatai/app/PredictionTrackingScheduler.kt
- related unit tests

## Requirements
1. Read latest main before editing.
2. Verify deadline order is by individual open race, not by venue.
3. Verify the today.json fallback cannot leak stale previous-day records.
4. Verify historical 404 remains an actual error.
5. Verify WAITING does not render as fatal UI error.
6. Verify bootstrap retry stops at the defined cutoff and does not interfere with the next daily bootstrap.
7. Add/adjust regression tests where useful.
8. Do not change model thresholds, BUY/SKIP criteria, stakes, or research evaluation rules.
9. Do not implement unattended external wager submission.
10. Run unit tests, lint, Debug APK build and leave exact Run IDs in a dated handoff.

## Output
A Codex handoff under data/ summarizing findings, changes, tests, and any remaining real-device verification.
