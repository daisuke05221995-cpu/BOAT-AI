#!/usr/bin/env python3
"""Generate deterministic raw-score parity fixtures for frozen v0.16 Model A.

This script never reads race outcomes, odds, September/Q4 data, or production state.
It exercises the exact serialized LightGBM trees with deterministic numeric rows,
including missing values, so Kotlin tree traversal can be compared against
LightGBM 4.6.0 at scale.
"""
import argparse
import json
from pathlib import Path

import lightgbm as lgb
import numpy as np


def write_fixture(path: Path, x: np.ndarray, expected: np.ndarray) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row, score in zip(x, expected):
            values = ["NaN" if np.isnan(v) else format(float(v), ".17g") for v in row]
            values.append(format(float(score), ".17g"))
            f.write(",".join(values) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=1024)
    args = parser.parse_args()

    if lgb.__version__ != "4.6.0":
        raise RuntimeError(f"Pinned LightGBM 4.6.0 required, got {lgb.__version__}")
    if args.rows < 256:
        raise ValueError("Parity fixture must contain at least 256 rows per stage")

    manifest = json.loads((args.model_dir / "manifest.json").read_text())
    if manifest.get("variant") != "reaction":
        raise ValueError("Expected frozen reaction Model A")
    if manifest.get("temperature") != 1.0:
        raise ValueError("Frozen Model A temperature drift")
    if manifest.get("marketInOutcomeModel") is not False:
        raise ValueError("Market input unexpectedly enabled")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"lightgbmVersion": lgb.__version__, "rowsPerStage": args.rows, "stages": {}}

    for stage in range(3):
        model_path = args.model_dir / f"stage{stage}.txt"
        booster = lgb.Booster(model_file=str(model_path))
        features = int(booster.num_feature())
        expected_features = int(manifest["stages"][str(stage)]["features"])
        if features != expected_features:
            raise ValueError(f"stage {stage}: feature count drift {features} != {expected_features}")

        rng = np.random.default_rng(160400 + stage)
        x = rng.normal(0.0, 2.0, size=(args.rows, features)).astype(np.float64)

        # Exercise common feature regimes: indicators, non-negative counts, wide values,
        # zeros and LightGBM missing-value routing. These rows are deliberately synthetic
        # and exist only to verify serialized-tree evaluator parity.
        if features > 8:
            x[:, ::11] = rng.integers(0, 2, size=x[:, ::11].shape)
            x[:, 3::17] = np.abs(x[:, 3::17]) * 50.0
            x[:, 5::23] = 0.0
            x[:, 7::29] *= 10.0
        missing = rng.random(x.shape) < 0.0125
        x[missing] = np.nan

        expected = booster.predict(x, raw_score=True)
        if expected.ndim != 1 or len(expected) != args.rows or not np.isfinite(expected).all():
            raise ValueError(f"stage {stage}: invalid LightGBM output")

        fixture = args.output_dir / f"stage{stage}.csv"
        write_fixture(fixture, x, expected)
        (args.output_dir / f"stage{stage}.txt").write_bytes(model_path.read_bytes())
        summary["stages"][str(stage)] = {
            "features": features,
            "trees": int(booster.num_trees()),
            "fixture": fixture.name,
        }

    (args.output_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
