# BOAT AI DEVELOPMENT ROUTING

Updated: 2026-10-11

This file defines how future BOAT AI work is split between normal ChatGPT and ChatGPT Work.

## Source of truth
Always start from:
1. latest main and latest GitHub Release
2. current GitHub Actions
3. CURRENT_STATUS.md
4. latest dated assignment/handoff under data/

Never rely on an older chat summary when repository state is newer.

## Normal ChatGPT — implementation / integration owner
Use for:
- deciding product behavior and user-facing scope
- production Android implementation
- code fixes and tests
- versionCode/versionName
- CI/build error diagnosis and follow-up
- release publication
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
- operational continuity reviews
- reports and handoff documents

Default boundary:
- do not edit production app/
- do not bump versionCode/versionName
- do not publish releases
- do not commit private BOAT-AI-backup.json
unless a dated assignment explicitly changes the boundary.

## Codex status

Codex is **suspended from the normal BOAT AI workflow** because its cloud environment/repository handoff added more setup friction than value for this project.

Historical Codex assignment files may remain for audit/history, but they are not active tasks.
Do not ask the user to run Codex unless the user explicitly decides to restore it later.

## Gambling transaction boundary
BOAT AI may:
- calculate BUY/SKIP
- calculate combinations and stake amounts
- automatically save a local pending-purchase draft
- open the official purchase surface
- record purchases after user confirmation

BOAT AI must not implement an unattended external wager submission. Final submission remains user-confirmed on the official service.

## Current working model
- Normal ChatGPT: implementation, Android changes, CI, release, integration
- Work: research/evidence only when a concrete analysis task exists

When Work is useful, normal chat must explicitly tell the user:
- `Workへの指示：あり`
- exact assignment file/path to send

When Work is not needed, normal chat should say:
- `Workへの指示：なし`

## Handoff rule
Every substantial task should end with:
- commit SHA
- GitHub Actions Run IDs
- what changed
- what remains
- any real-device verification required

Normal chat then integrates the result and updates CURRENT_STATUS.md.
