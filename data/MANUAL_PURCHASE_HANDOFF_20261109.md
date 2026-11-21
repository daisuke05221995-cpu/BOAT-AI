# Manual purchase handoff research — 2026-11-09

Standalone pure Node prototype. Produces sorted buy lines, each stake, total, deterministic handoff ID, and explicit awaiting-manual-purchase status. Reconciles manually transcribed official receipt number, lines and total; mismatches remain unconfirmed. No app integration, network, official app control, purchase, private receipt collection, or production changes.

Run: `node --test scripts/manual_purchase_handoff.test.mjs`.

Android owner next: adapt display and two-device handoff using existing authenticated channel; show pending state and require the user to verify official app receipt. Do not treat a handoff ID as proof of official purchase. This prototype does not provide a cross-device purchase lock; do not mark as complete.
