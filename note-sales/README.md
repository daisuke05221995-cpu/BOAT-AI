## Current sales design: previous-night forecast (2026-11-16)

The user has selected **tomorrow's races forecast on the previous evening**, without same-day wind, wave, exhibition or live odds. The new opt-in script is note-sales/day_ahead.py and the new scheduler is .github/workflows/note-sales-day-ahead.yml (JST 23:10 and 23:40). It reuses historic lane/racer/motor scoring but operates without preview inputs; its selection index is **not a win probability**, and the previous 34.0% historical simulation must not be represented as its live accuracy. The legacy daytime-scheduled workflow has been converted to manual-only, to avoid accidental same-day sales.

Before enabling: supply a **commercially licensed tomorrow-program JSON endpoint**, set BOAT_AI_DAY_AHEAD_PROGRAM_URL, BOAT_AI_DAY_AHEAD_SOURCE_ID, BOAT_AI_COMMERCIAL_SOURCE_APPROVED=true and NOTE_DAY_AHEAD_ENABLED=true. Article generation uses a complete future six-boat program only and does not publish without a separately verified note account. See DAY_AHEAD_ja.md.

### Note about older instructions below
Earlier references to BOAT_AI_FORECAST_URL, NOTE_SALES_ENABLED, and T-8 live odds are for the **legacy same-day manual workflow**, not the nightly sale. For nightly sale use the settings in DAY_AHEAD_ja.md and the current preflight.py.

# BOAT AI -> note paid daily article (separate sales system)

Status: implemented article generator and experimental note browser adapter, **not connected to a note account**, no production publication yet.

## Historical reference
The sales copy emphasizes **historical race hit rate** rather than stake-weighted ROI. In data/historical_backtest_2026.json, the top completed month by race hit rate is May 2026: 559 wins from 1,644 BUY race recommendations (34.0% rounded). This old 4-pick historical simulation returned 79.7% ROI with its recorded staking (negative profit). September 2026 had the highest ROI (86.8%) but NOT the highest hit rate. The old dataset did not verify the live pre-close odds gate. Never imply the 34.0% is the current live sales policy's measured hit rate or claim positive returns by changing bet sizes.

## Current live source
The input is the existing forecast Worker GET /v1/forecasts?date=YYYY-MM-DD. A race is included only if status=READY, decision=BUY, six-digit venue/race metadata from the twelve-digit race ID, future deadline at least three minutes away, forecast/odds observed within twenty minutes, documented source and model, no quality flags/results, and complete distinct 100-yen increment trifecta combinations. The top five eligible picks are ranked by actual source confidence (if supplied) then deadline. The script NEVER fabricates confidence.

As at 2026-11-16 the Worker lacks the required production-ready live data source for all races. Most days will have ZERO eligible picks, so the generator will correctly return NO_ELIGIBLE_RACES. This is not a functioning profitable daily business without a compliant source of timely race predictions.

## Article format
Public: date, number of races, earliest deadline, **prominent explicitly labeled historical hit rate, actual hit/BUY race counts and historical month**, caveats. Historical labels distinguish simulations from live paid forecasts. ROI remains available as metadata, but it is not the primary sales headline.
Paid: race labels, combination/stake, odds provenance, timestamp.
Article 100 yen; no recommended races => do not sell.
No unprotected paid text is committed or saved to GitHub Actions artifacts or printed to logs.

## Manual local test
At the repository root:
    python -m unittest discover -s note-sales -p 'test_*.py' -v
    BOAT_AI_FORECAST_URL='https://YOUR-WORKER.workers.dev/v1/forecasts' python note-sales/pipeline.py --output /tmp/article.json

## Automatic running
GitHub Actions workflow: .github/workflows/note-sales-daily.yml
Configured by GitHub repository Variables:
- NOTE_SALES_ENABLED=true: activate scheduled generator (default disabled)
- BOAT_AI_FORECAST_URL: your trusted HTTPS forecast Worker endpoint, ending in /v1/forecasts
- NOTE_AUTO_PUBLISH_ENABLED=true: enable experimental browser publishing (default disabled)
- NOTE_BROWSER_UI_VERIFIED=true: ONLY after live account end-to-end UI checks

GitHub encrypted Actions Secret:
- NOTE_SESSION_STATE_B64: base64-encoded Playwright storage-state JSON for the owner's authenticated note account. Treat this as a login credential; do not share in chat or commit. Sessions can expire.

The regular-user note official API is NOT available (as of 2026-11); note API currently supports eligible note pro service integrations. Therefore the publishing adapter uses the public browser UI, WITHOUT reverse-engineering private APIs or bypassing authentication challenges.

The browser automation uses documented paid-area selection controls and refuses to publish if the 100 yen setting and paywall placement cannot be verified. It is a prototype: actual selectors and paywall position have not been tested on the user's authenticated account. Setting NOTE_BROWSER_UI_VERIFIED without a successful draft/live test is unsafe and risks unintended publication. After publication, only date/URL/content SHA are saved in the public ledger for retry protection. If publishing succeeds but recording the ledger fails, duplicate posts could still occur. Do not turn on unattended production until this is addressed.

Other limitations: the existing cloud source captures near deadline (8/5 minutes before); true early-morning sales need a distinct reliable early forecast feed. Existing Android/Cloudflare code, releases and original BUY/SKIP policies were left untouched. Do not upload private backup records or paid articles into this public repository.

## Publication safety upgrades (2026-11-16)
- A paid daily bundle requires at least **45 minutes** from generation to its earliest race deadline; publication itself requires at least **30 minutes** before the earliest deadline. These are intentional **commercial usefulness gates**, NOT new model performance tests. Old T-8/T-5 live feeds will not qualify for a daily roundup.
- The article must be the current JST date, have a recent generation timestamp, 100 yen price, valid SHA-256, and no trifecta combinations exposed in the free text. This is enforced by publish_guard.py and repeated immediately before the final click.
- Before posting, a public GitHub metadata claim (status=PUBLISHING_REQUIRES_MANUAL_RECOVERY_IF_INTERRUPTED) is committed. The claim prevents the workflow from repeating publication after any crash or uncertain outcome. If the publish crashes, inspect note manually, reconcile the claim, and NEVER silently re-publish.
- After posting, the browser must open the URL in a fresh **anonymous** context. It must display the public introduction, **hide paid headings and all combinations**, and show purchase/paywall cues. Only then can the ledger become POSTED_VERIFIED. UI selectors are still unproven on the owner's live account; NOTE_BROWSER_UI_VERIFIED stays false until tested.
- No plaintext note login credentials or cookie values are requested in chat. Account session remains encrypted GitHub Actions Secret. The first note paid publication may require note's identity-registration flow, which cannot be completed autonomously by this headless script.
- See official help: https://www.help-note.com/hc/ja/articles/360008882894 and API announcement https://note.jp/n/n6e16e4dc9e26
