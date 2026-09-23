#!/usr/bin/env python3
"""Export the selected walk-forward value model for the Android app.

The exporter is intentionally release-gated. A 2026 development result alone is not
sufficient: the committed independent 2023-2025 validation must also pass the frozen
strict criteria. Model parameters are trained only through strategy.dataThrough.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import search_2026_strategy_v9 as v9
from build_2026_backtest import LearningProfile

EXPECTED_VALIDATION_YEARS = [2023, 2024, 2025]


def floats(values: Any) -> list[float]:
    return [float(value) for value in values.tolist()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--strategy", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    strategy = json.loads(args.strategy.read_text(encoding="utf-8"))
    if int(strategy.get("schemaVersion", 0)) < 12:
        raise SystemExit("strategy schema 12+ is required")
    if strategy.get("historicalCriteriaMet") is not True:
        raise SystemExit("2026 development criteria are not met")

    validation = json.loads(args.validation.read_text(encoding="utf-8"))
    if int(validation.get("schemaVersion", 0)) < 1:
        raise SystemExit("independent validation schema is invalid")
    if validation.get("validationYears") != EXPECTED_VALIDATION_YEARS:
        raise SystemExit(
            f"independent validation must cover exactly {EXPECTED_VALIDATION_YEARS}"
        )
    if validation.get("independentValidationPassed") is not True:
        raise SystemExit("independent multi-year validation has not passed")
    if validation.get("releaseCandidate") is not True:
        raise SystemExit("independent validation does not mark this strategy as a release candidate")
    if int(validation.get("yearsMeetingStrictCriteria", 0)) != len(EXPECTED_VALIDATION_YEARS):
        raise SystemExit("not every independent year meets the strict release criteria")
    if validation.get("development2026CriteriaMet") is not True:
        raise SystemExit("validation summary does not confirm the 2026 development criteria")

    year_results = validation.get("yearResults")
    if not isinstance(year_results, list) or len(year_results) != len(EXPECTED_VALIDATION_YEARS):
        raise SystemExit("independent year results are missing")
    for expected_year, item in zip(EXPECTED_VALIDATION_YEARS, year_results):
        if not isinstance(item, dict) or int(item.get("targetYear", 0)) != expected_year:
            raise SystemExit("independent year result order/content is invalid")
        if item.get("historicalCriteriaMet") is not True:
            raise SystemExit(f"independent year {expected_year} did not pass")

    config = strategy.get("nextLiveConfig")
    if not isinstance(config, dict):
        raise SystemExit("nextLiveConfig is missing")

    trained_through = date.fromisoformat(str(strategy["dataThrough"]))
    learning_json = json.loads(args.learning.read_text(encoding="utf-8"))
    if learning_json.get("trainedThrough") != "2025-12-31":
        raise SystemExit("production model learning snapshot must end at 2025-12-31")
    learning = LearningProfile(learning_json)
    records, errors = v9.build_records(date(2026, 1, 1), trained_through, learning, args.workers)
    if errors:
        raise SystemExit(f"race download failures: {errors}")

    model = v9.v6.fit_conditional_model(records, date(2026, 1, 1), trained_through)
    combined_validation = validation.get("combined") or {}
    payload = {
        "schemaVersion": 2,
        "trainedFrom": "2026-01-01",
        "trainedThrough": trained_through.isoformat(),
        "strategySourceSchema": int(strategy["schemaVersion"]),
        "strategy": config,
        "validation": {
            "schemaVersion": int(validation["schemaVersion"]),
            "years": EXPECTED_VALIDATION_YEARS,
            "independentValidationPassed": True,
            "combinedRoi": combined_validation.get("roi"),
            "combinedProfit": combined_validation.get("profit"),
            "yearsMeetingStrictCriteria": int(validation["yearsMeetingStrictCriteria"]),
        },
        "featureSpec": {
            "baseFeatureCount": len(model.first_mean),
            "secondFeatureCount": len(model.second_mean),
            "thirdFeatureCount": len(model.third_mean),
        },
        "first": {
            "mean": floats(model.first_mean),
            "std": floats(model.first_std),
            "weights": floats(model.first_weights),
        },
        "second": {
            "mean": floats(model.second_mean),
            "std": floats(model.second_std),
            "weights": floats(model.second_weights),
        },
        "third": {
            "mean": floats(model.third_mean),
            "std": floats(model.third_std),
            "weights": floats(model.third_weights),
        },
        "notes": [
            "Production odds must come from official BOAT RACE pages.",
            "Historical archive odds are not bundled into the Android app.",
            "The strategy passed the committed independent 2023-2025 validation before export.",
            "The model is a frozen snapshot and should be refreshed only through a leakage-safe validated workflow.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "trainedThrough": payload["trainedThrough"],
        "strategy": config,
        "validation": payload["validation"],
        "featureSpec": payload["featureSpec"],
        "recordCount": len(records),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
