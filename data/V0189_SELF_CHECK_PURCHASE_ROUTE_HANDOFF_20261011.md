# BOAT AI v0.18.9 — Silent Self-Check / Official Purchase Routing

Date: 2026-10-11

## Release
- versionName: 0.18.9
- versionCode: 55
- release target: `085c0f113c1e68d5bff0d546bb31851559d08c21`
- Debug validation Run: `38069749817` SUCCESS
- Signed Release Run: `38069749807` SUCCESS
- GitHub Release ID: `409080706`
- APK: `BOAT-AI-v0.18.9.apk`
- APK SHA-256: `60094e0b2dfb321ab8b29ec4fc21dc8c83c4b7f34aeebf95a2f13b0cc9986e45`

## Silent operational self-check

Normal state remains invisible.

The app checks durable/live state when current data/accounting is synchronized and surfaces a card only when an actionable abnormality is detected.

Forward-looking monitoring starts from the first v0.18.9 run so old historical gaps are not suddenly reported as new failures.

Checks:
1. recent hidden background exception (visible for up to 6 hours);
2. a decision-ready race closed 15+ minutes ago after monitoring began but has no pre-close prediction record;
3. a newly monitored prediction remains unsettled into the next day or 120+ minutes after close;
4. a current-version settled value-v1 BUY is missing required live audit evidence.

Guidance:
- current acquisition failure: use the existing data issue card and immediate retry;
- operational issue: immediate retry, then backup/share if repeated;
- audit evidence missing: do not reconstruct history; backup/share for investigation.

Data acquisition errors suppress the operational issue card so one root problem does not render duplicate red cards.

Background acquisition exceptions that were previously swallowed by getOrNull are now persisted through CrashRecoveryStore so the next self-check can report them.

## Official purchase route

Primary route:
- official Simple Betting site: `https://bu.tbbr.jp/`

Fallback order:
1. official smartphone betting site: `https://spweb.brtb.jp/`
2. installed official BOATRACE app
3. manual fallback: copy selected tickets + total + Simple Betting URL to clipboard

Selected tickets are copied before opening any route.

After the primary launch attempt, the pending-purchase card exposes:
- `購入画面が開かない場合：別の公式投票サイト`

The alternate button is hidden until a primary launch attempt, preserving the quiet UI.

External wager submission remains user-confirmed on the official service.

## What is verified vs requires real-device confirmation

Verified in code/CI:
- current official primary/fallback URLs are fixed in OfficialBetLauncher;
- URL/clipboard tests pass;
- Intent fallback logic compiles/lints/builds;
- no selected race means no launch;
- manual fallback preserves ticket details and URL.

Verified from current public official sources:
- BOAT RACE launched the Simple Betting site in July 2026 at `https://bu.tbbr.jp/`;
- the smartphone betting site `https://spweb.brtb.jp/` remains the supported smartphone route after the old WEB betting site closure.

Still requires one real-device/account check:
- install v0.18.9 over existing data;
- when a real pending BUY exists, tap the official purchase button;
- confirm the Simple Betting login/purchase surface opens on the user's Android/browser;
- login if required;
- stop before final wager submission if only testing;
- return to BOAT AI without marking purchase complete unless an actual wager was submitted.

If Simple Betting does not reach a usable purchase surface:
- return to BOAT AI;
- use the alternate official smartphone route button;
- if authentication remains a problem, use BOAT RACE official-site login/SSO manually;
- if no route launches, the clipboard already contains the tickets and official URL.

## Work

The previously requested versioned evidence Work task is complete:
- merge commit `21b0fe25d347feffefbb42b8b9a4cb55dec16171`
- report: `data/V016_VERSIONED_EVIDENCE_REPORT_20261011.md`
- versioned helper and synthetic tests are available.

No additional Work task is required for v0.18.9 implementation.
