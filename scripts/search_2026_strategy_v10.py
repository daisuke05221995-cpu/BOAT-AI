#!/usr/bin/env python3
"""Robust historical-odds value search with September as untouched holdout.

This stage keeps the v9 model/odds mechanics but uses a predeclared robustness rule
that allows one negative development month. September is never used to select the
strategy and is evaluated only after May-Aug parameters are frozen.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import search_2026_strategy_v6_compat  # type: ignore  # noqa: F401
import search_2026_strategy_v9 as v9
from build_2026_backtest import JST, LearningProfile

MIN_MONTH_BUYS = 100
MIN_DEV_BUYS = 400
MIN_DEV_ROI = 110.0
MIN_WORST_MONTH_ROI = 85.0
MIN_POSITIVE_MONTHS = 3


def qualifies(item: dict[str, Any]) -> bool:
    months = list(item["developmentMonths"].values())
    positive = sum(1 for stats in months if v9.profitable(stats))
    return (
        int(item["development"]["purchaseRaces"]) >= MIN_DEV_BUYS
        and float(item["development"]["roi"]) >= MIN_DEV_ROI
        and positive >= MIN_POSITIVE_MONTHS
        and all(int(stats["purchaseRaces"]) >= MIN_MONTH_BUYS for stats in months)
        and min(float(stats["roi"]) for stats in months) >= MIN_WORST_MONTH_ROI
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    today_jst = datetime.now(JST).date()
    data_end = args.end or min(today_jst - timedelta(days=1), date(2026, 12, 31))
    if data_end < date(2026, 9, 1):
        raise SystemExit("September holdout has not started")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    records, race_errors = v9.build_records(args.start, data_end, learning, args.workers)
    if race_errors:
        raise SystemExit(f"race download failures: {race_errors}")

    odds_by_day, odds_errors = v9.fetch_odds_range(date(2026, 5, 1), data_end, args.workers)
    if odds_errors:
        raise SystemExit(f"odds download failures: {odds_errors}")

    dev, missing_dev = v9.build_month_signals(records, odds_by_day, v9.DEV_MONTHS)
    if any(len(dev[f"2026-{month:02d}"]) < 500 for month in v9.DEV_MONTHS):
        raise RuntimeError(f"insufficient odds-matched development signals: { {k: len(v) for k, v in dev.items()} }")

    gate_candidates: list[dict[str, Any]] = []
    for alpha in v9.ALPHAS:
        prepared = v9.prepare_months(dev, alpha)
        for min_ev in v9.MIN_EV_OPTIONS:
            for min_prob in v9.MIN_PROB_OPTIONS:
                for max_odds in v9.MAX_ODDS_OPTIONS:
                    cfg = {
                        "alpha": alpha,
                        "minEv": min_ev,
                        "minProbability": min_prob,
                        "maxOdds": max_odds,
                        "maxPoints": 1,
                        "allocationMode": "equal",
                        "budget": v9.BUDGET,
                    }
                    monthly, total = v9.evaluate_prepared(prepared, cfg)
                    if int(total["purchaseRaces"]) < MIN_DEV_BUYS:
                        continue
                    gate_candidates.append({
                        "config": cfg,
                        "monthly": monthly,
                        "total": total,
                        "score": v9.robust_score(monthly, total),
                    })
        print(f"alpha={alpha:.2f} gate search complete", flush=True)

    if not gate_candidates:
        raise RuntimeError("no gate candidates")
    gate_candidates.sort(key=lambda item: item["score"], reverse=True)
    gate_candidates = gate_candidates[: v9.KEEP_GATES]

    candidates: list[dict[str, Any]] = []
    for alpha in sorted({float(item["config"]["alpha"]) for item in gate_candidates}):
        prepared = v9.prepare_months(dev, alpha)
        for gate in [item for item in gate_candidates if float(item["config"]["alpha"]) == alpha]:
            base = gate["config"]
            for points in v9.POINT_OPTIONS:
                for mode in v9.ALLOCATION_MODES:
                    cfg = {**base, "maxPoints": points, "allocationMode": mode}
                    monthly, total = v9.evaluate_prepared(prepared, cfg)
                    candidates.append({
                        "config": cfg,
                        "developmentMonths": monthly,
                        "development": total,
                        "score": v9.robust_score(monthly, total),
                    })
        print(f"alpha={alpha:.2f} ticket search complete", flush=True)

    eligible = [item for item in candidates if qualifies(item)]
    pool = eligible or candidates
    pool.sort(
        key=lambda item: (
            1 if item in eligible else 0,
            item["score"][1],
            item["score"][2],
            item["score"][3],
            item["score"][4],
        ),
        reverse=True,
    )
    selected = pool[0]
    cfg = selected["config"]
    qualified_for_final = selected in eligible

    final_stats: dict[str, Any] | None = None
    final_signal_count = 0
    final_missing = 0
    qualified_for_release = False
    combined_through_final: dict[str, Any] | None = None
    if qualified_for_final:
        final_model = v9.v6.fit_conditional_model(records, date(2026, 1, 1), date(2026, 8, 31))
        final_signals, final_missing = v9.make_signals(
            final_model,
            records,
            date(2026, 9, 1),
            data_end,
            odds_by_day,
        )
        final_signal_count = len(final_signals)
        prepared_final = {
            "2026-09": [v9.prepare_signal(signal, float(cfg["alpha"])) for signal in final_signals]
        }
        final_monthly, _ = v9.evaluate_prepared(prepared_final, cfg)
        final_stats = final_monthly["2026-09"]
        combined_through_final = v9.combine([selected["development"], final_stats])
        qualified_for_release = bool(
            int(final_stats["purchaseRaces"]) >= 20
            and v9.profitable(final_stats)
            and float(combined_through_final["roi"]) > 100.0
        )

    result = {
        "schemaVersion": 10,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "v9 odds-value model with robust 3-of-4 development-month rule; September strict holdout",
        "oddsFinalGateIncluded": True,
        "oddsSource": "lamrongol/BoatraceOdds v3 archive (production continues to use official BOAT RACE odds)",
        "periods": {
            "train": ["2026-01-01", "2026-04-30"],
            "development": ["2026-05-01", "2026-08-31"],
            "final": ["2026-09-01", data_end.isoformat()],
        },
        "developmentRule": {
            "minPositiveMonths": MIN_POSITIVE_MONTHS,
            "minCombinedRoi": MIN_DEV_ROI,
            "minWorstMonthRoi": MIN_WORST_MONTH_ROI,
            "minPurchasesPerMonth": MIN_MONTH_BUYS,
            "minCombinedPurchases": MIN_DEV_BUYS,
        },
        "selected": selected,
        "validationMonths": {
            "2026-07": selected["developmentMonths"].get("2026-07", {}),
            "2026-08": selected["developmentMonths"].get("2026-08", {}),
        },
        "validation": v9.combine([
            selected["developmentMonths"].get("2026-07", v9.empty_stats()),
            selected["developmentMonths"].get("2026-08", v9.empty_stats()),
        ]),
        "final": final_stats if final_stats is not None else {"withheld": True},
        "combinedThroughFinal": combined_through_final if combined_through_final is not None else {"withheld": True},
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "oddsCoverage": {
            "daysLoaded": len(odds_by_day),
            "developmentSignals": {key: len(value) for key, value in dev.items()},
            "developmentMissingRaces": missing_dev,
            "finalSignals": final_signal_count,
            "finalMissingRaces": final_missing,
        },
        "releaseRule": "May-Aug: >=3 profitable months, combined ROI >=110%, worst month >=85%, >=100 buys/month; then Sep must be profitable with >=20 buys and May-Sep combined >100%",
        "topCandidates": pool[:20],
        "notes": [
            "September is not used for strategy selection.",
            "One negative development month is allowed to avoid rejecting a positive strategy solely due to monthly variance.",
            "Historical odds are archived snapshots and can differ from the exact live purchase second.",
            "Production continues to fetch official BOAT RACE odds.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "selected": selected,
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "final": result["final"],
        "combinedThroughFinal": result["combinedThroughFinal"],
        "oddsCoverage": result["oddsCoverage"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
