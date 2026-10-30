"""Compare shadow-only video ranks with original exhibition time measurements.

No outcome/payout/odds data may enter this comparison, and no trained model or
Android production BUY/SKIP path is modified here.
"""

from __future__ import annotations

from datetime import datetime
import math
from typing import Any


REFERENCE_MAP = {
    "straight_time_s": ("nobiashi",),
    "turn_time_s": ("mawariashi", "turn_performance"),
    "lap_time_s": ("overall_index",),
}


def _parse_time(raw: Any) -> datetime:
    if not isinstance(raw, str):
        raise ValueError("missing reference timestamp")
    result = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("reference timestamp missing timezone")
    return result


def _rank_with_ties(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    position = 0
    while position < len(order):
        end = position + 1
        while end < len(order) and abs(values[order[end]] - values[order[position]]) < 1e-9:
            end += 1
        average_rank = (position + 1 + end) / 2
        for idx in order[position:end]:
            ranks[idx] = average_rank
        position = end
    return ranks


def _spearman(x: list[float], y: list[float]) -> float | None:
    rx = _rank_with_ties(x)
    ry = _rank_with_ties(y)
    mean_x = sum(rx) / len(rx)
    mean_y = sum(ry) / len(ry)
    xx = sum((v - mean_x) ** 2 for v in rx)
    yy = sum((v - mean_y) ** 2 for v in ry)
    if xx < 1e-12 or yy < 1e-12:
        return None
    return round(sum((a - mean_x) * (b - mean_y) for a, b in zip(rx, ry)) / math.sqrt(xx * yy), 6)


def compare_original_exhibition(vision: dict, reference: dict) -> dict:
    """Spearman rank agreement in a matched six-boat, pre-close research race."""
    if vision.get("status") != "SHADOW_READY" or vision.get("forecast_input_allowed") is not False:
        raise ValueError("comparison requires valid pre-close research-only vision")
    if vision.get("race") != reference.get("race"):
        raise ValueError("race identity/deadline mismatch")
    ref_source = reference.get("source")
    if not isinstance(ref_source, str) or not ref_source.strip() or not reference.get("permission_reference"):
        raise ValueError("reference provenance missing")
    deadline = _parse_time(reference["race"]["deadline"])
    if _parse_time(reference.get("captured_at")) >= deadline:
        raise ValueError("reference captured after deadline")
    records = reference.get("boats")
    if not isinstance(records, list) or len(records) != 6 or {b.get("lane") for b in records if isinstance(b, dict)} != set(range(1, 7)):
        raise ValueError("six reference boats required")
    records = sorted(records, key=lambda b: b["lane"])
    visions = sorted(vision["boats"], key=lambda b: b["lane"])
    if [b["lane"] for b in visions] != [b["lane"] for b in records]:
        raise ValueError("lane mismatch")
    result = {"schema_version": 1, "race": reference["race"], "status": "RESEARCH_COMPARISON",
              "source": ref_source, "forecast_input_allowed": False,
              "purchase_decision_allowed": False, "agreements": {}}
    for reference_key, vision_fields in REFERENCE_MAP.items():
        raw = [b.get(reference_key) for b in records]
        if any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) or v <= 0 for v in raw):
            result["agreements"][reference_key] = {f: None for f in vision_fields}
            continue
        reference_quality = [-float(v) for v in raw]  # Lower time is better.
        result["agreements"][reference_key] = {}
        for field in vision_fields:
            predicted = [float(b["overall_index"] if field == "overall_index" else b["scores"][field]) for b in visions]
            result["agreements"][reference_key][field] = _spearman(predicted, reference_quality)
    return result
