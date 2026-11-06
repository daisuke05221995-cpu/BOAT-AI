"""Experimental turn-window detection from six calibrated boat trajectories.

This deliberately declines to label phases when a collective turn cannot be
observed. A pre-turn split between run-up and straight is a fixed heuristic,
not a validated racing-phase classifier. Never use these labels for BUY/ROI.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Any


class PhaseDetectionError(ValueError):
    pass


def _turn_angle(a: dict, b: dict, c: dict) -> float:
    ax, ay = b["x_m"] - a["x_m"], b["y_m"] - a["y_m"]
    bx, by = c["x_m"] - b["x_m"], c["y_m"] - b["y_m"]
    if math.hypot(ax, ay) < 0.05 or math.hypot(bx, by) < 0.05:
        return 0.0
    return math.atan2(ax * by - ay * bx, ax * bx + ay * by)


def detect_six_boat_turn(boats: list[dict[str, Any]]) -> dict[str, Any]:
    """Find one shared turn in a fixed-camera video (all six tracks required)."""
    if len(boats) != 6 or {boat.get("lane") for boat in boats} != set(range(1, 7)):
        raise PhaseDetectionError("six identifiable boats required")
    by_lane = []
    for boat in sorted(boats, key=lambda x: x["lane"]):
        points = boat.get("points")
        if not isinstance(points, list) or len(points) < 24:
            raise PhaseDetectionError("insufficient tracked frames for automatic turn")
        by_lane.append({point["t"]: point for point in points})
    common_times = sorted(set.intersection(*(set(points) for points in by_lane)))
    if len(common_times) < 24:
        raise PhaseDetectionError("insufficient concurrent six-boat observations")
    ordered = [[points[t] for t in common_times] for points in by_lane]
    motion = [0.0] * len(common_times)
    for index in range(1, len(common_times) - 1):
        motion[index] = median(
            _turn_angle(points[index - 1], points[index], points[index + 1])
            for points in ordered
        )
    # Smooth a few frames to suppress isolated single-pixel direction jumps.
    smooth = [sum(motion[max(0, i - 2):min(len(motion), i + 3)]) /
              len(motion[max(0, i - 2):min(len(motion), i + 3)])
              for i in range(len(motion))]
    active = [i for i, angle in enumerate(smooth) if abs(angle) >= 0.020]
    if not active:
        raise PhaseDetectionError("no sustained common turn observed")
    groups: list[list[int]] = [[active[0]]]
    for i in active[1:]:
        if i - groups[-1][-1] <= 3:
            groups[-1].append(i)
        else:
            groups.append([i])
    groups.sort(key=lambda group: sum(abs(smooth[i]) for i in group), reverse=True)
    for other in groups[1:]:
        if len(other) >= 6 and sum(abs(smooth[i]) for i in other) >= 0.60:
            raise PhaseDetectionError("multiple significant turns: ambiguous exhibition segment")
    best = groups[0]
    start, end = max(1, best[0] - 1), min(len(common_times) - 1, best[-1] + 2)
    total_angle = sum(smooth[start:end])
    consistent_turn_frames = sum(1 for i in range(start, end) if smooth[i] * total_angle >= 0)
    if (end - start < 6 or abs(total_angle) < 0.60 or
            consistent_turn_frames / (end - start) < 0.75):
        raise PhaseDetectionError("common turn angle/consistency below gate")
    if start < 10 or end > len(common_times) - 4:
        raise PhaseDetectionError("not enough pre-turn or exit footage")

    runup_end_index = start // 2
    if runup_end_index < 4 or start - runup_end_index < 4:
        raise PhaseDetectionError("cannot isolate run-up and straight segments")
    runup_end = common_times[runup_end_index]
    turn_start = common_times[start]
    turn_end = common_times[end]
    # Last time + one ordinary frame period to assign every observed frame.
    dt = median(b - a for a, b in zip(common_times, common_times[1:]))
    observed_start = min(min(points) for points in by_lane)
    observed_end = max(max(points) for points in by_lane)
    phase_windows = [
        {"phase": "runup", "start_s": observed_start, "end_s": runup_end},
        {"phase": "straight", "start_s": runup_end, "end_s": turn_start},
        {"phase": "turn", "start_s": turn_start, "end_s": turn_end},
        {"phase": "exit", "start_s": turn_end, "end_s": observed_end + dt},
    ]
    return {
        "method": "collective_heading_change_v1_unvalidated",
        "phase_windows": phase_windows,
        "total_turn_angle_degrees": round(math.degrees(total_angle), 2),
        "common_observations": len(common_times),
        "runup_split_is_heuristic": True,
    }


def apply_detected_phases(boats: list[dict[str, Any]]) -> dict[str, Any]:
    detected = detect_six_boat_turn(boats)
    windows = detected["phase_windows"]
    for boat in boats:
        assigned = []
        for point in boat["points"]:
            phase = next((w["phase"] for w in windows if w["start_s"] <= point["t"] < w["end_s"]), None)
            if phase is not None:
                point["phase"] = phase
                assigned.append(point)
        boat["points"] = assigned
    return detected
