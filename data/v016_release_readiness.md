# BOAT AI v0.16 release readiness

Updated: 2026-09-24

- Forecast candidate: frozen market-free Model A reaction, temperature 1.0.
- September independent holdout: `PASS_FORECAST_HOLDOUT`.
- Q4 final forecast holdout: `PASS_Q4_FINAL_FORECAST`, Run `36004272796`.
- Q4 comparison population: 11,896 races, coverage 99.9412%, same-day history leak 0, duplicate keys 0.
- Q4 Model A vs v0.15.16: first Top1 57.8093% vs 46.1500%; trifecta Top4 30.6153% vs 19.3763%; LogLoss 3.761125 vs 4.181624.
- Q4 paired day-block LogLoss delta 95% CI: [-0.440041, -0.402842].
- Python/Kotlin raw score, 120-way probability, player history, and compact history parity: PASS, Run `36001980730`.
- JVM smoke: forecast median 6.212 ms, P95 7.806 ms.
- Deployment assets: Run `36005654248`, Artifact `10810058921`.
- Frozen tree SHA256 values match the research artifact.
- Player history asset is through 2026-09-23: 141,542 update races, 1,726 registered players, 4,222,646 bytes, SHA256 `a180aa722ad0520b5d86705bac742ff588309e72a49bed373eabf102f257acc3`.
- 2026 history source commits are pinned and docs/v2 is normalized into the frozen r4 schema.
- Market inputs: false.
- Automatic BUY: **OFF**. Historical odds remain unsuitable for realizable ROI promotion.

Next gate: full Android unit test + lint + Debug APK build with the actual embedded deployment assets. Only after SUCCESS may `versionName` be raised to `0.16.0` and the signed release workflow run.
