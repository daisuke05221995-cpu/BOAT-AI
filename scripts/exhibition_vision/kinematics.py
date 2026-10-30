"""Prototype motion features from camera-calibrated per-boat video tracks.

Requires an independent detector/tracker to label the five racing phases and
produce actual x/y meters. Pixel coordinates are not accepted. These formulas
are provisional hypotheses and require real footage calibration/validation.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any


class InvalidTrack(ValueError):
    pass


PHASES = ("runup", "straight", "turn", "exit")


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise InvalidTrack(f"{name}: finite numeric meters/seconds required")
    return float(value)


def _phase(points: list[dict], phase: str) -> tuple[list[dict], list[float], list[float]]:
    selected = [point for point in points if point.get("phase") == phase]
    if len(selected) < 4:
        raise InvalidTrack(f"{phase}: at least 4 tracked observations needed")
    selected.sort(key=lambda p: p["t"])
    speeds: list[float] = []
    midpoints: list[float] = []
    for left, right in zip(selected, selected[1:]):
        dt = right["t"] - left["t"]
        if dt <= 0 or dt > 2:
            raise InvalidTrack(f"{phase}: duplicate/time-gap in track")
        dx = right["x_m"] - left["x_m"]
        dy = right["y_m"] - left["y_m"]
        speeds.append(math.hypot(dx, dy) / dt)
        midpoints.append((left["t"] + right["t"]) / 2)
    return selected, speeds, midpoints


def _acceleration(speeds: list[float], midpoints: list[float]) -> float:
    span = midpoints[-1] - midpoints[0]
    if span <= 0:
        raise InvalidTrack("zero acceleration time span")
    return (speeds[-1] - speeds[0]) / span


def measurements_from_tracks(tracked: dict[str, Any]) -> list[dict]:
    """Convert 6 phase-labelled boat tracks to the scoring input's boats array."""
    marker = tracked.get("turn_marker_m")
    if not isinstance(marker, dict):
        raise InvalidTrack("turn marker coordinates missing")
    marker_x = _finite(marker.get("x_m"), "marker.x_m")
    marker_y = _finite(marker.get("y_m"), "marker.y_m")
    boats = tracked.get("boats")
    if not isinstance(boats, list) or len(boats) != 6 or {b.get("lane") for b in boats if isinstance(b, dict)} != set(range(1, 7)):
        raise InvalidTrack("six uniquely labelled boats required")
    output = []
    for boat in sorted(boats, key=lambda b: b["lane"]):
        points = boat.get("points")
        if not isinstance(points, list):
            raise InvalidTrack("track points missing")
        normalized = []
        for point in points:
            if not isinstance(point, dict) or point.get("phase") not in PHASES:
                raise InvalidTrack("unknown phase")
            normalized.append({
                "phase": point["phase"],
                "t": _finite(point.get("t"), "frame time"),
                "x_m": _finite(point.get("x_m"), "calibrated x"),
                "y_m": _finite(point.get("y_m"), "calibrated y"),
            })
        segmented = {phase: _phase(normalized, phase) for phase in PHASES}
        runup, runup_speeds, runup_t = segmented["runup"]
        straight, straight_speeds, _ = segmented["straight"]
        turning, turn_speeds, _ = segmented["turn"]
        exiting, exit_speeds, exit_t = segmented["exit"]
        speed_reference = median(straight_speeds)
        if speed_reference <= 0:
            raise InvalidTrack("zero straight reference speed")
        quality = boat.get("quality")
        if not isinstance(quality, dict):
            raise InvalidTrack("quality metadata missing")
        output.append({
            "lane": boat["lane"],
            "quality": quality,
            "measurements": {
                "exit_acceleration_mps2": round(_acceleration(exit_speeds, exit_t), 5),
                "runup_acceleration_mps2": round(_acceleration(runup_speeds, runup_t), 5),
                "straight_speed_mps": round(speed_reference, 5),
                "turn_speed_mps": round(median(turn_speeds), 5),
                "turn_time_s": round(turning[-1]["t"] - turning[0]["t"], 5),
                "turn_min_speed_retention": round(min(1.0, min(turn_speeds) / speed_reference), 5),
                "turn_marker_clearance_m": round(min(
                    math.hypot(p["x_m"] - marker_x, p["y_m"] - marker_y) for p in turning
                ), 5),
            },
        })
    return output
