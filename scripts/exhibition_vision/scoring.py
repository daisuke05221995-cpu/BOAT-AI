"""Score six calibrated exhibition-video measurement sets, fail closed.

Input measurements MUST be produced from licensed footage by a separate vision
detector and camera calibration stage.  The scores are within-race comparison
indices, NOT estimated winning probabilities or calibrated predictive effects.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
from typing import Any

METRIC_KEYS = (
    "exit_acceleration_mps2",    # 出足: acceleration after turn
    "runup_acceleration_mps2",   # 行き足: acceleration before turn
    "straight_speed_mps",        # 伸び足: calibrated straight speed
    "turn_speed_mps",            # 回り足: calibrated speed during turn
    "turn_time_s",               # Turn-performance component
    "turn_min_speed_retention",  # Turn-performance component
    "turn_marker_clearance_m",   # Turn-performance component
)
TRAITS = ("deashi", "yukiashi", "nobiashi", "mawariashi", "turn_performance")

# Minimum physically meaningful spread for provisional within-race scores.
# These are research settings, not learned thresholds or BUY gates.
SCALES = {
    "exit_acceleration_mps2": 0.8,
    "runup_acceleration_mps2": 0.8,
    "straight_speed_mps": 1.0,
    "turn_speed_mps": 1.0,
    "turn_time_s": 1.5,
    "turn_min_speed_retention": 0.2,
    "turn_marker_clearance_m": 1.5,
}
LOWER_IS_BETTER = {"turn_time_s", "turn_marker_clearance_m"}
MIN_TRACK_COVERAGE = 0.90
MIN_DETECTOR_CONFIDENCE = 0.85
MAX_CALIBRATION_ERROR_M = 1.0


class InvalidEvidence(ValueError):
    """The detector output cannot be safely interpreted."""


def _timestamp(value: Any, label: str) -> datetime:
    if not isinstance(value, str):
        raise InvalidEvidence(f"{label}: timestamp missing")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InvalidEvidence(f"{label}: invalid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise InvalidEvidence(f"{label}: timezone is required")
    return parsed


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InvalidEvidence(f"{label}: number missing")
    result = float(value)
    if not math.isfinite(result):
        raise InvalidEvidence(f"{label}: must be finite")
    return result


def _component_scores(values: list[float], key: str) -> list[float]:
    average = sum(values) / len(values)
    span = max(max(values) - min(values), SCALES[key])
    direction = -1 if key in LOWER_IS_BETTER else 1
    return [round(max(0.0, min(100.0, 50 + direction * 50 * (v - average) / span)), 2) for v in values]


def _competition_ranks(values: list[float]) -> list[int]:
    order = sorted(range(len(values)), key=lambda i: (-values[i], i))
    ranks = [0] * len(values)
    previous_value = None
    previous_rank = 0
    for position, index in enumerate(order, 1):
        # Roundoff of indices is not a meaningful competitive difference.
        if previous_value is None or abs(previous_value - values[index]) >= 0.1:
            previous_rank = position
        ranks[index] = previous_rank
        previous_value = values[index]
    return ranks


def _unusable(race: Any, reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "race": race,
        "status": "UNUSABLE",
        "reason": reason,
        "forecast_input_allowed": False,
        "purchase_decision_allowed": False,
        "boats": [],
    }


def evaluate_race(evidence: dict[str, Any]) -> dict[str, Any]:
    """Validate pre-race provenance/quality, then rank all six boats.

    Returns an empty, explicitly unusable result if evidence is incomplete.
    There is deliberately NO path into the app's production decision engine.
    """
    race = evidence.get("race")
    try:
        if evidence.get("schema_version") != 1 or not isinstance(race, dict):
            raise InvalidEvidence("unsupported schema or missing race")
        date = race.get("date")
        venue = race.get("venue")
        number = race.get("number")
        if not isinstance(date, str) or not (isinstance(venue, int) and 1 <= venue <= 24) or not (isinstance(number, int) and 1 <= number <= 12):
            raise InvalidEvidence("invalid race key")
        deadline = _timestamp(race.get("deadline"), "deadline")
        if deadline.date().isoformat() != date:
            raise InvalidEvidence("race date/deadline mismatch")
        capture = evidence.get("capture")
        if not isinstance(capture, dict):
            raise InvalidEvidence("capture provenance missing")
        if not capture.get("source_id") or not capture.get("permission_reference"):
            raise InvalidEvidence("authorized source/permission reference missing")
        if not capture.get("detector_version") or not capture.get("calibration_version"):
            raise InvalidEvidence("detector or metric calibration missing")
        digest = capture.get("video_sha256")
        if not isinstance(digest, str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise InvalidEvidence("video content hash missing")
        captured = _timestamp(capture.get("captured_at"), "captured_at")
        analyzed = _timestamp(capture.get("analyzed_at"), "analyzed_at")
        if captured > analyzed:
            raise InvalidEvidence("capture cannot follow analysis")
        if captured >= deadline:
            raise InvalidEvidence("post-deadline video: outcome leakage risk")
        boats = evidence.get("boats")
        if not isinstance(boats, list) or len(boats) != 6 or {b.get("lane") for b in boats if isinstance(b, dict)} != set(range(1, 7)):
            raise InvalidEvidence("exactly one tracked boat per lane 1..6 required")
        boats = sorted(boats, key=lambda b: b["lane"])
        for boat in boats:
            q = boat.get("quality")
            m = boat.get("measurements")
            if not isinstance(q, dict) or not isinstance(m, dict):
                raise InvalidEvidence(f"lane {boat['lane']}: quality or measurements missing")
            coverage = _number(q.get("track_coverage"), "track coverage")
            confidence = _number(q.get("detector_confidence"), "detector confidence")
            error = _number(q.get("calibration_error_m"), "calibration error")
            if coverage < MIN_TRACK_COVERAGE or not 0 <= coverage <= 1 or confidence < MIN_DETECTOR_CONFIDENCE or not 0 <= confidence <= 1 or not 0 <= error <= MAX_CALIBRATION_ERROR_M:
                raise InvalidEvidence(f"lane {boat['lane']}: video tracking quality below gate")
            for key in METRIC_KEYS:
                _number(m.get(key), f"lane {boat['lane']} {key}")
            if not (0 < m["turn_min_speed_retention"] <= 1):
                raise InvalidEvidence(f"lane {boat['lane']}: impossible turn speed retention")
            if m["turn_time_s"] <= 0 or m["turn_marker_clearance_m"] < 0 or m["straight_speed_mps"] <= 0 or m["turn_speed_mps"] <= 0:
                raise InvalidEvidence(f"lane {boat['lane']}: impossible physical measurement")
    except InvalidEvidence as exc:
        return _unusable(race, str(exc))

    components: dict[str, list[float]] = {
        key: _component_scores([float(b["measurements"][key]) for b in boats], key)
        for key in METRIC_KEYS
    }
    trait_scores = {
        "deashi": components["exit_acceleration_mps2"],
        "yukiashi": components["runup_acceleration_mps2"],
        "nobiashi": components["straight_speed_mps"],
        "mawariashi": components["turn_speed_mps"],
        "turn_performance": [
            round(0.40 * components["turn_time_s"][i]
                  + 0.35 * components["turn_min_speed_retention"][i]
                  + 0.25 * components["turn_marker_clearance_m"][i], 2)
            for i in range(6)
        ],
    }
    ranks = {trait: _competition_ranks(trait_scores[trait]) for trait in TRAITS}
    overall = [round(sum(trait_scores[t][i] for t in TRAITS) / len(TRAITS), 2) for i in range(6)]
    overall_ranks = _competition_ranks(overall)
    return {
        "schema_version": 1,
        "race": race,
        "status": "SHADOW_READY" if analyzed < deadline else "RESEARCH_ONLY_LATE",
        "reason": None,
        "method": "provisional_within_race_linear_indices_v1",
        "forecast_input_allowed": False,
        "purchase_decision_allowed": False,
        "capture": capture,
        "boats": [
            {
                "lane": b["lane"],
                "measurements": b["measurements"],
                "quality": b["quality"],
                "scores": {trait: trait_scores[trait][i] for trait in TRAITS},
                "ranks": {trait: ranks[trait][i] for trait in TRAITS},
                "overall_index": overall[i],
                "overall_rank": overall_ranks[i],
            }
            for i, b in enumerate(boats)
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path, help="calibrated measurements from an authorized video detector")
    parser.add_argument("--output", type=Path, help="write shadow-only ranking JSON")
    args = parser.parse_args()
    raw = args.evidence.read_bytes()
    evidence = json.loads(raw)
    result = evaluate_race(evidence)
    result["evidence_sha256"] = hashlib.sha256(raw).hexdigest()
    content = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    else:
        print(content, end="")


if __name__ == "__main__":
    main()
