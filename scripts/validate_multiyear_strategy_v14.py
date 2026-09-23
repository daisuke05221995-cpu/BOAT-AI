#!/usr/bin/env python3
"""BOAT AI v14 research: empirical AI-vs-market edge calibration.

Research-only walk-forward evaluator for 2023-2025.

Protocol:
- each target-year model is trained only through the previous month;
- archived trifecta odds are converted to normalized market probabilities;
- the AI/market probability ratio is grouped into coarse, fixed bins;
- prior months estimate realized lift versus market expectation with shrinkage toward 1.0;
- those lifts calibrate the next month's 120-combo distribution;
- ticket thresholds are selected once from Feb-Apr and frozen for May-Sep;
- May-Sep outcomes never change ticket thresholds, only the probability calibrator receives
  prior-month outcomes before the next month starts;
- 2023-2025 are development data and cannot unlock release by themselves.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import search_2026_strategy_v9 as v9
from build_kfile_validation_records import build_records_from_kfiles

CALIBRATION_MONTHS = (2, 3, 4)
OPERATION_MONTHS = (5, 6, 7, 8, 9)
ALL_MONTHS = CALIBRATION_MONTHS + OPERATION_MONTHS

# Coarse fixed bins avoid fitting arbitrary breakpoints to the development years.
RATIO_EDGES = (0.0, 0.60, 0.80, 1.00, 1.25, 1.50, 2.00, 3.00, float("inf"))
PRIOR_EXPECTED_HITS = 25.0
MIN_LIFT = 0.50
MAX_LIFT = 1.50

MIN_EV_OPTIONS = (1.02, 1.05, 1.08, 1.10, 1.15, 1.20, 1.30)
MIN_PROB_OPTIONS = (0.005, 0.010, 0.020)
MAX_ODDS_OPTIONS = (20.0, 40.0, 80.0, 150.0)
POINT_OPTIONS = (1, 2, 3, 4)
ALLOCATION_MODES = ("equal", "probability")

MIN_CAL_VALID_MONTHS = 2
MIN_CAL_MONTH_BUYS = 20
MIN_CAL_TOTAL_BUYS = 80
MIN_OPERATION_MONTH_BUYS = 40
MIN_OPERATION_TOTAL_BUYS = 300
RESEARCH_TARGET_ROI = 105.0
RESEARCH_TARGET_POSITIVE_MONTHS = 4
RESEARCH_TARGET_WORST_ROI = 90.0


def month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def fetch_archived_odds(year: int, workers: int) -> tuple[dict[date, dict[tuple[int, int], dict[str, float]]], dict[str, str]]:
    original = v9.ODDS_URL
    v9.ODDS_URL = f"https://raw.githubusercontent.com/lamrongol/BoatraceOdds/gh-pages/docs/v3/{year}/{{day}}.json"
    try:
        return v9.fetch_odds_range(date(year, 2, 1), date(year, 9, 30), workers)
    finally:
        v9.ODDS_URL = original


def build_month_signals(*, year: int, records: list[dict[str, Any]], odds_by_day: dict[date, dict[tuple[int, int], dict[str, float]]]) -> tuple[dict[int, list[dict[str, Any]]], dict[int, int]]:
    signals: dict[int, list[dict[str, Any]]] = {}
    missing: dict[int, int] = {}
    for month in ALL_MONTHS:
        model = v9.v6.fit_conditional_model(records, date(year, 1, 1), month_end(year, month - 1))
        rows, absent = v9.make_signals(
            model,
            records,
            date(year, month, 1),
            month_end(year, month),
            odds_by_day,
        )
        signals[month] = rows
        missing[month] = absent
        print(f"{year}-{month:02d}: signals={len(rows)} missing={absent}", flush=True)
    return signals, missing


def first_lane_group(combo: str) -> str:
    try:
        first = int(str(combo).split("-")[0])
    except (TypeError, ValueError):
        return "other"
    if first == 1:
        return "lane1"
    if first in (2, 3):
        return "lane23"
    return "lane456"


def ratio_bucket(model_p: float, market_p: float) -> int:
    ratio = float(model_p) / max(float(market_p), 1e-12)
    for idx in range(len(RATIO_EDGES) - 1):
        if RATIO_EDGES[idx] <= ratio < RATIO_EDGES[idx + 1]:
            return idx
    return len(RATIO_EDGES) - 2


def bucket_key(combo: str, model_p: float, market_p: float) -> tuple[str, int]:
    return first_lane_group(combo), ratio_bucket(model_p, market_p)


def fit_lifts(signals_by_month: dict[int, list[dict[str, Any]]], history_months: list[int]) -> tuple[dict[tuple[str, int], float], dict[str, Any]]:
    stats: dict[tuple[str, int], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for month in history_months:
        for signal in signals_by_month[month]:
            actual = str(signal["combo"])
            for combo, model_p, market_p, _odd in signal["items"]:
                key = bucket_key(str(combo), float(model_p), float(market_p))
                row = stats[key]
                row[0] += 1.0 if str(combo) == actual else 0.0  # observed hits
                row[1] += float(market_p)  # expected hits under market
                row[2] += 1.0

    lifts: dict[tuple[str, int], float] = {}
    diagnostics: list[dict[str, Any]] = []
    for lane_group in ("lane1", "lane23", "lane456"):
        for bucket in range(len(RATIO_EDGES) - 1):
            observed, expected, count = stats.get((lane_group, bucket), [0.0, 0.0, 0.0])
            # This prior shrinks empirical lift toward 1.0 rather than toward zero.
            lift = (observed + PRIOR_EXPECTED_HITS) / (expected + PRIOR_EXPECTED_HITS)
            lift = max(MIN_LIFT, min(MAX_LIFT, lift))
            lifts[(lane_group, bucket)] = lift
            diagnostics.append({
                "laneGroup": lane_group,
                "ratioLow": RATIO_EDGES[bucket],
                "ratioHigh": None if math.isinf(RATIO_EDGES[bucket + 1]) else RATIO_EDGES[bucket + 1],
                "observedHits": round(observed, 3),
                "marketExpectedHits": round(expected, 3),
                "candidateCount": int(count),
                "lift": round(lift, 6),
            })
    return lifts, {
        "historyMonths": history_months,
        "priorExpectedHits": PRIOR_EXPECTED_HITS,
        "buckets": diagnostics,
    }


def prepare_signal(signal: dict[str, Any], lifts: dict[tuple[str, int], float]) -> dict[str, Any]:
    raw: list[tuple[str, float, float]] = []
    total = 0.0
    for combo, model_p, market_p, odd in signal["items"]:
        key = bucket_key(str(combo), float(model_p), float(market_p))
        lift = float(lifts.get(key, 1.0))
        weight = max(float(market_p), 1e-12) * lift
        raw.append((str(combo), weight, float(odd)))
        total += weight
    ranked: list[tuple[str, float, float, float]] = []
    if total > 0.0:
        for combo, weight, odd in raw:
            probability = weight / total
            ranked.append((combo, probability, odd, probability * odd))
        ranked.sort(key=lambda row: (row[3], row[1]), reverse=True)
    return {"combo": str(signal["combo"]), "amount": int(signal["amount"]), "ranked": ranked}


def build_walkforward_prepared(signals_by_month: dict[int, list[dict[str, Any]]]) -> tuple[dict[int, list[dict[str, Any]]], dict[int, dict[str, Any]]]:
    prepared: dict[int, list[dict[str, Any]]] = {}
    calibration_meta: dict[int, dict[str, Any]] = {}
    for month in ALL_MONTHS:
        history_months = list(range(2, month))
        lifts, meta = fit_lifts(signals_by_month, history_months)
        prepared[month] = [prepare_signal(signal, lifts) for signal in signals_by_month[month]]
        calibration_meta[month] = meta
        print(f"prepared month={month:02d} history={history_months}", flush=True)
    return prepared, calibration_meta


def ticket_grid() -> list[dict[str, Any]]:
    return [
        {
            "minEv": min_ev,
            "minProbability": min_prob,
            "maxOdds": max_odds,
            "maxPoints": points,
            "allocationMode": allocation,
            "budget": v9.BUDGET,
        }
        for min_ev in MIN_EV_OPTIONS
        for min_prob in MIN_PROB_OPTIONS
        for max_odds in MAX_ODDS_OPTIONS
        for points in POINT_OPTIONS
        for allocation in ALLOCATION_MODES
    ]


def select_fixed_ticket_config(prepared: dict[int, list[dict[str, Any]]]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    ranked: list[tuple[tuple[Any, ...], dict[str, Any], dict[int, dict[str, Any]], dict[str, Any]]] = []
    for cfg in ticket_grid():
        monthly: dict[int, dict[str, Any]] = {}
        for month in CALIBRATION_MONTHS:
            key = f"cal-{month:02d}"
            result, _ = v9.evaluate_prepared({key: prepared[month]}, cfg)
            monthly[month] = result[key]
        total = v9.combine(list(monthly.values()))
        valid = sum(int(row["purchaseRaces"]) >= MIN_CAL_MONTH_BUYS for row in monthly.values())
        if valid < MIN_CAL_VALID_MONTHS or int(total["purchaseRaces"]) < MIN_CAL_TOTAL_BUYS:
            continue
        positive = sum(v9.profitable(row) for row in monthly.values())
        active_rois = [float(row["roi"]) for row in monthly.values() if int(row["purchaseRaces"]) > 0]
        worst = min(active_rois, default=0.0)
        score = (
            positive,
            worst,
            float(total["roi"]),
            -abs(int(total["purchaseRaces"]) - 400),
        )
        ranked.append((score, cfg, monthly, total))

    if not ranked:
        return None, {"eligibleConfigCount": 0, "gridCount": len(ticket_grid())}
    ranked.sort(key=lambda row: row[0], reverse=True)
    score, cfg, monthly, total = ranked[0]
    return cfg, {
        "eligibleConfigCount": len(ranked),
        "gridCount": len(ticket_grid()),
        "score": list(score),
        "monthly": {f"m{month:02d}": stats for month, stats in monthly.items()},
        "total": total,
    }


def no_bet_stats() -> dict[str, Any]:
    return v9.finalize(v9.empty_stats())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    year = int(args.year)
    if year not in (2023, 2024, 2025):
        raise SystemExit("v14 archived-odds research currently supports 2023-2025")

    learning_json = json.loads(args.learning.read_text(encoding="utf-8"))
    expected_through = f"{year - 1}-12-31"
    if learning_json.get("trainedThrough") != expected_through:
        raise SystemExit(f"learning leakage guard: expected {expected_through}, got {learning_json.get('trainedThrough')}")
    if learning_json.get("snapshotComplete") is not True:
        raise SystemExit("learning snapshot is not marked complete")

    records, record_source = build_records_from_kfiles(year=year, learning_json=learning_json, workers=args.workers)
    if float(record_source.get("programMetricCoverage", 0.0)) < 90.0:
        raise SystemExit(f"program metric coverage too low: {record_source}")

    odds_by_day, odds_errors = fetch_archived_odds(year, args.workers)
    if odds_errors:
        raise SystemExit(f"odds download failures: {odds_errors}")

    signals_by_month, missing = build_month_signals(year=year, records=records, odds_by_day=odds_by_day)
    if any(len(signals_by_month[month]) < 500 for month in ALL_MONTHS):
        raise SystemExit("insufficient odds-matched signals")

    prepared, calibration_meta = build_walkforward_prepared(signals_by_month)
    fixed_cfg, ticket_meta = select_fixed_ticket_config(prepared)

    operation: dict[str, dict[str, Any]] = {}
    if fixed_cfg is None:
        for month in OPERATION_MONTHS:
            operation[f"m{month:02d}"] = no_bet_stats()
    else:
        for month in OPERATION_MONTHS:
            key = f"m{month:02d}"
            result, _ = v9.evaluate_prepared({key: prepared[month]}, fixed_cfg)
            operation[key] = result[key]
            print(
                f"operation month={month:02d} roi={operation[key]['roi']} "
                f"buys={operation[key]['purchaseRaces']}",
                flush=True,
            )

    operation_total = v9.combine(list(operation.values()))
    positive_months = sum(v9.profitable(row) for row in operation.values())
    worst_roi = min((float(row["roi"]) for row in operation.values() if int(row["purchaseRaces"]) > 0), default=0.0)
    all_months_have_volume = all(int(row["purchaseRaces"]) >= MIN_OPERATION_MONTH_BUYS for row in operation.values())
    research_target_met = bool(
        fixed_cfg is not None
        and int(operation_total["purchaseRaces"]) >= MIN_OPERATION_TOTAL_BUYS
        and float(operation_total["roi"]) >= RESEARCH_TARGET_ROI
        and positive_months >= RESEARCH_TARGET_POSITIVE_MONTHS
        and worst_roi >= RESEARCH_TARGET_WORST_ROI
        and all_months_have_volume
    )

    result = {
        "schemaVersion": 14,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "targetYear": year,
        "researchOnly": True,
        "releaseQualified": False,
        "learningTrainedThrough": learning_json.get("trainedThrough"),
        "method": "v14 market-prior empirical AI/market ratio lift calibration with shrinkage",
        "recordSource": record_source,
        "fixedTicketConfig": fixed_cfg,
        "fixedTicketCalibration": ticket_meta,
        "calibrationByTargetMonth": {f"m{month:02d}": calibration_meta[month] for month in ALL_MONTHS},
        "operationMonths": operation,
        "operation": operation_total,
        "positiveOperationMonths": positive_months,
        "worstOperationMonthRoi": worst_roi,
        "researchTargetMet": research_target_met,
        "oddsCoverage": {
            "daysLoaded": len(odds_by_day),
            "signalCounts": {f"m{month:02d}": len(signals_by_month[month]) for month in ALL_MONTHS},
            "missingRaces": {f"m{month:02d}": missing[month] for month in ALL_MONTHS},
        },
        "policy": {
            "probabilityCalibration": "market probability multiplied by prior-month empirical lift of fixed AI/market ratio and first-lane buckets",
            "shrinkage": f"lift=(observed+{PRIOR_EXPECTED_HITS})/(marketExpected+{PRIOR_EXPECTED_HITS}), capped {MIN_LIFT}-{MAX_LIFT}",
            "ticketThresholdSelection": "selected once from walk-forward Feb-Apr prepared probabilities then frozen through May-Sep",
            "developmentStatus": "2023-2025 are development data because previous experiments already inspected them",
        },
        "researchRule": (
            "May-Sep combined ROI >=105%, >=4/5 positive months, worst active month ROI >=90%, "
            ">=40 buys/month and >=300 total buys. Passing is research evidence only, not release approval."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "targetYear": year,
        "fixedTicketConfig": fixed_cfg,
        "operationMonths": operation,
        "operation": operation_total,
        "positiveOperationMonths": positive_months,
        "worstOperationMonthRoi": worst_roi,
        "researchTargetMet": research_target_met,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
