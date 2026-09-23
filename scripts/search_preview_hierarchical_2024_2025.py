#!/usr/bin/env python3
"""Design a preview-enhanced hierarchical value strategy on 2024 and freeze it for 2025.

Protocol
--------
* 2024 Feb-Apr outcomes fit the fixed hierarchical market calibration.
* 2024 May-Sep outcomes may be used to choose ticket thresholds (development only).
* Calibration and ticket thresholds are then frozen.
* 2025 May-Sep is evaluated with NO refit or threshold changes.
* 2025 Oct-Dec remains unopened and is not loaded by this script.

Both 2024 and 2025 May-Sep were inspected by earlier strategy families, so this is
robust development evidence, not pristine holdout proof. The reserved 2025-Q4 period
is the only final holdout.
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

BUDGET = 1200
BUDGET_UNITS = 12
CALIBRATION_MONTHS = (2, 3, 4)
OPERATION_MONTHS = (5, 6, 7, 8, 9)

# Small, pre-declared grid. No venue/month-specific rules are searched.
MIN_EV_OPTIONS = (1.00, 1.02, 1.05, 1.08, 1.10)
MIN_PROB_OPTIONS = (0.003, 0.005, 0.010, 0.020)
MAX_ODDS_OPTIONS = (20.0, 40.0, 80.0)
POINT_OPTIONS = (1, 2, 3)

DESIGN_MIN_MONTH_BUYS = 10
DESIGN_MIN_TOTAL_BUYS = 75
TARGET_MIN_MONTH_BUYS = 10
TARGET_MIN_TOTAL_BUYS = 100
TARGET_MIN_ROI = 105.0
TARGET_MIN_POSITIVE_MONTHS = 4
TARGET_MIN_WORST_ROI = 90.0
TARGET_MAX_LARGEST_HIT_SHARE = 25.0


def load_cache(cache_dir: Path, year: int) -> v14.Cache:
    path = cache_dir / f"signal_cache_{year}.npz"
    if not path.exists():
        raise FileNotFoundError(path)
    cache = v14.Cache(path)
    if cache.year != year:
        raise RuntimeError(f"cache year mismatch {path}: {cache.year}")
    return cache


def prepare_month(cache: v14.Cache, month: int, fitted: dict[str, Any]) -> dict[str, np.ndarray]:
    p, ev, odds = hierarchy.calibrated_month(cache, month, fitted)
    mask = cache.month == month
    actual = cache.actual[mask]
    amount = cache.amount[mask]
    order = np.argsort(-ev, axis=1)
    return {
        "p": np.take_along_axis(p, order, axis=1),
        "ev": np.take_along_axis(ev, order, axis=1),
        "odds": np.take_along_axis(odds, order, axis=1),
        "comboIndex": order,
        "actual": actual,
        "amount": amount,
    }


def config_grid() -> list[dict[str, Any]]:
    return [
        {
            "minEv": min_ev,
            "minProbability": min_prob,
            "maxOdds": max_odds,
            "maxPoints": max_points,
            "allocationMode": "equal",
            "budget": BUDGET,
        }
        for min_ev in MIN_EV_OPTIONS
        for min_prob in MIN_PROB_OPTIONS
        for max_odds in MAX_ODDS_OPTIONS
        for max_points in POINT_OPTIONS
    ]


def finalize(
    purchase_races: int,
    hits: int,
    stake: int,
    payout: int,
    bets: int,
    largest_hit_payout: int,
) -> dict[str, Any]:
    return {
        "purchaseRaces": int(purchase_races),
        "hits": int(hits),
        "stake": int(stake),
        "payout": int(payout),
        "profit": int(payout - stake),
        "roi": round(payout * 100.0 / stake, 1) if stake else 0.0,
        "hitRate": round(hits * 100.0 / purchase_races, 1) if purchase_races else 0.0,
        "bets": int(bets),
        "avgPoints": round(bets / purchase_races, 2) if purchase_races else 0.0,
        "largestHitPayout": int(largest_hit_payout),
        "largestHitShare": round(largest_hit_payout * 100.0 / payout, 1) if payout else 0.0,
    }


def evaluate_month(prepared: dict[str, np.ndarray], cfg: dict[str, Any]) -> dict[str, Any]:
    p = prepared["p"]
    ev = prepared["ev"]
    odds = prepared["odds"]
    order = prepared["comboIndex"]
    actual = prepared["actual"]
    amount = prepared["amount"]

    eligible = (
        (ev >= float(cfg["minEv"]))
        & (p >= float(cfg["minProbability"]))
        & (odds > 0.0)
        & (odds <= float(cfg["maxOdds"]))
    )
    rank = np.cumsum(eligible, axis=1)
    take = eligible & (rank <= int(cfg["maxPoints"]))
    point_count = take.sum(axis=1).astype(np.int64)
    buy = point_count > 0
    purchase_races = int(buy.sum())
    if purchase_races == 0:
        return finalize(0, 0, 0, 0, 0, 0)

    base_units = np.zeros(len(point_count), dtype=np.int64)
    base_units[buy] = BUDGET_UNITS // point_count[buy]
    remainder = np.zeros(len(point_count), dtype=np.int64)
    remainder[buy] = BUDGET_UNITS - base_units[buy] * point_count[buy]
    units = np.where(
        take,
        base_units[:, None] + ((rank <= remainder[:, None]) & take).astype(np.int64),
        0,
    )

    actual_match = order == actual[:, None]
    actual_units = (units * actual_match).sum(axis=1).astype(np.int64)
    race_payout = amount.astype(np.int64) * actual_units
    hits = int((actual_units > 0).sum())
    payout = int(race_payout.sum())
    largest_hit = int(race_payout.max(initial=0))
    stake = purchase_races * BUDGET
    bets = int(point_count[buy].sum())
    return finalize(purchase_races, hits, stake, payout, bets, largest_hit)


def combine(rows: list[dict[str, Any]]) -> dict[str, Any]:
    purchase_races = sum(int(row["purchaseRaces"]) for row in rows)
    hits = sum(int(row["hits"]) for row in rows)
    stake = sum(int(row["stake"]) for row in rows)
    payout = sum(int(row["payout"]) for row in rows)
    bets = sum(int(row["bets"]) for row in rows)
    largest = max((int(row["largestHitPayout"]) for row in rows), default=0)
    return finalize(purchase_races, hits, stake, payout, bets, largest)


def evaluate_year(
    prepared: dict[int, dict[str, np.ndarray]], cfg: dict[str, Any]
) -> tuple[dict[int, dict[str, Any]], dict[str, Any]]:
    monthly = {month: evaluate_month(prepared[month], cfg) for month in OPERATION_MONTHS}
    return monthly, combine(list(monthly.values()))


def positive(row: dict[str, Any]) -> bool:
    return int(row["purchaseRaces"]) > 0 and int(row["profit"]) > 0


def robustness(monthly: dict[int, dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
    rows = list(monthly.values())
    positive_months = sum(positive(row) for row in rows)
    worst_roi = min((float(row["roi"]) for row in rows), default=0.0)
    volume_ok = all(int(row["purchaseRaces"]) >= TARGET_MIN_MONTH_BUYS for row in rows)
    target = bool(
        int(total["purchaseRaces"]) >= TARGET_MIN_TOTAL_BUYS
        and float(total["roi"]) >= TARGET_MIN_ROI
        and positive_months >= TARGET_MIN_POSITIVE_MONTHS
        and worst_roi >= TARGET_MIN_WORST_ROI
        and float(total["largestHitShare"]) <= TARGET_MAX_LARGEST_HIT_SHARE
        and volume_ok
    )
    return {
        "positiveMonths": positive_months,
        "worstMonthRoi": worst_roi,
        "volumeOk": volume_ok,
        "largestHitShareOk": float(total["largestHitShare"]) <= TARGET_MAX_LARGEST_HIT_SHARE,
        "targetMet": target,
    }


def design_score(monthly: dict[int, dict[str, Any]], total: dict[str, Any]) -> tuple[Any, ...]:
    rows = list(monthly.values())
    positive_months = sum(positive(row) for row in rows)
    worst_roi = min((float(row["roi"]) for row in rows), default=0.0)
    # Jackpot concentration is penalized before total ROI.
    concentration_score = -float(total["largestHitShare"])
    return (
        positive_months,
        worst_roi,
        concentration_score,
        float(total["roi"]),
        int(total["purchaseRaces"]),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    cache_2024 = load_cache(args.cache_dir, 2024)
    cache_2025 = load_cache(args.cache_dir, 2025)

    # Fit once on 2024 Feb-Apr. This object is frozen before 2025 is evaluated.
    fitted = hierarchy.fit(cache_2024)
    prepared_2024 = {
        month: prepare_month(cache_2024, month, fitted) for month in OPERATION_MONTHS
    }
    prepared_2025 = {
        month: prepare_month(cache_2025, month, fitted) for month in OPERATION_MONTHS
    }

    ranked: list[tuple[tuple[Any, ...], dict[str, Any], dict[int, dict[str, Any]], dict[str, Any]]] = []
    for cfg in config_grid():
        monthly, total = evaluate_year(prepared_2024, cfg)
        if int(total["purchaseRaces"]) < DESIGN_MIN_TOTAL_BUYS:
            continue
        if any(int(row["purchaseRaces"]) < DESIGN_MIN_MONTH_BUYS for row in monthly.values()):
            continue
        ranked.append((design_score(monthly, total), cfg, monthly, total))

    if not ranked:
        raise RuntimeError("no 2024 preview-enhanced config met basic volume guards")
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, selected, design_monthly, design_total = ranked[0]

    design_metrics = robustness(design_monthly, design_total)
    frozen_monthly, frozen_total = evaluate_year(prepared_2025, selected)
    frozen_metrics = robustness(frozen_monthly, frozen_total)

    ready_for_holdout = bool(design_metrics["targetMet"] and frozen_metrics["targetMet"])

    result = {
        "schemaVersion": 17,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "releaseQualified": False,
        "method": (
            "preview-enhanced hierarchical market calibration fitted on 2024 Feb-Apr; "
            "ticket config selected on 2024 May-Sep; both frozen for 2025 May-Sep"
        ),
        "featurePolicy": (
            "pre-race program metrics + prior-race average ST + archived exhibition "
            "course/ST/time + wind/wave; historical learning-bonus input forced to zero"
        ),
        "calibration": {
            "sourcePeriod": "2024-02-01..2024-04-30",
            "sampleRaces": int(fitted["sampleRaces"]),
            "parentPriorExpected": hierarchy.PARENT_PRIOR_EXPECTED,
            "cellPriorExpected": hierarchy.CELL_PRIOR_EXPECTED,
            "liftCap": [hierarchy.LIFT_MIN, hierarchy.LIFT_MAX],
        },
        "selectedTicketConfig": selected,
        "design2024": {
            "period": "2024-05-01..2024-09-30",
            "score": list(score),
            "months": {f"2024-{month:02d}": design_monthly[month] for month in OPERATION_MONTHS},
            "total": design_total,
            **design_metrics,
        },
        "frozenEvaluation2025": {
            "period": "2025-05-01..2025-09-30",
            "months": {f"2025-{month:02d}": frozen_monthly[month] for month in OPERATION_MONTHS},
            "total": frozen_total,
            **frozen_metrics,
        },
        "readyForFinalHoldout": ready_for_holdout,
        "holdoutPolicy": {
            "reserved": "2025-10-01..2025-12-31",
            "opened": False,
            "rule": "Open exactly once only when readyForFinalHoldout=true; never retune after viewing it.",
        },
        "acceptance": {
            "minTotalBuys": TARGET_MIN_TOTAL_BUYS,
            "minMonthlyBuys": TARGET_MIN_MONTH_BUYS,
            "minRoi": TARGET_MIN_ROI,
            "minPositiveMonths": TARGET_MIN_POSITIVE_MONTHS,
            "minWorstMonthRoi": TARGET_MIN_WORST_ROI,
            "maxLargestHitShare": TARGET_MAX_LARGEST_HIT_SHARE,
        },
        "notes": [
            "2024 and 2025 May-Sep are development evidence because prior strategy families inspected their outcomes.",
            "2025 Oct-Dec remains the pristine final holdout and is not loaded by this script.",
            "No month/venue-specific thresholds are searched.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "selectedTicketConfig": selected,
        "design2024": {"total": design_total, **design_metrics},
        "frozenEvaluation2025": {"total": frozen_total, **frozen_metrics},
        "readyForFinalHoldout": ready_for_holdout,
        "holdoutOpened": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
