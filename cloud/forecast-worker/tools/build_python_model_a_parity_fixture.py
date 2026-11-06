#!/usr/bin/env python3
"""Independent Python/LightGBM golden output for frozen Model A.

Synthetic features only; no races, dates, outcomes, market odds, history state,
2025 holdouts, or model tuning. Requires pinned lightgbm==4.6.0 and NumPy.
"""

import hashlib
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
from v016_r2_model import COMBOS, PREFIXES, context, rows, softmax  # noqa: E402


def json_number(number):
    number = float(number)
    return number if np.isfinite(number) else None


def main():
    if lgb.__version__ != "4.6.0":
        raise RuntimeError(f"Pinned LightGBM version required: got {lgb.__version__}")

    rng = np.random.default_rng(0xB0A7A1)
    n = 4
    boat = rng.normal(loc=1.5, scale=2.5, size=(n, 6, 82)).astype(np.float32)
    boat[:, :, 0] = rng.uniform(3.0, 9.0, size=(n, 6))
    boat[:, :, 15] = rng.uniform(6.4, 7.3, size=(n, 6))
    boat[:, :, 16] = rng.uniform(-0.1, 0.25, size=(n, 6))
    for case in range(n):
        boat[case, :, 17] = np.roll(np.arange(1, 7), case)
    missing = rng.random(boat.shape) < 0.025
    missing[:, :, [0, 15, 16, 17]] = False
    boat[missing] = np.nan

    global_features = rng.normal(loc=0.2, scale=1.4, size=(n, 24)).astype(np.float32)
    venue = np.array([1, 7, 18, 24], dtype=int)
    race_number = np.array([1, 6, 10, 12], dtype=int)
    global_features[:, 22] = venue
    global_features[:, 23] = race_number
    c = {
        "boat": boat,
        "global_features": global_features,
        "venue": venue,
        "race_number": race_number,
        # Python context() constructs market features even for the
        # fundamental (market-free) family. These are unused by rows().
        "market_p": np.full((n, 120), 1.0 / 120.0, dtype=np.float32),
    }
    ctx = context(c)

    model_files = [ROOT / "app" / "src" / "main" / "assets" / f"model_a_stage{s}.txt" for s in range(3)]
    models = [lgb.Booster(model_file=str(path)) for path in model_files]
    for stage, model in enumerate(models):
        if model.num_feature() != [545, 715, 885][stage]:
            raise RuntimeError(f"Unexpected frozen stage width {stage}: {model.num_feature()}")

    q = []
    for stage in range(3):
        prefixes = PREFIXES[stage]
        race = np.repeat(np.arange(n), len(prefixes))
        prefix = np.tile(prefixes, (n, 1))
        x, base, candidates = rows(ctx, race, prefix, "fundamental")
        if not np.array_equal(base, np.zeros_like(base)):
            raise RuntimeError("Frozen fundamental model unexpectedly consumes market")
        scores = models[stage].predict(x, raw_score=True, num_threads=2)
        prob = softmax(scores.reshape(-1, 6 - stage))
        table = np.zeros((n,) + (6,) * (stage + 1), np.float64)
        indices = [np.repeat(race, 6 - stage)]
        indices.extend(np.repeat(prefix[:, s], 6 - stage) for s in range(stage))
        indices.append(candidates.ravel())
        table[tuple(indices)] = prob.ravel()
        q.append(table)

    chain = q[0][:, COMBOS[:, 0]] * q[1][:, COMBOS[:, 0], COMBOS[:, 1]] * q[2][
        :, COMBOS[:, 0], COMBOS[:, 1], COMBOS[:, 2]
    ]
    if not np.allclose(chain.sum(axis=1), 1.0, atol=1e-10):
        raise RuntimeError("Golden chain failed probability mass check")
    if not np.isfinite(chain).all():
        raise RuntimeError("Golden chain contained NaN/Inf")

    fixture = {
        "schema_version": 1,
        "source": "Python v016_r2_model.py + LightGBM 4.6.0, fundamental market-free family",
        "temperature": 1.0,
        "model_sha256": {
            f"stage{s}": hashlib.sha256(path.read_bytes()).hexdigest()
            for s, path in enumerate(model_files)
        },
        "cases": [
            {
                "input": {
                    "boat": [[json_number(value) for value in row] for row in boat[i]],
                    "global": [json_number(value) for value in global_features[i]],
                    "venue": int(venue[i]),
                    "raceNumber": int(race_number[i]),
                },
                "probabilities": [float(value) for value in chain[i]],
            }
            for i in range(n)
        ],
    }
    target = ROOT / "cloud" / "forecast-worker" / "test" / "fixtures" / "python-model-a-parity.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(fixture, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"Wrote {n} golden 120-way forecasts to {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
