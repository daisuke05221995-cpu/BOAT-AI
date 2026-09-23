#!/usr/bin/env python3
"""Export the selected walk-forward value model for the Android app.

The exporter refuses to publish an asset unless the latest strategy search is marked
qualifiedForRelease. Model parameters are trained only through dataThrough, so the
asset can be used for races after that date with the selected nextLiveConfig.
"""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

import search_2026_strategy_v9 as v9
from build_2026_backtest import LearningProfile


def floats(values: Any) -> list[float]:
    return [float(value) for value in values.tolist()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--strategy", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    strategy = json.loads(args.strategy.read_text(encoding="utf-8"))
    if int(strategy.get("schemaVersion", 0)) < 11:
        raise SystemExit("strategy schema 11+ is required")
    if strategy.get("qualifiedForRelease") is not True:
        raise SystemExit("strategy is not qualified for release")
    config = strategy.get("nextLiveConfig")
    if not isinstance(config, dict):
        raise SystemExit("nextLiveConfig is missing")

    trained_through = date.fromisoformat(str(strategy["dataThrough"]))
    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    records, errors = v9.build_records(date(2026, 1, 1), trained_through, learning, args.workers)
    if errors:
        raise SystemExit(f"race download failures: {errors}")

    model = v9.v6.fit_conditional_model(records, date(2026, 1, 1), trained_through)
    payload = {
        "schemaVersion": 1,
        "trainedFrom": "2026-01-01",
        "trainedThrough": trained_through.isoformat(),
        "strategySourceSchema": int(strategy["schemaVersion"]),
        "strategy": config,
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
            "The model is a frozen snapshot and should be refreshed by the training workflow as new settled data accumulates.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "trainedThrough": payload["trainedThrough"],
        "strategy": config,
        "featureSpec": payload["featureSpec"],
        "recordCount": len(records),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
