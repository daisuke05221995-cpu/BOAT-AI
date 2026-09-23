#!/usr/bin/env python3
"""BOAT AI v14 research: fixed empirical model-vs-market calibration.

Strict research protocol:
1. Fit model-vs-market calibration ONLY on 2023 Feb-Apr.
2. Freeze that calibration.
3. Design ticket thresholds on 2023 May-Sep.
4. Freeze ticket thresholds.
5. Apply both frozen calibration and frozen ticket thresholds to 2024 and 2025
   May-Sep without any retuning or monthly adaptation.

This is intentionally stricter than the earlier monthly-adaptive experiments and is
also directly portable to Android as a static model asset. 2023-2025 have been
inspected by earlier experiments, so this is development evidence rather than pristine
holdout proof. A separate 2025 Oct-Dec holdout is reserved and must remain unopened
until v14 is fully frozen and the 2024/2025 evaluation is satisfactory.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BUDGET = 1200
BUDGET_UNITS = 12
CALIBRATION_MONTHS = (2, 3, 4)
OPERATION_MONTHS = (5, 6, 7, 8, 9)

# Fixed before looking at v14 outcomes. These are not searched.
BIN_EDGES = np.asarray(
    [-np.inf, -2.0, -1.25, -0.75, -0.35, 0.0, 0.35, 0.75, 1.25, 2.0, np.inf],
    dtype=np.float64,
)
PRIOR_EXPECTED_WINS = 100.0
MULTIPLIER_MIN = 0.50
MULTIPLIER_MAX = 1.75

# Ticket search is allowed only on 2023 May-Sep design data.
MIN_EV_OPTIONS = (1.02, 1.05, 1.10, 1.15, 1.20)
MIN_PROB_OPTIONS = (0.005, 0.010, 0.020)
MAX_ODDS_OPTIONS = (20.0, 40.0, 80.0, 150.0)
POINT_OPTIONS = (1, 2, 3)

DESIGN_MIN_MONTH_BUYS = 30
DESIGN_MIN_TOTAL_BUYS = 250
RESEARCH_MIN_MONTH_BUYS = 30
RESEARCH_MIN_TOTAL_BUYS = 250
RESEARCH_MIN_ROI = 105.0
RESEARCH_MIN_POSITIVE_MONTHS = 4
RESEARCH_MIN_WORST_ROI = 90.0


class Cache:
    def __init__(self, path: Path):
        arr = np.load(path)
        self.year = int(arr["year"][0])
        self.combos = arr["combos"]
        self.month = arr["month"].astype(np.int16)
        self.actual = arr["actual_index"].astype(np.int16)
        self.amount = arr["amount"].astype(np.int64)
        self.model_p = arr["model_p"].astype(np.float64)
        self.market_p = arr["market_p"].astype(np.float64)
        self.odds = arr["odds"].astype(np.float64)
        if self.model_p.shape != self.market_p.shape or self.model_p.shape != self.odds.shape:
            raise ValueError(f"cache shape mismatch: {path}")
        if self.model_p.shape[1] != 120:
            raise ValueError(f"expected 120 combos: {path}")

    def mask_month(self, month: int) -> np.ndarray:
        return self.month == month


def load_caches(cache_dir: Path) -> dict[int, Cache]:
    caches: dict[int, Cache] = {}
    for year in (2023, 2024, 2025):
        path = cache_dir / f"signal_cache_{year}.npz"
        if not path.exists():
            raise FileNotFoundError(path)
        cache = Cache(path)
        if cache.year != year:
            raise ValueError(f"cache year mismatch: {path} -> {cache.year}")
        caches[year] = cache
    return caches


def fit_multipliers(model_p: np.ndarray, market_p: np.ndarray, actual: np.ndarray) -> dict[str, Any]:
    valid = (model_p > 0.0) & (market_p > 0.0)
    ratio = np.zeros_like(model_p, dtype=np.float64)
    ratio[valid] = np.log(model_p[valid] / market_p[valid])
    bin_id = np.digitize(ratio, BIN_EDGES[1:-1], right=False)
    bin_count = len(BIN_EDGES) - 1

    expected = np.bincount(
        bin_id[valid].ravel(),
        weights=market_p[valid].ravel(),
        minlength=bin_count,
    ).astype(np.float64)

    row_index = np.arange(len(actual))
    actual_valid = valid[row_index, actual]
    actual_bins = bin_id[row_index[actual_valid], actual[actual_valid]]
    observed = np.bincount(actual_bins, minlength=bin_count).astype(np.float64)

    multipliers = (observed + PRIOR_EXPECTED_WINS) / (expected + PRIOR_EXPECTED_WINS)
    multipliers = np.clip(multipliers, MULTIPLIER_MIN, MULTIPLIER_MAX)
    return {
        "multipliers": multipliers,
        "expected": expected,
        "observed": observed,
        "sampleRaces": int(len(actual)),
    }


def fixed_2023_calibration(cache: Cache) -> dict[str, Any]:
    mask = np.isin(cache.month, CALIBRATION_MONTHS)
    if int(mask.sum()) < 1000:
        raise RuntimeError("insufficient 2023 Feb-Apr calibration races")
    return fit_multipliers(cache.model_p[mask], cache.market_p[mask], cache.actual[mask])


def calibrate_month(cache: Cache, month: int, fit: dict[str, Any]) -> dict[str, np.ndarray]:
    mask = cache.mask_month(month)
    model_p = cache.model_p[mask]
    market_p = cache.market_p[mask]
    odds = cache.odds[mask]
    actual = cache.actual[mask]
    amount = cache.amount[mask]

    valid = (model_p > 0.0) & (market_p > 0.0) & (odds > 0.0)
    ratio = np.zeros_like(model_p, dtype=np.float64)
    ratio[valid] = np.log(model_p[valid] / market_p[valid])
    bin_id = np.digitize(ratio, BIN_EDGES[1:-1], right=False)

    weights = np.where(valid, market_p * fit["multipliers"][bin_id], 0.0)
    totals = weights.sum(axis=1, keepdims=True)
    calibrated = np.divide(weights, totals, out=np.zeros_like(weights), where=totals > 0.0)
    ev = calibrated * odds
    order = np.argsort(-ev, axis=1)

    return {
        "p": np.take_along_axis(calibrated, order, axis=1),
        "ev": np.take_along_axis(ev, order, axis=1),
        "odds": np.take_along_axis(odds, order, axis=1),
        "combo_index": order,
        "actual": actual,
        "amount": amount,
    }


def prepare_operation(caches: dict[int, Cache], fit: dict[str, Any]) -> dict[int, dict[int, dict[str, np.ndarray]]]:
    prepared: dict[int, dict[int, dict[str, np.ndarray]]] = {}
    for year in (2023, 2024, 2025):
        prepared[year] = {}
        for month in OPERATION_MONTHS:
            prepared[year][month] = calibrate_month(caches[year], month, fit)
            print(f"prepared {year}-{month:02d}", flush=True)
    return prepared


def config_grid() -> list[dict[str, Any]]:
    return [
        {
            "minEv": min_ev,
            "minProbability": min_prob,
            "maxOdds": max_odds,
            "maxPoints": points,
            "allocationMode": "equal",
            "budget": BUDGET,
        }
        for min_ev in MIN_EV_OPTIONS
        for min_prob in MIN_PROB_OPTIONS
        for max_odds in MAX_ODDS_OPTIONS
        for points in POINT_OPTIONS
    ]


def finalize(purchase_races: int, hits: int, stake: int, payout: int, bets: int) -> dict[str, Any]:
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
    }


def combine(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return finalize(
        sum(int(row["purchaseRaces"]) for row in rows),
        sum(int(row["hits"]) for row in rows),
        sum(int(row["stake"]) for row in rows),
        sum(int(row["payout"]) for row in rows),
        sum(int(row["bets"]) for row in rows),
    )


def evaluate_month(prepared: dict[str, np.ndarray], cfg: dict[str, Any]) -> dict[str, Any]:
    p = prepared["p"]
    ev = prepared["ev"]
    odds = prepared["odds"]
    order = prepared["combo_index"]
    actual = prepared["actual"]
    amount = prepared["amount"]

    eligible = (
        (ev >= float(cfg["minEv"]))
        & (p >= float(cfg["minProbability"]))
        & (odds <= float(cfg["maxOdds"]))
        & (odds > 0.0)
    )
    rank = np.cumsum(eligible, axis=1)
    take = eligible & (rank <= int(cfg["maxPoints"]))
    point_count = take.sum(axis=1).astype(np.int64)
    buy = point_count > 0
    purchase_races = int(buy.sum())
    if purchase_races == 0:
        return finalize(0, 0, 0, 0, 0)

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
    actual_units = (units * actual_match).sum(axis=1)
    hits = int((actual_units > 0).sum())
    payout = int(np.sum(amount * actual_units))
    stake = purchase_races * BUDGET
    bets = int(point_count[buy].sum())
    return finalize(purchase_races, hits, stake, payout, bets)


def profitable(row: dict[str, Any]) -> bool:
    return int(row["purchaseRaces"]) > 0 and int(row["profit"]) > 0


def design_score(monthly: dict[int, dict[str, Any]], total: dict[str, Any]) -> tuple[Any, ...]:
    values = [monthly[m] for m in OPERATION_MONTHS]
    valid = sum(int(row["purchaseRaces"]) >= DESIGN_MIN_MONTH_BUYS for row in values)
    positive = sum(profitable(row) for row in values)
    worst = min((float(row["roi"]) for row in values if int(row["purchaseRaces"]) > 0), default=0.0)
    return (valid, positive, worst, float(total["roi"]), int(total["purchaseRaces"]))


def evaluate_year(prepared_year: dict[int, dict[str, np.ndarray]], cfg: dict[str, Any]):
    monthly = {month: evaluate_month(prepared_year[month], cfg) for month in OPERATION_MONTHS}
    return monthly, combine(list(monthly.values()))


def research_metrics(monthly: dict[int, dict[str, Any]], total: dict[str, Any]) -> dict[str, Any]:
    positive = sum(profitable(row) for row in monthly.values())
    worst = min((float(row["roi"]) for row in monthly.values()), default=0.0)
    volume_ok = all(int(row["purchaseRaces"]) >= RESEARCH_MIN_MONTH_BUYS for row in monthly.values())
    target = bool(
        int(total["purchaseRaces"]) >= RESEARCH_MIN_TOTAL_BUYS
        and float(total["roi"]) >= RESEARCH_MIN_ROI
        and positive >= RESEARCH_MIN_POSITIVE_MONTHS
        and worst >= RESEARCH_MIN_WORST_ROI
        and volume_ok
    )
    return {
        "positiveMonths": positive,
        "worstMonthRoi": worst,
        "volumeOk": volume_ok,
        "researchTargetMet": target,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    caches = load_caches(args.cache_dir)
    fit = fixed_2023_calibration(caches[2023])
    prepared = prepare_operation(caches, fit)

    ranked: list[tuple[tuple[Any, ...], dict[str, Any], dict[int, dict[str, Any]], dict[str, Any]]] = []
    grid = config_grid()
    for idx, cfg in enumerate(grid):
        monthly, total = evaluate_year(prepared[2023], cfg)
        if int(total["purchaseRaces"]) < DESIGN_MIN_TOTAL_BUYS:
            continue
        score = design_score(monthly, total)
        if int(score[0]) < len(OPERATION_MONTHS):
            continue
        ranked.append((score, cfg, monthly, total))
        if (idx + 1) % 50 == 0:
            print(f"searched {idx + 1}/{len(grid)}", flush=True)
    if not ranked:
        raise RuntimeError("no v14 design config met 2023 volume guards")
    ranked.sort(key=lambda item: item[0], reverse=True)
    design_score_value, selected_cfg, design_monthly, design_total = ranked[0]

    year_results: list[dict[str, Any]] = []
    for year in (2023, 2024, 2025):
        if year == 2023:
            monthly, total = design_monthly, design_total
        else:
            monthly, total = evaluate_year(prepared[year], selected_cfg)
        metrics = research_metrics(monthly, total)
        result = {
            "year": year,
            "role": "ticket-design" if year == 2023 else "fully-frozen evaluation",
            "months": {f"{year}-{month:02d}": monthly[month] for month in OPERATION_MONTHS},
            "total": total,
            **metrics,
        }
        year_results.append(result)
        print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)

    evaluation_years = [row for row in year_results if row["year"] in (2024, 2025)]
    evaluation_total = combine([row["total"] for row in evaluation_years])
    evaluation_both_positive = all(float(row["total"]["roi"]) > 100.0 for row in evaluation_years)
    evaluation_targets = sum(bool(row["researchTargetMet"]) for row in evaluation_years)

    output = {
        "schemaVersion": 14,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "researchOnly": True,
        "releaseQualified": False,
        "method": "2023 Feb-Apr fixed empirical model/market calibration + 2023 May-Sep ticket design + fully frozen 2024-2025 evaluation",
        "fixedCalibration": {
            "sourcePeriod": "2023-02-01..2023-04-30",
            "sampleRaces": fit["sampleRaces"],
            "binEdges": [None if not math.isfinite(float(v)) else float(v) for v in BIN_EDGES],
            "priorExpectedWins": PRIOR_EXPECTED_WINS,
            "multiplierMin": MULTIPLIER_MIN,
            "multiplierMax": MULTIPLIER_MAX,
            "multipliers": [round(float(v), 6) for v in fit["multipliers"]],
            "expectedWins": [round(float(v), 3) for v in fit["expected"]],
            "observedWins": [int(v) for v in fit["observed"]],
        },
        "selectedTicketConfig": selected_cfg,
        "design2023": {
            "sourcePeriod": "2023-05-01..2023-09-30",
            "score": list(design_score_value),
            "gridCount": len(grid),
        },
        "yearResults": year_results,
        "evaluation2024to2025": {
            "combined": evaluation_total,
            "bothYearsPositive": evaluation_both_positive,
            "yearsMeetingResearchTarget": evaluation_targets,
        },
        "holdoutPolicy": {
            "reserved": "2025-10-01..2025-12-31",
            "opened": False,
            "rule": "Do not evaluate until calibration and ticket config are frozen and 2024/2025 evaluation is satisfactory.",
        },
        "policy": {
            "calibration": "fit once on 2023 Feb-Apr and frozen thereafter",
            "ticketThresholds": "searched on 2023 May-Sep only and frozen thereafter",
            "laterYears": "2024/2025 receive no calibration or ticket retuning",
            "developmentStatus": "2023-2025 were inspected by prior experiments, so results are not pristine holdout proof",
            "release": "this research file can never unlock release by itself",
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps({
        "fixedCalibrationMultipliers": output["fixedCalibration"]["multipliers"],
        "selectedTicketConfig": selected_cfg,
        "design2023": design_total,
        "evaluation2024to2025": output["evaluation2024to2025"],
        "holdoutOpened": False,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
