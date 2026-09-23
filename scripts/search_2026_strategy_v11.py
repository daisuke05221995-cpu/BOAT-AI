#!/usr/bin/env python3
"""Monthly adaptive odds-value walk-forward strategy.

For each operational month, the strategy configuration is selected only from earlier
walk-forward months. The target month's outcomes never participate in its config choice.
This mimics a live system that recalibrates monthly as market/model behaviour changes.

Calibration signals:
- Feb: model trained on Jan
- Mar: model trained through Feb
- Apr: model trained through Mar
Operational evaluation:
- May config selected from Feb-Apr
- Jun from Feb-May
- Jul from Feb-Jun
- Aug from Feb-Jul
- Sep from Feb-Aug
Current/next config is selected from Feb-Sep for live use after the test period.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import search_2026_strategy_v9 as v9
from build_2026_backtest import JST, LearningProfile

CALIBRATION_MONTHS = (2, 3, 4)
OPERATION_MONTHS = (5, 6, 7, 8, 9)
ALL_MONTHS = CALIBRATION_MONTHS + OPERATION_MONTHS
ALPHAS = (0.25, 0.35, 0.50, 0.65)
MIN_EV_OPTIONS = (1.05, 1.10, 1.20, 1.30)
MIN_PROB_OPTIONS = (0.005, 0.010)
MAX_ODDS_OPTIONS = (40.0, 80.0, 150.0)
POINT_OPTIONS = (1, 2, 3, 4, 6, 8, 10)
ALLOCATION_MODES = ("equal", "probability")
MIN_HISTORY_MONTH_BUYS = 20
MIN_HISTORY_TOTAL_BUYS = 100
MIN_OPERATION_MONTH_BUYS = 50
MIN_OPERATION_TOTAL_BUYS = 500
RELEASE_MIN_ROI = 105.0
RELEASE_MIN_POSITIVE_MONTHS = 4
RELEASE_MIN_WORST_ROI = 90.0


def config_grid() -> list[dict[str, Any]]:
    return [
        {
            "alpha": alpha,
            "minEv": min_ev,
            "minProbability": min_prob,
            "maxOdds": max_odds,
            "maxPoints": points,
            "allocationMode": mode,
            "budget": v9.BUDGET,
        }
        for alpha in ALPHAS
        for min_ev in MIN_EV_OPTIONS
        for min_prob in MIN_PROB_OPTIONS
        for max_odds in MAX_ODDS_OPTIONS
        for points in POINT_OPTIONS
        for mode in ALLOCATION_MODES
    ]


def aggregate(stats_by_month: dict[str, dict[str, Any]], keys: list[str]) -> dict[str, Any]:
    return v9.combine([stats_by_month[key] for key in keys])


def selection_score(stats_by_month: dict[str, dict[str, Any]], history_keys: list[str]) -> tuple[Any, ...]:
    values = [stats_by_month[key] for key in history_keys]
    total = v9.combine(values)
    valid = sum(int(item["purchaseRaces"]) >= MIN_HISTORY_MONTH_BUYS for item in values)
    positive = sum(v9.profitable(item) for item in values)
    worst = min((float(item["roi"]) for item in values if int(item["purchaseRaces"]) > 0), default=0.0)
    return (valid, positive, worst, float(total["roi"]), int(total["purchaseRaces"]))


def choose_config(
    configs: list[dict[str, Any]],
    monthly_cache: dict[int, dict[int, dict[str, Any]]],
    history_keys: list[str],
) -> tuple[int, dict[str, Any], tuple[Any, ...]]:
    ranked: list[tuple[tuple[Any, ...], int]] = []
    for idx, _cfg in enumerate(configs):
        stats_by_month = {month: monthly_cache[idx][int(month[-2:])] for month in history_keys}
        score = selection_score(stats_by_month, history_keys)
        total_buys = int(score[4])
        all_valid = int(score[0]) == len(history_keys)
        if not all_valid or total_buys < MIN_HISTORY_TOTAL_BUYS:
            continue
        ranked.append((score, idx))
    if not ranked:
        for idx, _cfg in enumerate(configs):
            stats_by_month = {month: monthly_cache[idx][int(month[-2:])] for month in history_keys}
            ranked.append((selection_score(stats_by_month, history_keys), idx))
    ranked.sort(key=lambda item: item[0], reverse=True)
    score, idx = ranked[0]
    return idx, configs[idx], score


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
        raise SystemExit("September operational period has not started")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    records, race_errors = v9.build_records(args.start, data_end, learning, args.workers)
    if race_errors:
        raise SystemExit(f"race download failures: {race_errors}")

    odds_by_day, odds_errors = v9.fetch_odds_range(date(2026, 2, 1), data_end, args.workers)
    if odds_errors:
        raise SystemExit(f"odds download failures: {odds_errors}")

    signals, missing = v9.build_month_signals(records, odds_by_day, ALL_MONTHS)
    signal_counts = {key: len(value) for key, value in signals.items()}
    if any(signal_counts.get(f"2026-{month:02d}", 0) < 500 for month in ALL_MONTHS):
        raise RuntimeError(f"insufficient odds-matched signals: {signal_counts}")

    configs = config_grid()
    # Prepare blended probabilities once per alpha/month, then evaluate every config.
    prepared: dict[float, dict[int, list[dict[str, Any]]]] = {}
    for alpha in ALPHAS:
        prepared[alpha] = {
            month: [v9.prepare_signal(signal, alpha) for signal in signals[f"2026-{month:02d}"]]
            for month in ALL_MONTHS
        }
        print(f"alpha={alpha:.2f} prepared", flush=True)

    monthly_cache: dict[int, dict[int, dict[str, Any]]] = {}
    for idx, cfg in enumerate(configs):
        alpha = float(cfg["alpha"])
        monthly_cache[idx] = {}
        for month in ALL_MONTHS:
            month_key = f"2026-{month:02d}"
            monthly, _ = v9.evaluate_prepared({month_key: prepared[alpha][month]}, cfg)
            monthly_cache[idx][month] = monthly[month_key]
        if (idx + 1) % 100 == 0:
            print(f"evaluated {idx + 1}/{len(configs)} configs", flush=True)

    operation: dict[str, dict[str, Any]] = {}
    monthly_configs: dict[str, dict[str, Any]] = {}
    monthly_selection_scores: dict[str, list[Any]] = {}

    for target_month in OPERATION_MONTHS:
        target_key = f"2026-{target_month:02d}"
        history_months = list(range(2, target_month))
        history_keys = [f"2026-{month:02d}" for month in history_months]
        idx, cfg, score = choose_config(configs, monthly_cache, history_keys)
        operation[target_key] = monthly_cache[idx][target_month]
        monthly_configs[target_key] = cfg
        monthly_selection_scores[target_key] = list(score)
        print(
            f"{target_key} cfg={cfg} result={operation[target_key]}",
            flush=True,
        )

    operation_total = v9.combine(list(operation.values()))
    positive_months = sum(v9.profitable(stats) for stats in operation.values())
    worst_roi = min(float(stats["roi"]) for stats in operation.values())
    all_months_have_volume = all(
        int(stats["purchaseRaces"]) >= MIN_OPERATION_MONTH_BUYS
        for stats in operation.values()
    )
    qualified_for_release = bool(
        int(operation_total["purchaseRaces"]) >= MIN_OPERATION_TOTAL_BUYS
        and float(operation_total["roi"]) >= RELEASE_MIN_ROI
        and positive_months >= RELEASE_MIN_POSITIVE_MONTHS
        and worst_roi >= RELEASE_MIN_WORST_ROI
        and all_months_have_volume
    )

    # Choose the next live config solely from all results available through September.
    all_history_keys = [f"2026-{month:02d}" for month in ALL_MONTHS]
    next_idx, next_config, next_score = choose_config(configs, monthly_cache, all_history_keys)
    next_history = {
        key: monthly_cache[next_idx][int(key[-2:])]
        for key in all_history_keys
    }

    result = {
        "schemaVersion": 11,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "monthly adaptive walk-forward conditional finish-order model + archived trifecta odds; each target month config selected only from prior months",
        "oddsFinalGateIncluded": True,
        "oddsSource": "lamrongol/BoatraceOdds v3 archive (production continues to use official BOAT RACE odds)",
        "periods": {
            "calibration": ["2026-02-01", "2026-04-30"],
            "operation": ["2026-05-01", data_end.isoformat()],
        },
        "monthlyConfigs": monthly_configs,
        "monthlySelectionScores": monthly_selection_scores,
        "operationMonths": operation,
        "operation": operation_total,
        "positiveOperationMonths": positive_months,
        "worstOperationMonthRoi": worst_roi,
        "qualifiedForRelease": qualified_for_release,
        "nextLiveConfig": next_config,
        "nextLiveSelectionScore": list(next_score),
        "nextLiveHistory": next_history,
        "oddsCoverage": {
            "daysLoaded": len(odds_by_day),
            "signals": signal_counts,
            "missingRaces": missing,
        },
        "searchSpace": {
            "configCount": len(configs),
            "alpha": list(ALPHAS),
            "minEv": list(MIN_EV_OPTIONS),
            "minProbability": list(MIN_PROB_OPTIONS),
            "maxOdds": list(MAX_ODDS_OPTIONS),
            "maxPoints": list(POINT_OPTIONS),
            "allocationMode": list(ALLOCATION_MODES),
        },
        "releaseRule": "May-Sep monthly adaptive walk-forward: combined ROI >=105%, >=4/5 positive months, worst month >=90%, >=50 buys/month and >=500 total buys",
        "notes": [
            "Each operational month is evaluated with a configuration selected before that month from prior-month results only.",
            "The same search rule is reused every month; target-month outcomes never choose their own parameters.",
            "Historical odds are archived snapshots and may differ from the exact live purchase second.",
            "Production app continues to fetch official BOAT RACE odds.",
            "Repeated research iterations mean this is a historical walk-forward validation, not a guarantee of future profitability.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "operationMonths": operation,
        "operation": operation_total,
        "positiveOperationMonths": positive_months,
        "worstOperationMonthRoi": worst_roi,
        "qualifiedForRelease": qualified_for_release,
        "nextLiveConfig": next_config,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
