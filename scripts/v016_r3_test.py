#!/usr/bin/env python3
"""Fail-closed guards for preregistered CORE r3 walk-forward research.

These tests deliberately do not score ROI.  They lock chronology and the final
2025-Q4 holdout boundary before any r3 trainer/evaluator is allowed to run.
"""
import json
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "data" / "v016_r3_protocol.json"
FINAL_HOLDOUT_START = date(2025, 10, 1)
FINAL_HOLDOUT_END = date(2025, 12, 31)


def d(value: str) -> date:
    return date.fromisoformat(value)


def assert_training_boundary(train_dates, eval_start):
    if not train_dates:
        raise ValueError("training set is empty")
    if max(map(d, train_dates)) >= d(eval_start):
        raise ValueError("chronology violation: training reaches evaluation period")


def assert_eval_allowed(start: str, end: str):
    lo, hi = d(start), d(end)
    if lo > hi:
        raise ValueError("invalid evaluation interval")
    if not (hi < FINAL_HOLDOUT_START or lo > FINAL_HOLDOUT_END):
        raise ValueError("SEALED_FINAL_HOLDOUT")


def assert_complete_quarter(required_dates, available_dates):
    missing = set(required_dates) - set(available_dates)
    if missing:
        raise ValueError("INCOMPLETE_QUARTER")


def test_protocol():
    p = json.loads(PROTOCOL.read_text())
    assert p["holdout"]["state"] == "SEALED"
    assert p["holdout"]["final"] == "2025-10-01..2025-12-31"
    assert p["inherits"]["betting_policy"] == {
        "budget_yen": 1200, "max_points": 3, "min_ev": 1.10,
        "min_probability": 0.01, "max_odds": 40.0,
    }
    for key, q in p["chronology"].items():
        if not isinstance(q, dict):
            continue
        assert d(q["train_end"]) < d(q["eval"][0]), key
        assert_eval_allowed(*q["eval"])


def test_guards():
    assert_training_boundary(["2024-01-01", "2024-03-31"], "2024-04-01")
    try:
        assert_training_boundary(["2024-04-01"], "2024-04-01")
        raise AssertionError("same-day training leak was accepted")
    except ValueError as e:
        assert "chronology violation" in str(e)
    try:
        assert_eval_allowed("2025-09-30", "2025-10-01")
        raise AssertionError("final holdout access was accepted")
    except ValueError as e:
        assert str(e) == "SEALED_FINAL_HOLDOUT"
    try:
        assert_complete_quarter(["a", "b"], ["a"])
        raise AssertionError("missing data was treated as zero-purchase")
    except ValueError as e:
        assert str(e) == "INCOMPLETE_QUARTER"


if __name__ == "__main__":
    test_protocol()
    test_guards()
    print("CORE r3 chronology guards: PASS")
