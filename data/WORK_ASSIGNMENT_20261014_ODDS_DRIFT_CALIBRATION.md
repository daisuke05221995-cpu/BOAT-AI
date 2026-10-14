# WORK ASSIGNMENT — 2026-10-14 — Pre-close to start-time odds calibration

## Goal

Build an evidence-based correction table that estimates start/closing trifecta odds from BOAT AI's cached pre-close odds.

Normal chat is implementing production fallback behavior:
- official BOAT RACE odds first;
- if official fetch fails, use BoatraceCSV od3 pre-close snapshot;
- apply a conservative provisional start-time adjustment;
- never invent odds if no valid 120-way snapshot exists.

Do not edit production Android code, version files, or releases.

## Existing source

BoatraceCSV:
- realtime process runs every 5 minutes;
- `data/previews/od3/YYYY/MM/DD.csv` stores one 120-way trifecta snapshot per race roughly before close;
- fields include race code, close time, fetched timestamp, and all 120 trifecta odds;
- payout files provide the winning combination and its final payout.

Existing BOAT AI backtest already uses this od3 source.

## Important limitation

Historical payout gives the final realized price only for the winning combination. That is NOT a full 120-way final-odds table and can create outcome-selection bias.

Therefore:
1. use winning-combination comparisons only as a provisional diagnostic;
2. clearly label them as biased/incomplete;
3. do not claim the resulting factors are final production truth.

## Provisional diagnostic already observed

A small recent diagnostic (2026-10-08 through 2026-10-12, 765 matched races) found approximately:
- pre-close rank 1: median final/pre-close ratio ~0.92; median absolute change ~-0.7x
- rank 2: roughly in the same broader 2-3 band with stronger downward movement
- rank 2-3 combined: median ratio around the mid/high 0.8s
- rank 4-6: median ratio around high 0.8s
- rank 7-12: median ratio around high 0.8s
- longshot ranks were much noisier

These numbers are only a starting point.

## Tasks

1. Read latest main and CURRENT_STATUS.md.
2. Read:
   - scripts/backtest_odds_gate_2026.py
   - data/odds_gate_backtest_2026.json
   - latest odds-related Android code
3. Expand the historical diagnostic over as much 2026 od3+payout data as practical.
4. Group by:
   - minutes before scheduled close (e.g. <=4, 4-6, 6-8, 8-10, >10)
   - pre-close popularity rank buckets: 1, 2-3, 4-6, 7-12, 13-30, 31+
   - optionally odds bands if sample supports it
5. Report:
   - n
   - median final/pre-close ratio
   - mean ratio
   - median absolute odds difference
   - p10/p25/p75/p90 ratio
   - how often odds fall vs rise
6. Quantify the winning-combination selection bias and explain what cannot be inferred for all 120 combinations.
7. Propose a conservative correction table suitable only as a prior.
8. Define a future full-snapshot collection protocol that can remove the winner-only bias:
   - capture all 120 odds pre-close
   - capture all 120 odds as close/final as technically available
   - pair by combination
   - minimum sample requirements before replacing provisional factors
9. Do not change Model A, BUY/SKIP thresholds, stake allocation, or frozen live-money accounting.
10. Do not commit private user backups.

## Output

Create a dated report under data/:
- `ODDS_DRIFT_CALIBRATION_20261014.md`

Include:
- provisional correction table
- confidence/sample warnings
- recommendation: KEEP / UPDATE provisional Android priors
- exact next data requirement for a production-grade correction model.
