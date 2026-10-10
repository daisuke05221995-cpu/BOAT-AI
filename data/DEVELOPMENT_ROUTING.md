# BOAT AI DEVELOPMENT ROUTING

Updated: 2026-10-10

This file defines how future BOAT AI work is split between normal ChatGPT, ChatGPT Work, and Codex-style coding work.

## Source of truth
Always start from:
1. latest main and latest GitHub Release
2. current GitHub Actions
3. CURRENT_STATUS.md
4. latest dated assignment/handoff under data/

Never rely on an older chat summary when repository state is newer.

## Normal ChatGPT — integration owner
Use for:
- deciding product behavior and user-facing scope
- production Android integration
- resolving conflicts between research and implementation
- versionCode/versionName
- CI follow-up and release publication
- CURRENT_STATUS.md updates
- final real-device interpretation

Normal chat must not claim a release is successful until CI/release is verified.

## ChatGPT Work — research and evidence
Use for:
- private backup/result analysis
- prospective evaluation protocol
- model/strategy research
- failure-pattern analysis
- sample-size and concentration analysis
- reports and handoff documents

Default boundary:
- do not edit production app/
- do not bump versionCode/versionName
- do not publish releases
- do not commit private BOAT-AI-backup.json
unless a dated assignment explicitly changes the boundary.

## Codex — isolated engineering implementation/review
Use for:
- Android reliability fixes
- unit/integration tests
- refactors with defined acceptance criteria
- CI/build error diagnosis
- code review of normal-chat patches

Codex should:
- read latest main before editing
- use a dedicated branch/PR when available
- avoid prediction-threshold tuning unless the assignment explicitly allows it
- avoid changing release/version files unless assigned
- leave exact test/run IDs in a handoff file

## Gambling transaction boundary
BOAT AI may:
- calculate BUY/SKIP
- calculate combinations and stake amounts
- automatically save a local pending-purchase draft
- open the official purchase surface
- record purchases after user confirmation

BOAT AI must not implement an unattended external wager submission. Final submission remains user-confirmed on the official service.

## Current parallel assignments
- Work: data/WORK_ASSIGNMENT_20261010_LIVE_EVIDENCE.md
- Codex: data/CODEX_ASSIGNMENT_20261010_BACKGROUND_RELIABILITY.md

## Handoff rule
Every substantial task should end with:
- commit/PR SHA
- GitHub Actions Run IDs
- what changed
- what remains
- any real-device verification required

Normal chat then integrates the result and updates CURRENT_STATUS.md.
