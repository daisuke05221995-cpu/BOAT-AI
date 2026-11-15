# BOAT AI -> note paid daily article (separate sales system)

Status: implemented article generator and experimental note browser adapter, **not connected to a note account**, no production publication yet.

## Historical reference
data/historical_backtest_2026.json records September 2026 as the highest completed-month ROI in 2026: 86.8% with 1,657 recommended races. This is negative profit, and these simulations did not include the verifiable live final odds gate. The system reads this report for historical reference ONLY; it does not present old winning tickets as today's valid picks or claim the past ROI is achieved today.

## Current live source
The input is the existing forecast Worker GET /v1/forecasts?date=YYYY-MM-DD. A race is included only if status=READY, decision=BUY, six-digit venue/race metadata from the twelve-digit race ID, future deadline at least three minutes away, forecast/odds observed within twenty minutes, documented source and model, no quality flags/results, and complete distinct 100-yen increment trifecta combinations. The top five eligible picks are ranked by actual source confidence (if supplied) then deadline. The script NEVER fabricates confidence.

As at 2026-11-16 the Worker lacks the required production-ready live data source for all races. Most days will have ZERO eligible picks, so the generator will correctly return NO_ELIGIBLE_RACES. This is not a functioning profitable daily business without a compliant source of timely race predictions.

## Article format
Public: date, number of races, earliest deadline, caveats.
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
