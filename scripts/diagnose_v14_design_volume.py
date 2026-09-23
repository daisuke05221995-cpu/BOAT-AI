#!/usr/bin/env python3
"""Diagnose v14 2023 design volume without opening any evaluation/holdout period.

This intentionally loads ONLY the 2023 signal cache. It measures ticket volume for the
existing frozen-calibration v14 grid. It does not choose a release strategy and does not
read 2024, 2025, or the reserved 2025-Q4 holdout.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import search_multiyear_strategy_v14 as v14


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cache = v14.Cache(args.cache_dir / "signal_cache_2023.npz")
    if cache.year != 2023:
        raise SystemExit(f"expected 2023 cache, got {cache.year}")

    fit = v14.fixed_2023_calibration(cache)
    prepared_2023 = {
        month: v14.calibrate_month(cache, month, fit)
        for month in v14.OPERATION_MONTHS
    }

    rows: list[dict[str, Any]] = []
    for cfg in v14.config_grid():
        monthly, total = v14.evaluate_year(prepared_2023, cfg)
        month_buys = [int(monthly[m]["purchaseRaces"]) for m in v14.OPERATION_MONTHS]
        active_rois = [float(monthly[m]["roi"]) for m in v14.OPERATION_MONTHS if month_buys[v14.OPERATION_MONTHS.index(m)] > 0]
        rows.append({
            "config": cfg,
            "monthlyBuys": {f"2023-{m:02d}": int(monthly[m]["purchaseRaces"]) for m in v14.OPERATION_MONTHS},
            "monthlyRoi": {f"2023-{m:02d}": float(monthly[m]["roi"]) for m in v14.OPERATION_MONTHS},
            "minMonthBuys": min(month_buys),
            "totalBuys": int(total["purchaseRaces"]),
            "totalRoi": float(total["roi"]),
            "positiveMonths": sum(v14.profitable(monthly[m]) for m in v14.OPERATION_MONTHS),
            "worstActiveRoi": min(active_rois, default=0.0),
        })

    by_min_month = sorted(
        rows,
        key=lambda row: (row["minMonthBuys"], row["totalBuys"], row["totalRoi"]),
        reverse=True,
    )
    by_total = sorted(
        rows,
        key=lambda row: (row["totalBuys"], row["minMonthBuys"], row["totalRoi"]),
        reverse=True,
    )

    feasibility = {}
    for monthly_floor in (30, 25, 20, 15, 10, 5, 1):
        for total_floor in (250, 200, 150, 100, 50):
            key = f"month{monthly_floor}_total{total_floor}"
            feasibility[key] = sum(
                row["minMonthBuys"] >= monthly_floor and row["totalBuys"] >= total_floor
                for row in rows
            )

    result = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "diagnosticOnly": True,
        "sourceYear": 2023,
        "evaluationYearsOpened": [],
        "reservedHoldoutOpened": False,
        "gridCount": len(rows),
        "currentDesignGuard": {
            "minMonthBuys": v14.DESIGN_MIN_MONTH_BUYS,
            "minTotalBuys": v14.DESIGN_MIN_TOTAL_BUYS,
        },
        "configsMeetingCurrentGuard": sum(
            row["minMonthBuys"] >= v14.DESIGN_MIN_MONTH_BUYS
            and row["totalBuys"] >= v14.DESIGN_MIN_TOTAL_BUYS
            for row in rows
        ),
        "bestByMinimumMonthlyVolume": by_min_month[:20],
        "bestByTotalVolume": by_total[:20],
        "feasibilityCounts": feasibility,
        "calibration": {
            "sourcePeriod": "2023-02-01..2023-04-30",
            "sampleRaces": int(fit["sampleRaces"]),
            "multipliers": [round(float(x), 6) for x in fit["multipliers"]],
        },
        "note": "2024/2025 and 2025-Q4 were not loaded or evaluated by this diagnostic.",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "configsMeetingCurrentGuard": result["configsMeetingCurrentGuard"],
        "bestByMinimumMonthlyVolume": result["bestByMinimumMonthlyVolume"][:5],
        "bestByTotalVolume": result["bestByTotalVolume"][:5],
        "feasibilityCounts": feasibility,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
