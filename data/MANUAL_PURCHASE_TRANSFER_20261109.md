# Two-device manual purchase transfer research (2026-11-09)

Adds a portable JSON envelope containing race, sorted picks, stakes, total and deterministic handoff ID. Receiving device verifies the content and returns an explicit RECEIVED_UNCONFIRMED state; acknowledgement remains NOT_CONFIRMED for purchase. It does not send a network request, operate the official app, or record a real purchase. This is a pure contract ready for the Android owner to integrate with the existing authenticated two-device transport.

Local Node tests: 5/5 passed using the existing manual-purchase contract copied for isolated test execution. GitHub Actions result must be checked separately. Test command: node --test scripts/manual_purchase_transfer.test.mjs

Next: Android owner maps the envelope to the existing authorized transfer channel and displays a receipt review action; do not treat delivery ACK as official purchase acceptance. No changes to app/** or production.
