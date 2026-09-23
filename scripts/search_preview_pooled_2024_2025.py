#!/usr/bin/env python3
"""Pool preview-era calibration data, design on 2024, freeze-evaluate on 2025.

Leakage / development protocol:
- Hierarchical market lift calibration uses only preview-era 2023 May-Sep plus
  2024 Feb-Apr. Fixed bins, priors and caps are inherited unchanged from v15.
- Ticket thresholds are selected on 2024 May-Sep (development period).
- Calibration + ticket thresholds are then frozen and applied to 2025 May-Sep.
- 2025 Oct-Dec is NEVER loaded by this script and remains the reserved final holdout.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import diagnose_v15_hierarchical_edge as hierarchy
import search_multiyear_strategy_v14 as v14
import search_preview_hierarchical_2024_2025 as ticket

CAL_2023_MONTHS = (5, 6, 7, 8, 9)
CAL_2024_MONTHS = (2, 3, 4)
OPERATION_MONTHS = ticket.OPERATION_MONTHS


def _cache_slice(cache: v14.Cache, months: tuple[int, ...]) -> dict[str, np.ndarray]:
    mask = np.isin(cache.month, months)
    return {
        "model": cache.model_p[mask],
        "market": cache.market_p[mask],
        "odds": cache.odds[mask],
        "actual": cache.actual[mask],
    }


def fit_pooled(cache_2023: v14.Cache, cache_2024: v14.Cache) -> dict[str, Any]:
    if cache_2023.combos.tolist() != cache_2024.combos.tolist():
        raise RuntimeError("combo ordering differs between preview caches")

    chunks = [
        _cache_slice(cache_2023, CAL_2023_MONTHS),
        _cache_slice(cache_2024, CAL_2024_MONTHS),
    ]
    model = np.concatenate([c["model"] for c in chunks], axis=0)
    market = np.concatenate([c["market"] for c in chunks], axis=0)
    odds = np.concatenate([c["odds"] for c in chunks], axis=0)
    actual = np.concatenate([c["actual"] for c in chunks], axis=0)

    valid = (model > 0.0) & (market > 0.0) & (odds > 0.0)
    log_ratio = np.zeros_like(model, dtype=np.float64)
    log_ratio[valid] = np.log(model[valid] / market[valid])
    ratio_bin = np.digitize(
        log_ratio, hierarchy.LOG_RATIO_EDGES[1:-1], right=False
    ).astype(np.int8)
    odds_bin = np.digitize(
        odds, hierarchy.ODDS_EDGES[1:-1], right=False
    ).astype(np.int8)
    lane_groups = hierarchy.combo_lane_groups(cache_2024.combos)
    rows = np.arange(len(actual))

    parent: dict[tuple[int, int], dict[str, float]] = {}
    for g in range(3):
        lane_mask = lane_groups[None, :] == g
        for rb in range(len(hierarchy.LOG_RATIO_EDGES) - 1):
            cell = valid & lane_mask & (ratio_bin == rb)
            expected = float(market[cell].sum())
            hit_mask = (
                (lane_groups[actual] == g)
                & (ratio_bin[rows, actual] == rb)
                & valid[rows, actual]
            )
            observed = float(hit_mask.sum())
            lift = (observed + hierarchy.PARENT_PRIOR_EXPECTED) / (
                expected + hierarchy.PARENT_PRIOR_EXPECTED
            )
            lift = max(hierarchy.LIFT_MIN, min(hierarchy.LIFT_MAX, lift))
            parent[(g, rb)] = {
                "observed": observed,
                "expected": expected,
                "lift": lift,
                "candidates": int(cell.sum()),
            }

    cells: dict[tuple[int, int, int], dict[str, float]] = {}
    for g in range(3):
        lane_mask = lane_groups[None, :] == g
        for rb in range(len(hierarchy.LOG_RATIO_EDGES) - 1):
            parent_lift = float(parent[(g, rb)]["lift"])
            for ob in range(len(hierarchy.ODDS_EDGES) - 1):
                cell = valid & lane_mask & (ratio_bin == rb) & (odds_bin == ob)
                expected = float(market[cell].sum())
                hit_mask = (
                    (lane_groups[actual] == g)
                    & (ratio_bin[rows, actual] == rb)
                    & (odds_bin[rows, actual] == ob)
                    & valid[rows, actual]
                )
                observed = float(hit_mask.sum())
                lift = (
                    observed + hierarchy.CELL_PRIOR_EXPECTED * parent_lift
                ) / (expected + hierarchy.CELL_PRIOR_EXPECTED)
                lift = max(hierarchy.LIFT_MIN, min(hierarchy.LIFT_MAX, lift))
                cells[(g, rb, ob)] = {
                    "observed": observed,
                    "expected": expected,
                    "lift": lift,
                    "candidates": int(cell.sum()),
                }

    return {
        "parent": parent,
        "cells": cells,
        "sampleRaces": int(len(actual)),
        "sources": {
            "2023": "2023-05-01..2023-09-30",
            "2024": "2024-02-01..2024-04-30",
        },
    }


def prepare_year(cache: v14.Cache, fitted: dict[str, Any]) -> dict[int, dict[str, np.ndarray]]:
    return {m: ticket.prepare_month(cache, m, fitted) for m in OPERATION_MONTHS}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cache-dir", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()

    c23 = ticket.load_cache(args.cache_dir, 2023)
    c24 = ticket.load_cache(args.cache_dir, 2024)
    c25 = ticket.load_cache(args.cache_dir, 2025)
    fitted = fit_pooled(c23, c24)

    prepared_2024 = prepare_year(c24, fitted)
    prepared_2025 = prepare_year(c25, fitted)

    all_candidates: list[
        tuple[tuple[Any, ...], dict[str, Any], dict[int, dict[str, Any]], dict[str, Any]]
    ] = []
    for cfg in ticket.config_grid():
        monthly, total = ticket.evaluate_year(prepared_2024, cfg)
        min_month = min(int(row["purchaseRaces"]) for row in monthly.values())
        if int(total["purchaseRaces"]) < ticket.DESIGN_MIN_TOTAL_BUYS:
            continue
        if min_month < ticket.DESIGN_MIN_MONTH_BUYS:
            continue
        all_candidates.append((ticket.design_score(monthly, total), cfg, monthly, total))

    # Always write a diagnostic payload even when the volume guard is not feasible.
    volume_rows: list[dict[str, Any]] = []
    for cfg in ticket.config_grid():
        monthly, total = ticket.evaluate_year(prepared_2024, cfg)
        volume_rows.append({
            "config": cfg,
            "minMonthBuys": min(int(row["purchaseRaces"]) for row in monthly.values()),
            "positiveMonths": sum(ticket.positive(row) for row in monthly.values()),
            "worstMonthRoi": min(float(row["roi"]) for row in monthly.values()),
            "total": total,
            "months": {f"2024-{m:02d}": monthly[m] for m in OPERATION_MONTHS},
        })
    volume_rows.sort(
        key=lambda r: (
            r["minMonthBuys"],
            r["total"]["purchaseRaces"],
            r["positiveMonths"],
            r["worstMonthRoi"],
            r["total"]["roi"],
        ),
        reverse=True,
    )

    result: dict[str, Any] = {
        "schemaVersion": 18,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "releaseQualified": False,
        "method": "fixed hierarchical calibration pooled across preview-era 2023 May-Sep + 2024 Feb-Apr",
        "calibration": {
            "sampleRaces": fitted["sampleRaces"],
            "sources": fitted["sources"],
            "parentPriorExpected": hierarchy.PARENT_PRIOR_EXPECTED,
            "cellPriorExpected": hierarchy.CELL_PRIOR_EXPECTED,
            "liftCap": [hierarchy.LIFT_MIN, hierarchy.LIFT_MAX],
            "binsChanged": False,
        },
        "basicVolumeFeasible": bool(all_candidates),
        "bestByVolume": volume_rows[:10],
        "holdoutPolicy": {
            "reserved": "2025-10-01..2025-12-31",
            "opened": False,
        },
    }

    if all_candidates:
        all_candidates.sort(key=lambda item: item[0], reverse=True)
        score, selected, design_monthly, design_total = all_candidates[0]
        design_metrics = ticket.robustness(design_monthly, design_total)
        frozen_monthly, frozen_total = ticket.evaluate_year(prepared_2025, selected)
        frozen_metrics = ticket.robustness(frozen_monthly, frozen_total)
        result.update({
            "selectedTicketConfig": selected,
            "design2024": {
                "period": "2024-05-01..2024-09-30",
                "score": list(score),
                "months": {f"2024-{m:02d}": design_monthly[m] for m in OPERATION_MONTHS},
                "total": design_total,
                **design_metrics,
            },
            "frozenEvaluation2025": {
                "period": "2025-05-01..2025-09-30",
                "months": {f"2025-{m:02d}": frozen_monthly[m] for m in OPERATION_MONTHS},
                "total": frozen_total,
                **frozen_metrics,
            },
            "readyForFinalHoldout": bool(
                design_metrics["targetMet"] and frozen_metrics["targetMet"]
            ),
        })
    else:
        result["readyForFinalHoldout"] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(json.dumps({
        "calibrationSampleRaces": fitted["sampleRaces"],
        "basicVolumeFeasible": result["basicVolumeFeasible"],
        "bestByVolume": result["bestByVolume"][:3],
        "selectedTicketConfig": result.get("selectedTicketConfig"),
        "design2024": result.get("design2024"),
        "frozenEvaluation2025": result.get("frozenEvaluation2025"),
        "readyForFinalHoldout": result["readyForFinalHoldout"],
        "holdoutOpened": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
