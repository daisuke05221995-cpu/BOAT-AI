"""Build immutable, research-only exhibition CSV features for a future Model B.

No race result, payout, odds, Model A weight, or video-derived claim is used.
Only records actually retrieved before the race cutoff are eligible.  This is
feature preparation, NOT model training or a current Android prediction.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path

TIME_FEATURES = ("lap_time_s", "half_lap_time_s", "turn_time_s", "straight_time_s")
EXTRA_FEATURES = ("exhibition_time_s", "exhibition_st", "tilt")
OUTPUT_VERSION = "public_exhibition_features_v1"


class UnusablePreview(ValueError):
    pass


def _time(raw: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise UnusablePreview("invalid provenance time") from exc
    if value.tzinfo is None or value.utcoffset() is None:
        raise UnusablePreview("provenance time lacks timezone")
    return value


def _number(raw) -> float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not math.isfinite(raw):
        raise UnusablePreview("unexpected numeric feature")
    return float(raw)


def build_features(record: dict) -> dict:
    """Convert a validated snapshot into six boat-relative numeric observations.

    Missing values remain null. Mean-centering removes cross-venue differences
    without fitted parameters or knowledge of subsequent race outcomes.
    """
    if (record.get("schema_version") != 1 or record.get("data_kind") != "published_numeric_exhibition_not_video_ai"
            or record.get("source") != "boatracecsv_public_preview" or record.get("status") != "PRE_CLOSE_OBSERVED"
            or record.get("forecast_input_allowed") is not False or record.get("purchase_decision_allowed") is not False):
        raise UnusablePreview("requires an explicitly research-only, pre-close public preview")
    race = record.get("race")
    if not isinstance(race, dict):
        raise UnusablePreview("race missing")
    deadline = _time(race.get("deadline"))
    retrieved = _time(record.get("retrieved_at"))
    if retrieved >= deadline:
        raise UnusablePreview("record was fetched too late")
    if not isinstance(record.get("source_captured_at"), dict):
        raise UnusablePreview("source timestamps missing")
    captured = record["source_captured_at"]
    if not captured or not set(captured).issubset(set(record.get("sources_present", []))):
        raise UnusablePreview("no validated pre-close source evidence")
    for value in captured.values():
        if _time(value) >= deadline or _time(value) > retrieved:
            raise UnusablePreview("source snapshot was not observed before cutoff")
    boats = record.get("boats")
    if (not isinstance(boats, list) or len(boats) != 6 or any(not isinstance(b, dict) for b in boats)
            or {b.get("lane") for b in boats} != set(range(1, 7))):
        raise UnusablePreview("six unique boats required")
    boats = sorted(boats, key=lambda b: b["lane"])
    for boat in boats:
        if not isinstance(boat.get("original"), dict):
            raise UnusablePreview("original time evidence missing")
    courses = [boat.get("course") for boat in boats]
    if all(course is not None for course in courses) and set(courses) != set(range(1, 7)):
        raise UnusablePreview("exhibition course mapping is not a permutation")
    names = TIME_FEATURES + EXTRA_FEATURES
    measurements = {
        name: [_number(b["original"].get(name) if name in TIME_FEATURES else b.get(name)) for b in boats]
        for name in names
    }
    # A field is comparable across all six boats or entirely unavailable.
    relative = {}
    for name, values in measurements.items():
        if any(v is None for v in values):
            relative[name] = [None] * 6
        else:
            mean = sum(values) / 6
            relative[name] = [round(v - mean, 6) for v in values]
    output_boats = []
    for i, boat in enumerate(boats):
        course = boat.get("course")
        if course is not None and (isinstance(course, bool) or not isinstance(course, int) or not 1 <= course <= 6):
            raise UnusablePreview("invalid exhibition course")
        output_boats.append({
            "lane": boat["lane"],
            "course": course,
            "relative": {field: relative[field][i] for field in names},
            "present": {field: relative[field][i] is not None for field in names},
        })
    return {
        "schema_version": 1,
        "feature_version": OUTPUT_VERSION,
        "race": race,
        "retrieved_at": record["retrieved_at"],
        "data_kind": "published_exhibition_numerics_only",
        "model_trained": False,
        "forecast_input_allowed": False,
        "purchase_decision_allowed": False,
        "source_credit": record.get("source_credit"),
        "sources_present": record.get("sources_present", []),
        "weather": record.get("weather"),
        "boats": output_boats,
    }


def run(input_dir: Path, output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"inputs": 0, "eligible": 0, "rejected": 0, "no_original": 0, "fully_observed_original": 0}
    for path in sorted(input_dir.glob("*.json")):
        if not path.is_file():
            continue
        summary["inputs"] += 1
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            result = build_features(record)
        except (UnusablePreview, ValueError, TypeError, KeyError, json.JSONDecodeError):
            summary["rejected"] += 1
            continue
        summary["eligible"] += 1
        keys = ("lap_time_s", "half_lap_time_s", "turn_time_s", "straight_time_s")
        seen = [result["boats"][0]["present"][field] for field in keys]
        if not any(seen):
            summary["no_original"] += 1
        if sum(seen) >= 2:
            summary["fully_observed_original"] += 1
        (output_dir / path.name).write_text(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(run(args.input_dir, args.output_dir)))


if __name__ == "__main__":
    main()
