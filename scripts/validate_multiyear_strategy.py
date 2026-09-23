#!/usr/bin/env python3
"""Independent multi-year validation for the guarded BOAT AI value strategy.

Each target year is evaluated independently:
- the supplied learning snapshot must end on Dec 31 of the previous year;
- target-year model features are reconstructed from official BOAT RACE B/K files;
- target-race actual course/ST/result-time weather are excluded from its own features;
- each monthly conditional model is trained only through the previous month;
- archived trifecta odds for the target year are used as pre-race market information;
- May-Sep configurations are selected only from prior months using the same v12 guard.

This script does not tune the v12 guard thresholds and never uses 2026 outcomes to
select a target-year configuration.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import search_2026_strategy_v9 as v9
import search_2026_strategy_v11 as v11
from build_kfile_validation_records import build_records_from_kfiles

CALIBRATION_MONTHS = (2, 3, 4)
OPERATION_MONTHS = (5, 6, 7, 8, 9)
ALL_MONTHS = CALIBRATION_MONTHS + OPERATION_MONTHS

MIN_COMBINED_ROI_GAIN = 5.0
MAX_WORST_ROI_DROP = 3.0
MIN_VOLUME_RETENTION = 0.60
MAX_POSITIVE_MONTH_DROP = 0

MIN_OPERATION_MONTH_BUYS = 50
MIN_OPERATION_TOTAL_BUYS = 500
RELEASE_MIN_ROI = 105.0
RELEASE_MIN_POSITIVE_MONTHS = 4
RELEASE_MIN_WORST_ROI = 90.0


def month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def score_for(
    idx: int,
    monthly_cache: dict[int, dict[int, dict[str, Any]]],
    history_keys: list[str],
) -> tuple[Any, ...]:
    stats = {key: monthly_cache[idx][int(key[-2:])] for key in history_keys}
    return v11.selection_score(stats, history_keys)


def guarded_choose(
    *,
    target_label: str,
    configs: list[dict[str, Any]],
    monthly_cache: dict[int, dict[int, dict[str, Any]]],
    history_keys: list[str],
    incumbent_idx: int | None,
) -> tuple[int, dict[str, Any], tuple[Any, ...], dict[str, Any]]:
    candidate_idx, candidate_cfg, candidate_score = v11.choose_config(
        configs, monthly_cache, history_keys
    )
    if incumbent_idx is None:
        return candidate_idx, candidate_cfg, candidate_score, {
            "target": target_label,
            "action": "initial",
            "selectedIndex": candidate_idx,
            "selectedConfig": candidate_cfg,
            "selectedScore": list(candidate_score),
        }

    incumbent_score = score_for(incumbent_idx, monthly_cache, history_keys)
    if candidate_idx == incumbent_idx:
        return incumbent_idx, configs[incumbent_idx], incumbent_score, {
            "target": target_label,
            "action": "keep_same",
            "selectedIndex": incumbent_idx,
            "selectedConfig": configs[incumbent_idx],
            "selectedScore": list(incumbent_score),
        }

    candidate_roi = float(candidate_score[3])
    incumbent_roi = float(incumbent_score[3])
    candidate_worst = float(candidate_score[2])
    incumbent_worst = float(incumbent_score[2])
    candidate_buys = int(candidate_score[4])
    incumbent_buys = int(incumbent_score[4])

    roi_gain = candidate_roi - incumbent_roi
    worst_drop = incumbent_worst - candidate_worst
    volume_retention = candidate_buys / max(1, incumbent_buys)
    positive_drop = int(incumbent_score[1]) - int(candidate_score[1])

    allowed = bool(
        roi_gain >= MIN_COMBINED_ROI_GAIN
        and worst_drop <= MAX_WORST_ROI_DROP
        and volume_retention >= MIN_VOLUME_RETENTION
        and positive_drop <= MAX_POSITIVE_MONTH_DROP
    )
    selected_idx = candidate_idx if allowed else incumbent_idx
    selected_score = candidate_score if allowed else incumbent_score
    return selected_idx, configs[selected_idx], selected_score, {
        "target": target_label,
        "action": "switch" if allowed else "hold_incumbent",
        "candidateIndex": candidate_idx,
        "incumbentIndex": incumbent_idx,
        "candidateScore": list(candidate_score),
        "incumbentScore": list(incumbent_score),
        "roiGain": round(roi_gain, 3),
        "worstRoiDrop": round(worst_drop, 3),
        "volumeRetention": round(volume_retention, 4),
        "positiveMonthDrop": positive_drop,
        "selectedIndex": selected_idx,
        "selectedConfig": configs[selected_idx],
        "selectedScore": list(selected_score),
    }


def build_month_signals(
    *,
    year: int,
    records: list[dict[str, Any]],
    odds_by_day: dict[date, dict[tuple[int, int], dict[str, float]]],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    signals_by_month: dict[str, list[dict[str, Any]]] = {}
    missing: dict[str, int] = {}
    for month in ALL_MONTHS:
        previous_end = month_end(year, month - 1)
        model = v9.v6.fit_conditional_model(records, date(year, 1, 1), previous_end)
        key = f"{year}-{month:02d}"
        signals, absent = v9.make_signals(
            model,
            records,
            date(year, month, 1),
            month_end(year, month),
            odds_by_day,
        )
        signals_by_month[key] = signals
        missing[key] = absent
        print(f"{key}: signals={len(signals)} missing={absent}", flush=True)
    return signals_by_month, missing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=12)
    args = parser.parse_args()

    year = int(args.year)
    if year < 2023 or year > 2025:
        raise SystemExit("independent archived-odds validation currently supports 2023-2025")

    learning_json = json.loads(args.learning.read_text(encoding="utf-8"))
    expected_through = date(year - 1, 12, 31).isoformat()
    if learning_json.get("trainedThrough") != expected_through:
        raise SystemExit(
            f"learning leakage guard: expected trainedThrough={expected_through}, "
            f"got {learning_json.get('trainedThrough')}"
        )
    if learning_json.get("snapshotComplete") is not True:
        raise SystemExit("learning snapshot is not marked complete")
    if not learning_json.get("racerStartTimingCount"):
        raise SystemExit("learning snapshot has no racer start-timing seed")

    start = date(year, 1, 1)
    end = date(year, 9, 30)
    records, record_source = build_records_from_kfiles(
        year=year,
        learning_json=learning_json,
        workers=args.workers,
    )
    print(json.dumps({"recordSource": record_source}, ensure_ascii=False, indent=2), flush=True)

    original_odds_url = v9.ODDS_URL
    v9.ODDS_URL = (
        f"https://raw.githubusercontent.com/lamrongol/BoatraceOdds/gh-pages/docs/v3/{year}/{{day}}.json"
    )
    try:
        odds_by_day, odds_errors = v9.fetch_odds_range(date(year, 2, 1), end, args.workers)
    finally:
        v9.ODDS_URL = original_odds_url
    if odds_errors:
        raise SystemExit(f"odds download failures: {odds_errors}")

    signals, missing = build_month_signals(year=year, records=records, odds_by_day=odds_by_day)
    signal_counts = {key: len(value) for key, value in signals.items()}
    if any(signal_counts.get(f"{year}-{month:02d}", 0) < 500 for month in ALL_MONTHS):
        raise RuntimeError(f"insufficient odds-matched signals: {signal_counts}")

    configs = v11.config_grid()
    prepared: dict[float, dict[int, list[dict[str, Any]]]] = {}
    for alpha in v11.ALPHAS:
        prepared[alpha] = {
            month: [v9.prepare_signal(signal, alpha) for signal in signals[f"{year}-{month:02d}"]]
            for month in ALL_MONTHS
        }
        print(f"alpha={alpha:.2f} prepared", flush=True)

    monthly_cache: dict[int, dict[int, dict[str, Any]]] = {}
    for idx, cfg in enumerate(configs):
        alpha = float(cfg["alpha"])
        monthly_cache[idx] = {}
        for month in ALL_MONTHS:
            key = f"{year}-{month:02d}"
            monthly, _ = v9.evaluate_prepared({key: prepared[alpha][month]}, cfg)
            monthly_cache[idx][month] = monthly[key]
        if (idx + 1) % 100 == 0:
            print(f"evaluated {idx + 1}/{len(configs)} configs", flush=True)

    operation: dict[str, dict[str, Any]] = {}
    monthly_configs: dict[str, dict[str, Any]] = {}
    monthly_selection_scores: dict[str, list[Any]] = {}
    guard_decisions: list[dict[str, Any]] = []
    incumbent_idx: int | None = None

    for target_month in OPERATION_MONTHS:
        target_key = f"{year}-{target_month:02d}"
        history_keys = [f"{year}-{month:02d}" for month in range(2, target_month)]
        selected_idx, cfg, score, decision = guarded_choose(
            target_label=target_key,
            configs=configs,
            monthly_cache=monthly_cache,
            history_keys=history_keys,
            incumbent_idx=incumbent_idx,
        )
        incumbent_idx = selected_idx
        operation[target_key] = monthly_cache[selected_idx][target_month]
        monthly_configs[target_key] = cfg
        monthly_selection_scores[target_key] = list(score)
        guard_decisions.append(decision)
        print(f"{target_key} cfg={cfg} result={operation[target_key]}", flush=True)

    operation_total = v9.combine(list(operation.values()))
    positive_months = sum(v9.profitable(stats) for stats in operation.values())
    worst_roi = min(float(stats["roi"]) for stats in operation.values())
    all_months_have_volume = all(
        int(stats["purchaseRaces"]) >= MIN_OPERATION_MONTH_BUYS
        for stats in operation.values()
    )
    historical_criteria_met = bool(
        int(operation_total["purchaseRaces"]) >= MIN_OPERATION_TOTAL_BUYS
        and float(operation_total["roi"]) >= RELEASE_MIN_ROI
        and positive_months >= RELEASE_MIN_POSITIVE_MONTHS
        and worst_roi >= RELEASE_MIN_WORST_ROI
        and all_months_have_volume
    )

    result = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "targetYear": year,
        "learningTrainedFrom": learning_json.get("trainedFrom"),
        "learningTrainedThrough": learning_json.get("trainedThrough"),
        "method": "independent guarded monthly adaptive walk-forward conditional finish-order model + official B/K archives + archived trifecta odds",
        "featureLeakagePolicy": "current-race actual entrance/ST/result-time wind-wave are excluded; only settled earlier races may update them indirectly through historical aggregates",
        "recordSource": record_source,
        "periods": {
            "calibration": [f"{year}-02-01", f"{year}-04-30"],
            "operation": [f"{year}-05-01", f"{year}-09-30"],
        },
        "monthlyConfigs": monthly_configs,
        "monthlySelectionScores": monthly_selection_scores,
        "operationMonths": operation,
        "operation": operation_total,
        "positiveOperationMonths": positive_months,
        "worstOperationMonthRoi": worst_roi,
        "historicalCriteriaMet": historical_criteria_met,
        "guardPolicy": {
            "minCombinedRoiGain": MIN_COMBINED_ROI_GAIN,
            "maxWorstMonthRoiDrop": MAX_WORST_ROI_DROP,
            "minVolumeRetention": MIN_VOLUME_RETENTION,
            "maxPositiveMonthDrop": MAX_POSITIVE_MONTH_DROP,
        },
        "guardDecisions": guard_decisions,
        "oddsCoverage": {
            "daysLoaded": len(odds_by_day),
            "signals": signal_counts,
            "missingRaces": missing,
        },
        "searchSpace": {
            "configCount": len(configs),
            "alpha": list(v11.ALPHAS),
            "minEv": list(v11.MIN_EV_OPTIONS),
            "minProbability": list(v11.MIN_PROB_OPTIONS),
            "maxOdds": list(v11.MAX_ODDS_OPTIONS),
            "maxPoints": list(v11.POINT_OPTIONS),
            "allocationMode": list(v11.ALLOCATION_MODES),
        },
        "validationRule": (
            "Each independent year must have May-Sep combined ROI >=105%, >=4/5 positive months, "
            "worst month ROI >=90%, >=50 buys/month and >=500 total buys."
        ),
        "notes": [
            "The target year never uses a learning snapshot containing target-year or later results.",
            "Official B files supply national/local win rates and motor/boat top-2 rates.",
            "Official K exhibition time is retained because it was observable pre-race; actual K entrance/ST and race-time wind/wave are deliberately excluded from the same race's features.",
            "Average start is reconstructed from prior settled K races only, seeded through the previous Dec 31 and updated after each whole day.",
            "Monthly models use only target-year races settled before the month being predicted.",
            "Configuration selection for each target month uses only earlier months in the same target year.",
            "The v12 guard thresholds are frozen from the 2026 development iteration and are not tuned here.",
            "Archived odds may differ from the exact live purchase second; production uses official BOAT RACE odds.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "targetYear": year,
        "operationMonths": operation,
        "operation": operation_total,
        "positiveOperationMonths": positive_months,
        "worstOperationMonthRoi": worst_roi,
        "historicalCriteriaMet": historical_criteria_met,
        "recordSource": record_source,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
