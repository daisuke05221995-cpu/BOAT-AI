#!/usr/bin/env python3
"""Guarded v12 monthly adaptive odds-value walk-forward.

This keeps v11's leakage-safe monthly selection, but prevents a single month from
jumping to a much narrower / materially riskier configuration. A challenger may
replace the incumbent only when its prior-month evidence is materially better and
its sample size / worst-month behaviour remain comparable.

IMPORTANT: v12 deliberately cannot qualify a release. 2026 has already been used
through repeated research iterations, so independent multi-year validation is
required before publishing the model to Android.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import search_2026_strategy_v11 as v11

MIN_COMBINED_ROI_GAIN = 5.0
MAX_WORST_ROI_DROP = 3.0
MIN_VOLUME_RETENTION = 0.60
MAX_POSITIVE_MONTH_DROP = 0

_original_choose = v11.choose_config
_previous_idx: int | None = None
_guard_decisions: list[dict[str, Any]] = []


def _score(idx: int, monthly_cache: dict[int, dict[int, dict[str, Any]]], history_keys: list[str]):
    stats = {key: monthly_cache[idx][int(key[-2:])] for key in history_keys}
    return v11.selection_score(stats, history_keys)


def guarded_choose_config(
    configs: list[dict[str, Any]],
    monthly_cache: dict[int, dict[int, dict[str, Any]]],
    history_keys: list[str],
):
    global _previous_idx

    candidate_idx, candidate_cfg, candidate_score = _original_choose(
        configs, monthly_cache, history_keys
    )
    label = f"2026-{len(history_keys) + 2:02d}" if len(history_keys) <= 7 else "nextLive"

    if _previous_idx is None:
        _previous_idx = candidate_idx
        _guard_decisions.append({
            "target": label,
            "action": "initial",
            "selectedIndex": candidate_idx,
            "selectedConfig": candidate_cfg,
            "selectedScore": list(candidate_score),
        })
        return candidate_idx, candidate_cfg, candidate_score

    incumbent_idx = _previous_idx
    incumbent_score = _score(incumbent_idx, monthly_cache, history_keys)
    if candidate_idx == incumbent_idx:
        _guard_decisions.append({
            "target": label,
            "action": "keep_same",
            "selectedIndex": incumbent_idx,
            "selectedConfig": configs[incumbent_idx],
            "selectedScore": list(incumbent_score),
        })
        return incumbent_idx, configs[incumbent_idx], incumbent_score

    candidate_roi = float(candidate_score[3])
    incumbent_roi = float(incumbent_score[3])
    candidate_worst = float(candidate_score[2])
    incumbent_worst = float(incumbent_score[2])
    candidate_buys = int(candidate_score[4])
    incumbent_buys = int(incumbent_score[4])
    volume_retention = candidate_buys / max(1, incumbent_buys)
    roi_gain = candidate_roi - incumbent_roi
    worst_drop = incumbent_worst - candidate_worst
    positive_drop = int(incumbent_score[1]) - int(candidate_score[1])

    allowed = bool(
        roi_gain >= MIN_COMBINED_ROI_GAIN
        and worst_drop <= MAX_WORST_ROI_DROP
        and volume_retention >= MIN_VOLUME_RETENTION
        and positive_drop <= MAX_POSITIVE_MONTH_DROP
    )

    if allowed:
        _previous_idx = candidate_idx
        chosen_idx = candidate_idx
        chosen_score = candidate_score
        action = "switch"
    else:
        chosen_idx = incumbent_idx
        chosen_score = incumbent_score
        action = "hold_incumbent"

    _guard_decisions.append({
        "target": label,
        "action": action,
        "candidateIndex": candidate_idx,
        "incumbentIndex": incumbent_idx,
        "candidateScore": list(candidate_score),
        "incumbentScore": list(incumbent_score),
        "roiGain": round(roi_gain, 3),
        "worstRoiDrop": round(worst_drop, 3),
        "volumeRetention": round(volume_retention, 4),
        "positiveMonthDrop": positive_drop,
        "selectedIndex": chosen_idx,
        "selectedConfig": configs[chosen_idx],
        "selectedScore": list(chosen_score),
    })
    return chosen_idx, configs[chosen_idx], chosen_score


def _output_path() -> Path:
    try:
        return Path(sys.argv[sys.argv.index("--output") + 1])
    except (ValueError, IndexError) as exc:
        raise SystemExit("--output is required") from exc


def main() -> None:
    output = _output_path()
    v11.choose_config = guarded_choose_config
    try:
        v11.main()
    finally:
        v11.choose_config = _original_choose

    result = json.loads(output.read_text(encoding="utf-8"))
    historical_criteria_met = bool(result.get("qualifiedForRelease"))
    result["schemaVersion"] = 12
    result["method"] = (
        "guarded monthly adaptive walk-forward conditional finish-order model + archived trifecta odds; "
        "configuration changes require material prior-month improvement, stable downside and retained sample volume"
    )
    result["guardPolicy"] = {
        "minCombinedRoiGain": MIN_COMBINED_ROI_GAIN,
        "maxWorstMonthRoiDrop": MAX_WORST_ROI_DROP,
        "minVolumeRetention": MIN_VOLUME_RETENTION,
        "maxPositiveMonthDrop": MAX_POSITIVE_MONTH_DROP,
    }
    result["guardDecisions"] = _guard_decisions
    result["historicalCriteriaMet"] = historical_criteria_met
    result["qualifiedForRelease"] = False
    result["releaseDeferredForIndependentValidation"] = True
    result["releaseRule"] = (
        "Historical May-Sep criteria remain ROI >=105%, >=4/5 positive months, worst month >=90%, "
        ">=50 buys/month and >=500 total buys; production release additionally requires independent multi-year validation."
    )
    notes = list(result.get("notes", []))
    notes.insert(0, "v12 prevents abrupt monthly parameter changes caused by small or fragile historical samples.")
    notes.insert(1, "2026 repeated research iterations are development evidence only; release is forcibly deferred until independent multi-year validation.")
    result["notes"] = notes
    output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(json.dumps({
        "operation": result.get("operation"),
        "operationMonths": result.get("operationMonths"),
        "historicalCriteriaMet": historical_criteria_met,
        "qualifiedForRelease": False,
        "nextLiveConfig": result.get("nextLiveConfig"),
        "guardDecisions": _guard_decisions,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
