# v0.16 Model A 2025 Q4 final forecast holdout

- Protocol: `3a56378244dd1f3621f862ac89cea3db8ccea6af` (committed before Q4 access).
- Decision: **PASS_Q4_FINAL_FORECAST**.
- Comparison races: 11,896; coverage 99.941%; same-day leak 0; duplicate keys 0.

## Frozen Model A vs v0.15.16 baseline
- LogLoss: 3.761125 vs 4.181624
- Brier: 0.957727 vs 0.976797
- First Top1: 57.809% vs 46.150%
- First Top2: 76.547% vs 67.628%
- Trifecta Top1: 10.625% vs 5.901%
- Trifecta Top4: 30.615% vs 19.376%
- Trifecta Top8: 46.738% vs 31.952%

- Paired day-block LogLoss delta 95% CI: [-0.44004084209313427, -0.4028417702079884]
- Primary pass: True; secondary safety: True.

- Forecast-only. Odds/payout/ROI/BUY were not read or evaluated. Automatic BUY remains OFF.
