# Odds drift research — 2026-10-14

Research-only source collection and diagnostics. No Model A, BUY/SKIP, stake, Android, or live-money evaluator dependency.

Requires Python 3.10+, numpy and pandas. The CSV inventory is pinned to BoatraceCSV commit `31b03b22989700a9f3a94152ae88edcaa1642124`. Primary coverage is all available 2026 od3 dates through the last complete day, 2026-07-19..2026-10-13. The exploratory full-final panel uniformly selects 8 races per date, independently of winner rank, payout and drift, seed 20261014. Selection is among structurally valid primary matches. Never replace failed panel races with favorable alternatives.

```bash
python scripts/odds_drift/download.py --root odds_drift_work
python scripts/odds_drift/analyze.py --root odds_drift_work
python scripts/odds_drift/restore_raw.py --root odds_drift_work
python scripts/odds_drift/full_panel.py --root odds_drift_work
python -m unittest discover -s scripts/odds_drift -p 'test_semantics.py' -v
```

Restore the committed public evidence archive before the full-panel analysis to reproduce the dated result without querying mutable official files again. Every raw file hash and original response-receipt file timestamp is checked/preserved. Omit the restore step only for a new exploratory collection; compare its hashes and do not silently replace the historical result.

The final collector caps request starts at 2/second with at most 8 concurrent requests. It retries network failures twice, records complete final-file mismatches with the winning payout without filtering on that outcome, and rejects incomplete/nonpositive/nonfinite 120-way final files. It recognizes the integer display precision of quotes at 1000x and above. Raw official files are cached locally; checksums and excluded race codes are reported. Ratios are final / pre-close; differences are final minus pre-close. Signed and unsigned differences are both retained.

`validation.py` reads independently fetched official HTML pages from `cache/official_odds3t_<racecode>.html` and compares the explicit HTML lane labels, including rowspans, with the 120-column final file. This is an auxiliary mapping check, not a scraper or scheduler for production.

Treat primary payout comparisons as winner-selected diagnostics. Treat the small full-final panel as an equal-day exploratory panel with clustered observations; the number of independent races is not the number of combinations. Bootstrap confidence intervals resample calendar days, 800 replicates, seed 20261014. They describe sampling uncertainty and do not remove source, time-label or selection bias.

Use the dated report and future capture protocol for promotion requirements. Generated files belong under the selected work directory; raw source CSVs and any private device backups are not added to this repository.
