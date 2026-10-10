# CODEX ASSIGNMENT — 2026-10-10 — Android unattended tracking reliability

## Goal
Review and harden BOAT AI so, after the unavoidable first Android launch/initialization, daily near-close prediction capture keeps working without manually opening the app.

## Current normal-chat changes to review
- Fresh installs default to normal mode unless an actual crash explicitly disabled normal boot.
- Application process start self-heals prediction tracking alarms.
- Tracking receiver reschedules after boot, package replacement, date/time/timezone changes.
- Notification-service live evaluation now persists the full OddsFetchResult.
- Safe AI purchase preparation can auto-create a local pending ticket set, but never submits a wager.
- Notification alert and AI purchase-preparation toggles are separate.
- Formal evaluation progress target is 360 audited BUYs with a remaining-race counter.

## Review tasks
1. Inspect latest main before editing.
2. Verify Android background limits:
   - boot/package replacement
   - exact alarm unavailable fallback
   - app process killed normally
   - force-stop limitation documented, not falsely bypassed
   - battery saver / Doze behavior
3. Add regression tests where practical for:
   - provisional records receiving near-close official-odds audit data
   - formal evaluation progress
   - purchase-assist never overwriting an unresolved pending purchase
   - notification OFF not disabling prediction tracking
4. Avoid any implementation that automatically submits a gambling transaction.
5. Do not alter prediction thresholds or tune ROI based on the already-inspected live sample.
6. Run unit tests, lint, Debug APK build.
7. Update a Codex handoff markdown with findings and exact Run IDs.

## Completion
A reviewed Android reliability patch/tests that can be merged/released by normal chat after CI is green.
