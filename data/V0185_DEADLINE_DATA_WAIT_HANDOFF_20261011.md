# BOAT AI v0.18.5 — Deadline UI / Program Publication Reliability Handoff

Date: 2026-10-11

## Release

- versionName: 0.18.5
- versionCode: 51
- release target: `d828efb649da2147c206ad43e30cf0afc5adc69a`
- Debug validation Run: `38063285208` SUCCESS
- Signed Release Run: `38063285199` SUCCESS
- GitHub Release ID: `409029816`
- APK: `BOAT-AI-v0.18.5.apk`
- APK SHA-256: `340e08dcf41c18675ea6db69ec248eb3f29ebfebae9ebf4270a5543c1926e18c`

## User-requested UI changes

### Bulk-purchase choice menu removed

The large Prediction-screen card labeled "一括購入の対象" was removed.

- The user no longer has to choose between "購入推奨のみ" and "見送りも含む".
- Venue detail exposes only a compact recommendation-only bulk selection action.
- Purchase tab's bulk action now explicitly selects recommendation-only races.
- Manual individual-race controls remain available.

### Deadline mode is now race-level

"締切順" no longer sorts venue tiles.

It now:
- shows one currently purchasable race per row;
- sorts all venues together by each race's closing time;
- displays closing time, venue, race number, remaining time, and current BUY/SKIP/wait status;
- opens race detail by tapping a row;
- removes already-closed races from the deadline list.

Regression tests:
- individual races across venues sort globally by deadline;
- already-closed races are excluded.

## HTTP 404 / daily program publication fix

The daily source may return HTTP 404 before a requested day's JSON has been published.

v0.18.5 behavior for today's date:
1. Try the dated endpoint.
2. If today's dated endpoint returns 404, try `/api/v1/today.json`.
3. Filter fallback records to the requested JST date so stale previous-day data cannot leak into today.
4. If today's data still is not published, return a WAITING diagnostic instead of a fatal error.

Historical-date HTTP failures are not silently converted to WAITING.

UI behavior while waiting:
- no red fatal "HTTP 404" card;
- date header says "本日データ公開待ち";
- the 24 venue tiles are suppressed, so unpublished data is not misrepresented as "開催なし";
- a waiting card explains that data will be retried;
- the ViewModel retries after 15 minutes while alive.

## Background continuity fix

The always-on prediction tracker now handles an empty/unpublished morning program source:

- daily bootstrap remains 06:25 JST;
- if no races are available, retry after 15 minutes;
- same-day retry continues only before 10:30 JST;
- the next daily bootstrap is always scheduled;
- when races become available, normal per-race near-close scheduling is rebuilt.

This prevents a single morning source-publication delay from turning into a full missing prediction day.

## Tests added

- `PredictionListOrderTest`
- `ProgramDataAvailabilityTest`
- bootstrap retry cutoff coverage in `PredictionTrackingPolicyTest`

CI:
- Run `38063285208`: live API schema, unit tests, lint, Debug APK and artifact upload all SUCCESS.
- Run `38063285199`: release test/lint/build, APK signing verification and GitHub Release publication all SUCCESS.

## Formal live evaluation

No strategy threshold was changed.

The frozen formal target remains:
- 360 fully audited value-v1 BUYs
- prior reviewed baseline: 223
- prior remaining count: 137

The app continues to calculate the remaining count from the durable audited ledger.

## Parallel assignments

Work:
- `data/WORK_ASSIGNMENT_20261011_OPERATION_REVIEW.md`

Codex:
- `data/CODEX_ASSIGNMENT_20261011_UI_BACKGROUND_REVIEW.md`

Work should audit post-patch operational continuity on the next private backup.
Codex should independently review the deadline list / publication-wait / retry code and tests.

## Real-device verification

Install v0.18.5 over v0.18.4 without uninstalling or clearing app data.

Verify:
1. shortly after midnight, unpublished data shows WAITING rather than fatal 404;
2. once data appears, Refresh or the automatic retry populates the day;
3. "開催一覧" remains the venue tile view;
4. "締切順" is a vertical individual-race list globally ordered by deadline;
5. the large bulk-choice menu is gone;
6. background capture continues into the next day's backup.
