# Licensed live feed: forward-trial offline evaluator (2026-11-08 JST)

Scope: PR #42 research branch only. This is a **dry-run acceptance metric tool**, not a provider adapter, live source, purchase recommendation or credentialed API client. No network calls.

Files: `scripts/live_feed_trial_metrics.mjs` and `scripts/live_feed_trial_metrics.test.mjs`.
Command: `node --test scripts/live_feed_trial_metrics.test.mjs` (12/12 PASS in local Node runtime, 2026-11-08 JST).
CLI (once a licensed trial exists): `node scripts/live_feed_trial_metrics.mjs authorized-trials.json`.

Input: `{"trials":[{"id":"YYYY-MM-DD/stadium/race","deadline_ms":1000000,"attempts":[]}]}`. Every trial is pre-registered. An attempt has `stage` T8/T5, `request_ms`, `received_ms`, `complete`, `permission_verified`, `race_identity_verified`, `preview_6_st_weather_complete`, `odds_120_positive_complete`, and `preview_observed_ms`, `weather_observed_ms`, `odds_observed_ms`. All timestamps are epoch milliseconds; the example deadline is illustrative only, not a real race.

Acceptance requires permission evidence **externally verified**, matching race, complete preview and all 120 positive odds, three independent source observation timestamps within 120 seconds of receipt, and receipt before deadline. This tool checks boolean evidence *as supplied*, not the truth of those claims. The provenance and source timestamp authenticity still need independent review. No T5 if T8 already complete. Missing attempts remain in registered denominator. No sample => rate `null`, not 0% or 100%. `unavailable` is not `SKIP` and no BUY/SKIP is inferred.

Limitations: no provider authorized yet; 0 live requests and 0 live measured successes. No p50/p95 here, because synthetic timings must never be presented as live latency. Future licensed trial must preserve raw request/receipt and provider source-time evidence with separate audit storage, protect secrets, and verify the contract before any forecast integration. This tool is research-only and intentionally has no cloud/Android wiring.

Checkpoint: main checked through `7d55ae7`; PR #42 head before change `167587b`; latest nearby merged PR #53 added read-only cloud collection audits. No production file edited. Next: obtain explicit provider license and independent observation-time semantics, then pre-register races and evaluate genuine trial logs without post-hoc selection.
