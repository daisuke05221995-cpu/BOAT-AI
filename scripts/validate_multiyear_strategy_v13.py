#!/usr/bin/env python3
"""BOAT AI v13 research: probability-calibrated value strategy.

This is a research-only walk-forward evaluator for 2023-2025.

Key differences from v12:
- alpha (AI-vs-market blend) is selected ONLY by predictive log-loss, never by ROI;
- ticket/value thresholds are selected once from Feb-Apr and frozen for May-Sep;
- May-Sep outcomes never change ticket thresholds;
- alpha may be re-calibrated before each operation month using only earlier months;
- target-year model training remains leakage-safe and uses official B/K archives;
- archived trifecta odds are used as pre-race market information.

Because 2023-2025 have already been inspected during development, results from this
script are development evidence and MUST NOT be labelled independent holdout proof.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import search_2026_strategy_v9 as v9
from build_kfile_validation_records import build_records_from_kfiles

CALIBRATION_MONTHS = (2, 3, 4)
OPERATION_MONTHS = (5, 6, 7, 8, 9)
ALL_MONTHS = CALIBRATION_MONTHS + OPERATION_MONTHS

# Include alpha=0.0 so the market-only probability baseline can win calibration.
ALPHAS = (0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.65)
MIN_EV_OPTIONS = (1.02, 1.05, 1.10, 1.15, 1.20, 1.30, 1.50)
MIN_PROB_OPTIONS = (0.005, 0.010, 0.020)
MAX_ODDS_OPTIONS = (20.0, 40.0, 80.0, 150.0)
POINT_OPTIONS = (1, 2, 3, 4)
ALLOCATION_MODES = ("equal", "probability")

MIN_CAL_MONTH_BUYS = 20
MIN_CAL_TOTAL_BUYS = 100
MIN_OPERATION_MONTH_BUYS = 40
MIN_OPERATION_TOTAL_BUYS = 300
RESEARCH_TARGET_ROI = 105.0
RESEARCH_TARGET_POSITIVE_MONTHS = 4
RESEARCH_TARGET_WORST_ROI = 90.0


def month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


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


def fetch_archived_odds(year: int, workers: int) -> tuple[dict[date, dict[tuple[int, int], dict[str, float]]], dict[str, str]]:
    original = v9.ODDS_URL
    v9.ODDS_URL = (
        f"https://raw.githubusercontent.com/lamrongol/BoatraceOdds/gh-pages/docs/v3/{year}/{{day}}.json"
    )
    try:
        return v9.fetch_odds_range(date(year, 2, 1), date(year, 9, 30), workers)
    finally:
        v9.ODDS_URL = original


def build_month_signals(
    *,
    year: int,
    records: list[dict[str, Any]],
    odds_by_day: dict[date, dict[tuple[int, int], dict[str, float]]],
) -> tuple[dict[int, list[dict[str, Any]]], dict[int, int]]:
    signals: dict[int, list[dict[str, Any]]] = {}
    missing: dict[int, int] = {}
    for month in ALL_MONTHS:
        model = v9.v6.fit_conditional_model(
            records,
            date(year, 1, 1),
            month_end(year, month - 1),
        )
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


def blended_actual_probability(signal: dict[str, Any], alpha: float) -> float | None:
    denom = 0.0
    actual_weight: float | None = None
    actual = str(signal["combo"])
    for combo, model_p, market_p, _odd in signal["items"]:
        value = math.exp(
            alpha * math.log(max(float(model_p), 1e-12))
            + (1.0 - alpha) * math.log(max(float(market_p), 1e-12))
        )
        denom += value
        if str(combo) == actual:
            actual_weight = value
    if denom <= 0.0 or actual_weight is None:
        return None
    return max(actual_weight / denom, 1e-12)


def log_loss(signals: list[dict[str, Any]], alpha: float) -> tuple[float, int]:
    total = 0.0
    count = 0
    for signal in signals:
        probability = blended_actual_probability(signal, alpha)
        if probability is None:
            continue
        total -= math.log(probability)
        count += 1
    return (total / count if count else float("inf"), count)


def choose_alpha(
    signals_by_month: dict[int, list[dict[str, Any]]],
    history_months: list[int],
) -> tuple[float, dict[str, Any]]:
    rows: list[tuple[float, float, int]] = []
    history = [signal for month in history_months for signal in signals_by_month[month]]
    for alpha in ALPHAS:
        loss, count = log_loss(history, alpha)
        rows.append((loss, alpha, count))
    rows.sort(key=lambda item: (item[0], item[1]))
    loss, alpha, count = rows[0]
    return alpha, {
        "historyMonths": history_months,
        "selectedAlpha": alpha,
        "logLoss": round(loss, 6),
        "sampleCount": count,
        "candidates": [
            {"alpha": a, "logLoss": round(l, 6), "sampleCount": c}
            for l, a, c in rows
        ],
    }


def calibration_score(monthly: dict[int, dict[str, Any]], total: dict[str, Any]) -> tuple[Any, ...]:
    values = [monthly[m] for m in CALIBRATION_MONTHS]
    valid = sum(int(row["purchaseRaces"]) >= MIN_CAL_MONTH_BUYS for row in values)
    positive = sum(v9.profitable(row) for row in values)
    worst = min((float(row["roi"]) for row in values if int(row["purchaseRaces"]) > 0), default=0.0)
    return (
        valid,
        positive,
        worst,
        float(total["roi"]),
        -abs(int(total["purchaseRaces"]) - 600),
    )


def select_fixed_ticket_config(
    signals_by_month: dict[int, list[dict[str, Any]]],
    calibration_alpha: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    prepared = {
        month: [v9.prepare_signal(signal, calibration_alpha) for signal in signals_by_month[month]]
        for month in CALIBRATION_MONTHS
    }
    ranked: list[tuple[tuple[Any, ...], dict[str, Any], dict[int, dict[str, Any]], dict[str, Any]]] = []
    for cfg in ticket_grid():
        monthly: dict[int, dict[str, Any]] = {}
        for month in CALIBRATION_MONTHS:
            key = f"cal-{month:02d}"
            month_stats, _ = v9.evaluate_prepared({key: prepared[month]}, cfg)
            monthly[month] = month_stats[key]
        total = v9.combine(list(monthly.values()))
        if int(total["purchaseRaces"]) < MIN_CAL_TOTAL_BUYS:
            continue
        ranked.append((calibration_score(monthly, total), cfg, monthly, total))

    if not ranked:
        raise RuntimeError("no v13 ticket configuration met calibration-volume guard")
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, cfg, monthly, total = ranked[0]
    return cfg, {
        "score": list(score),
        "monthly": {f"m{month:02d}": stats for month, stats in monthly.items()},
        "total": total,
        "gridCount": len(ticket_grid()),
    }


def evaluate_operation(
    *,
    signals_by_month: dict[int, list[dict[str, Any]]],
    fixed_cfg: dict[str, Any],
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    operation: dict[str, dict[str, Any]] = {}
    alpha_history: list[dict[str, Any]] = []
    for target_month in OPERATION_MONTHS:
        history_months = list(range(2, target_month))
        alpha, alpha_meta = choose_alpha(signals_by_month, history_months)
        key = f"m{target_month:02d}"
        prepared = [v9.prepare_signal(signal, alpha) for signal in signals_by_month[target_month]]
        stats, _ = v9.evaluate_prepared({key: prepared}, fixed_cfg)
        operation[key] = stats[key]
        alpha_meta["targetMonth"] = target_month
        alpha_history.append(alpha_meta)
        print(
            f"operation month={target_month:02d} alpha={alpha:.2f} "
            f"roi={operation[key]['roi']} buys={operation[key]['purchaseRaces']}",
            flush=True,
        )
    return operation, alpha_history


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    year = int(args.year)
    if year not in (2023, 2024, 2025):
        raise SystemExit("v13 archived-odds research currently supports 2023-2025")

    learning_json = json.loads(args.learning.read_text(encoding="utf-8"))
    expected_through = f"{year - 1}-12-31"
    if learning_json.get("trainedThrough") != expected_through:
        raise SystemExit(
            f"learning leakage guard: expected trainedThrough={expected_through}, "
            f"got {learning_json.get('trainedThrough')}"
        )
    if learning_json.get("snapshotComplete") is not True:
        raise SystemExit("learning snapshot is not marked complete")

    records, record_source = build_records_from_kfiles(
        year=year,
        learning_json=learning_json,
        workers=args.workers,
    )
    if float(record_source.get("programMetricCoverage", 0.0)) < 90.0:
        raise SystemExit(f"program metric coverage too low: {record_source}")

    odds_by_day, odds_errors = fetch_archived_odds(year, args.workers)
    if odds_errors:
        raise SystemExit(f"odds download failures: {odds_errors}")

    signals_by_month, missing = build_month_signals(
        year=year,
        records=records,
        odds_by_day=odds_by_day,
    )
    if any(len(signals_by_month[month]) < 500 for month in ALL_MONTHS):
        raise SystemExit(
            "insufficient odds-matched signals: "
            + json.dumps({month: len(signals_by_month[month]) for month in ALL_MONTHS})
        )

    calibration_alpha, calibration_alpha_meta = choose_alpha(
        signals_by_month,
        list(CALIBRATION_MONTHS),
    )
    fixed_cfg, config_meta = select_fixed_ticket_config(signals_by_month, calibration_alpha)
    operation, alpha_history = evaluate_operation(
        signals_by_month=signals_by_month,
        fixed_cfg=fixed_cfg,
    )

    operation_total = v9.combine(list(operation.values()))
    positive_months = sum(v9.profitable(row) for row in operation.values())
    worst_roi = min(float(row["roi"]) for row in operation.values())
    all_months_have_volume = all(
        int(row["purchaseRaces"]) >= MIN_OPERATION_MONTH_BUYS
        for row in operation.values()
    )
    research_target_met = bool(
        int(operation_total["purchaseRaces"]) >= MIN_OPERATION_TOTAL_BUYS
        and float(operation_total["roi"]) >= RESEARCH_TARGET_ROI
        and positive_months >= RESEARCH_TARGET_POSITIVE_MONTHS
        and worst_roi >= RESEARCH_TARGET_WORST_ROI
        and all_months_have_volume
    )

    result = {
        "schemaVersion": 13,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "targetYear": year,
        "researchOnly": True,
        "releaseQualified": False,
        "learningTrainedThrough": learning_json.get("trainedThrough"),
        "method": "v13 fixed ticket thresholds + log-loss-only monthly AI/market calibration",
        "recordSource": record_source,
        "calibrationAlpha": calibration_alpha_meta,
        "fixedTicketConfig": fixed_cfg,
        "fixedTicketCalibration": config_meta,
        "operationAlphaHistory": alpha_history,
        "operationMonths": operation,
        "operation": operation_total,
        "positiveOperationMonths": positive_months,
        "worstOperationMonthRoi": worst_roi,
        "researchTargetMet": research_target_met,
        "oddsCoverage": {
            "daysLoaded": len(odds_by_day),
            "signalCounts": {f"m{m:02d}": len(signals_by_month[m]) for m in ALL_MONTHS},
            "missingRaces": {f"m{m:02d}": missing[m] for m in ALL_MONTHS},
        },
        "policy": {
            "ticketThresholdSelection": "selected once from Feb-Apr then frozen through May-Sep",
            "alphaSelection": "minimum log-loss only; ROI never participates in alpha selection",
            "operationAdaptation": "before each month, alpha may use outcomes from earlier months only",
            "developmentStatus": "2023-2025 are development data because previous experiments already inspected them",
        },
        "researchRule": (
            "May-Sep combined ROI >=105%, >=4/5 positive months, worst month ROI >=90%, "
            ">=40 buys/month and >=300 total buys. Passing is research evidence only, not release approval."
        ),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps({
        "targetYear": year,
        "calibrationAlpha": calibration_alpha,
        "fixedTicketConfig": fixed_cfg,
        "operationMonths": operation,
        "operation": operation_total,
        "positiveOperationMonths": positive_months,
        "worstOperationMonthRoi": worst_roi,
        "researchTargetMet": research_target_met,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
