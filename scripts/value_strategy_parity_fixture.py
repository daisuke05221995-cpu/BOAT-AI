#!/usr/bin/env python3
"""Reproduce the synthetic Python reference used by Android ValueStrategyModelTest.

This fixture covers feature rows, conditional ordering, blended market probability,
ticket selection, and non-equal 1,200-yen stake allocation without historical data.
"""
import json
import math

import numpy as np

import search_2026_strategy as v6
import search_2026_strategy_v9 as v9
from build_2026_backtest import LearningProfile


def section(length: int, phase: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.zeros(length),
        np.ones(length),
        np.array([math.sin((index + 1) * 0.61 + phase) * 0.28 for index in range(length)]),
    )


def main() -> None:
    model = v6.ConditionalPositionModel(*section(32, 0.3), *section(50, 0.7), *section(65, 1.1))
    racers = []
    for lane in range(1, 7):
        racers.append({
            "lane": lane,
            "national_win": 4.6 + 0.32 * lane,
            "local_win": 5.8 - 0.13 * lane,
            "motor_top2": 28.0 + 3.4 * lane,
            "boat_top2": 33.0 + 2.1 * lane,
            "average_start": 0.12 + 0.013 * lane,
            "exhibition": 6.7 + 0.035 * lane,
            "preview_start": 0.1 + 0.012 * lane,
            "course": 3 if lane == 2 else 2 if lane == 3 else lane,
        })
    learning = LearningProfile({})
    features = [v6.feature_row(racer, 1, 4, 3, learning) for racer in racers]
    distribution = v9.full_distribution(model, {"features": features})
    odds = {
        combo: float(68 + ((int(combo[0]) * 17 + int(combo[2]) * 11 + int(combo[4]) * 7) % 81))
        for combo, _ in distribution
    }
    market_sum = sum(1.0 / odd for odd in odds.values())
    signal = {
        "combo": "1-2-3",
        "amount": 1000,
        "items": [(combo, p, (1.0 / odds[combo]) / market_sum, odds[combo]) for combo, p in distribution],
    }
    config = {"minEv": 1.05, "minProbability": 0.005, "maxOdds": 150.0}
    picks = v9.filter_items(v9.prepare_signal(signal, 0.25), config, limit=4)
    units = v9.allocate_units(picks, "probability")
    assert len(picks) == 4 and sum(units) == 12
    print(json.dumps([
        {"combination": combo, "expectedValue": ev, "stake": unit * 100}
        for (combo, _, _, ev), unit in zip(picks, units)
    ], indent=2))


if __name__ == "__main__":
    main()
