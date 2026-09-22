#!/usr/bin/env python3
"""Search race-specific 1-10 pick BOAT AI strategies with staged validation.

Protocol:
- Jan-Apr: train/search coarse race contexts.
- May-Jun: tune and require the same context/config to remain profitable.
- Jul-Aug: validation; never used to select a context or stake pattern.
- Sep-latest: final confirmation is calculated only when Jul-Aug passes.

Historical closing odds are unavailable, so the live odds final gate is excluded.
The search therefore focuses on prediction context, point count and 100-yen stake allocation.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from build_2026_backtest import (
    JST,
    LearningProfile,
    PerformanceProfile,
    as_int,
    buy_threshold,
    decision_ready,
    fetch_day,
    parse_day,
    race_racers,
    race_result,
    raw_confidence,
)

BUDGET_UNITS = 12  # 12 x 100 yen = 1,200 yen
MIN_CONFIDENCE = 70
MIN_CONTEXT_TRAIN = 80
MIN_CONTEXT_TUNE = 30
MIN_CONTEXT_ROI = 105.0
MIN_VALIDATION_BUYS = 50
MIN_FINAL_BUYS = 20


def top_picks(score_map: dict[int, float], limit: int = 10) -> list[str]:
    ranked: list[tuple[str, float]] = []
    lanes = sorted(score_map)
    for first in lanes:
        for second in lanes:
            if second == first:
                continue
            for third in lanes:
                if third in (first, second):
                    continue
                score = score_map[first] + score_map[second] * 0.58 + score_map[third] * 0.31
                ranked.append((f"{first}-{second}-{third}", score))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [combo for combo, _ in ranked[:limit]]


def stake_patterns(points: int, total_units: int = BUDGET_UNITS) -> list[tuple[int, ...]]:
    """All non-increasing positive 100-yen allocations summing to the budget."""
    patterns: list[tuple[int, ...]] = []

    def walk(prefix: tuple[int, ...], remaining: int, left: int, maximum: int) -> None:
        if left == 0:
            if remaining == 0:
                patterns.append(prefix)
            return
        upper = min(maximum, remaining - (left - 1))
        for value in range(upper, 0, -1):
            walk(prefix + (value,), remaining - value, left - 1, value)

    walk(tuple(), total_units, points, total_units)
    return patterns


def confidence_band(value: int) -> str:
    if value < 80:
        return "70-79"
    if value < 85:
        return "80-84"
    if value < 90:
        return "85-89"
    if value < 94:
        return "90-93"
    return "94+"


def first_group(lane: int | None) -> str:
    if lane == 1:
        return "1"
    if lane in (2, 3):
        return "2-3"
    return "4-6"


def context_key(rec: dict[str, Any]) -> str:
    return "|".join(
        [
            confidence_band(int(rec["confidence"])),
            first_group(rec.get("firstLane")),
            "wind5+" if int(rec.get("wind", 0)) >= 5 else "wind0-4",
            "courseChange" if rec.get("courseChanged") else "courseStable",
            "historySkip" if rec.get("historySkip") else "historyKeep",
        ]
    )


def context_payload(key: str) -> dict[str, Any]:
    confidence, first, wind, course, history = key.split("|")
    return {
        "confidenceBand": confidence,
        "firstLaneGroup": first,
        "windBand": wind,
        "courseState": course,
        "historyState": history,
    }


def empty_stats() -> dict[str, Any]:
    return {"purchaseRaces": 0, "hits": 0, "stake": 0, "payout": 0}


def finalize_stats(stats: dict[str, Any]) -> dict[str, Any]:
    buys = int(stats.get("purchaseRaces", 0))
    hits = int(stats.get("hits", 0))
    stake = int(stats.get("stake", 0))
    payout = int(stats.get("payout", 0))
    return {
        "purchaseRaces": buys,
        "hits": hits,
        "hitRate": round(hits * 100.0 / buys, 1) if buys else 0.0,
        "stake": stake,
        "payout": payout,
        "profit": payout - stake,
        "roi": round(payout * 100.0 / stake, 1) if stake else 0.0,
    }


def evaluate_records(records: list[dict[str, Any]], points: int, stakes: tuple[int, ...]) -> dict[str, Any]:
    stats = empty_stats()
    for rec in records:
        stats["purchaseRaces"] += 1
        stats["stake"] += BUDGET_UNITS * 100
        picks = rec["picks"][:points]
        combo = rec["combo"]
        if combo in picks:
            stats["hits"] += 1
            idx = picks.index(combo)
            stats["payout"] += int(rec["amount"]) * stakes[idx]
    return finalize_stats(stats)


def evaluate_strategy(
    records: list[dict[str, Any]],
    start: date,
    end: date,
    selected: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    stats = empty_stats()
    for rec in records:
        day = rec["day"]
        if day < start or day > end:
            continue
        selected_context = selected.get(rec["contextKey"])
        if not selected_context:
            continue
        cfg = selected_context["config"]
        points = int(cfg["points"])
        stakes = tuple(int(value) // 100 for value in cfg["stakes"])
        stats["purchaseRaces"] += 1
        stats["stake"] += BUDGET_UNITS * 100
        picks = rec["picks"][:points]
        combo = rec["combo"]
        if combo in picks:
            stats["hits"] += 1
            idx = picks.index(combo)
            stats["payout"] += int(rec["amount"]) * stakes[idx]
    return finalize_stats(stats)


def evaluate_current_baseline(records: list[dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    stats = empty_stats()
    stakes = (5, 4, 2, 1)
    for rec in records:
        day = rec["day"]
        if day < start or day > end:
            continue
        if rec["historySkip"] or int(rec["confidence"]) < int(rec["baseThreshold"]):
            continue
        stats["purchaseRaces"] += 1
        stats["stake"] += 1200
        picks = rec["picks"][:4]
        if rec["combo"] in picks:
            stats["hits"] += 1
            idx = picks.index(rec["combo"])
            stats["payout"] += int(rec["amount"]) * stakes[idx]
    return finalize_stats(stats)


def config_payload(points: int, stakes: tuple[int, ...]) -> dict[str, Any]:
    return {
        "points": points,
        "stakes": [unit * 100 for unit in stakes],
        "budget": BUDGET_UNITS * 100,
    }


def profitable(stats: dict[str, Any], minimum_roi: float = 100.0) -> bool:
    return stats["roi"] > minimum_roi and stats["profit"] > 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    today_jst = datetime.now(JST).date()
    data_end = args.end or min(today_jst - timedelta(days=1), date(2026, 12, 31))
    if data_end < date(2026, 9, 1):
        raise SystemExit("final validation period has not started yet")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    performance = PerformanceProfile()

    dates: list[date] = []
    cursor = args.start
    while cursor <= data_end:
        dates.append(cursor)
        cursor += timedelta(days=1)

    payloads: dict[date, dict[str, Any]] = {}
    failed_days: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_day, day): day for day in dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                payloads[day] = payload
            elif error != "404":
                failed_days[day.isoformat()] = error or "unknown"

    if failed_days:
        raise SystemExit(f"download failures: {failed_days}")

    records: list[dict[str, Any]] = []
    for day in dates:
        root = payloads.get(day)
        if root is None:
            continue
        races = parse_day(root)
        observations: list[tuple[int, int, int | None, bool, int, int]] = []

        for race in races:
            combo, trifecta_amount = race_result(race)
            if not combo or trifecta_amount <= 0 or not decision_ready(race):
                continue

            raw, leader_lane, score_map = raw_confidence(race, learning)
            if raw == 0 or not score_map:
                continue
            picks = top_picks(score_map, 10)
            if not picks:
                continue

            venue = as_int(race.get("stadium_number"), 0) or 0
            first_lane = as_int(picks[0].split("-")[0])
            penalty = performance.penalty(venue, raw, first_lane)
            confidence = max(20, min(97, raw + penalty))
            history_skip = performance.auto_skip(venue, raw, first_lane)
            wind = as_int((race.get("preview") or {}).get("wind_speed"), 0) or 0
            first_racer = next((r for r in race_racers(race) if r["lane"] == first_lane), None)
            course = (first_racer or {}).get("course")
            course_changed = bool(course is not None and first_lane is not None and course != first_lane)

            if confidence >= MIN_CONFIDENCE:
                rec = {
                    "day": day,
                    "confidence": confidence,
                    "baseThreshold": buy_threshold(race, leader_lane),
                    "historySkip": history_skip,
                    "firstLane": first_lane,
                    "wind": wind,
                    "courseChanged": course_changed,
                    "picks": picks,
                    "combo": combo,
                    "amount": trifecta_amount,
                }
                rec["contextKey"] = context_key(rec)
                records.append(rec)

            # Preserve the app's current walk-forward performance memory while deriving contexts.
            current_hit = combo in picks[:4]
            perf_payout = trifecta_amount * 3 if current_hit else 0
            observations.append((venue, raw, first_lane, current_hit, 1200, perf_payout))

        # No same-day leakage: apply outcomes only after every race that day was scored.
        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)

    train_start, train_end = date(2026, 1, 1), date(2026, 4, 30)
    tune_start, tune_end = date(2026, 5, 1), date(2026, 6, 30)
    validation_start, validation_end = date(2026, 7, 1), date(2026, 8, 31)
    final_start, final_end = date(2026, 9, 1), data_end

    by_period_context: dict[str, dict[str, list[dict[str, Any]]]] = {
        "train": defaultdict(list),
        "tune": defaultdict(list),
    }
    for rec in records:
        day = rec["day"]
        if train_start <= day <= train_end:
            by_period_context["train"][rec["contextKey"]].append(rec)
        elif tune_start <= day <= tune_end:
            by_period_context["tune"][rec["contextKey"]].append(rec)

    selected_contexts: list[dict[str, Any]] = []
    selected_map: dict[str, dict[str, Any]] = {}
    diagnostics: list[dict[str, Any]] = []

    all_contexts = sorted(set(by_period_context["train"]) | set(by_period_context["tune"]))
    for key in all_contexts:
        train_records = by_period_context["train"].get(key, [])
        tune_records = by_period_context["tune"].get(key, [])
        if len(train_records) < MIN_CONTEXT_TRAIN or len(tune_records) < MIN_CONTEXT_TUNE:
            continue

        best: dict[str, Any] | None = None
        for points in range(1, 11):
            for stakes in stake_patterns(points):
                train = evaluate_records(train_records, points, stakes)
                tune = evaluate_records(tune_records, points, stakes)
                score = min(train["roi"], tune["roi"])
                candidate = {
                    "contextKey": key,
                    "context": context_payload(key),
                    "config": config_payload(points, stakes),
                    "train": train,
                    "tune": tune,
                    "robustRoi": round(score, 1),
                }
                if best is None or (
                    score,
                    tune["roi"],
                    train["roi"],
                    tune["profit"] + train["profit"],
                ) > (
                    best["robustRoi"],
                    best["tune"]["roi"],
                    best["train"]["roi"],
                    best["tune"]["profit"] + best["train"]["profit"],
                ):
                    best = candidate

        if best is None:
            continue
        diagnostics.append(best)
        if (
            best["robustRoi"] >= MIN_CONTEXT_ROI
            and profitable(best["train"])
            and profitable(best["tune"])
        ):
            selected_contexts.append(best)
            selected_map[key] = best

    selected_contexts.sort(
        key=lambda item: (
            item["robustRoi"],
            item["tune"]["roi"],
            item["train"]["roi"],
        ),
        reverse=True,
    )
    diagnostics.sort(key=lambda item: item["robustRoi"], reverse=True)

    aggregate_train = evaluate_strategy(records, train_start, train_end, selected_map)
    aggregate_tune = evaluate_strategy(records, tune_start, tune_end, selected_map)
    aggregate_validation = evaluate_strategy(records, validation_start, validation_end, selected_map)

    qualified_for_final = bool(
        selected_contexts
        and profitable(aggregate_train)
        and profitable(aggregate_tune)
        and profitable(aggregate_validation)
        and aggregate_validation["purchaseRaces"] >= MIN_VALIDATION_BUYS
    )

    final_stats: dict[str, Any] | None = None
    qualified_for_release = False
    if qualified_for_final and final_end >= final_start:
        final_stats = evaluate_strategy(records, final_start, final_end, selected_map)
        qualified_for_release = bool(
            profitable(final_stats)
            and final_stats["purchaseRaces"] >= MIN_FINAL_BUYS
        )

    baseline = {
        "train": evaluate_current_baseline(records, train_start, train_end),
        "tune": evaluate_current_baseline(records, tune_start, tune_end),
        "validation": evaluate_current_baseline(records, validation_start, validation_end),
    }
    if qualified_for_final and final_end >= final_start:
        baseline["final"] = evaluate_current_baseline(records, final_start, final_end)

    result = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "walk-forward predictions; context/config chosen on Jan-Apr + May-Jun only; Jul-Aug validation; Sep final evaluated only after validation passes",
        "oddsFinalGateIncluded": False,
        "searchSpace": {
            "points": [1, 10],
            "budget": 1200,
            "stakeUnit": 100,
            "allocationRule": "all non-increasing positive allocations summing to 1,200 yen",
            "contextDimensions": ["confidenceBand", "firstLaneGroup", "windBand", "courseState", "historyState"],
            "minimumConfidence": MIN_CONFIDENCE,
            "minimumContextTrainRaces": MIN_CONTEXT_TRAIN,
            "minimumContextTuneRaces": MIN_CONTEXT_TUNE,
            "minimumContextRobustRoi": MIN_CONTEXT_ROI,
        },
        "periods": {
            "train": [train_start.isoformat(), train_end.isoformat()],
            "tune": [tune_start.isoformat(), tune_end.isoformat()],
            "validation": [validation_start.isoformat(), validation_end.isoformat()],
            "final": [final_start.isoformat(), final_end.isoformat()],
        },
        "selectedContexts": selected_contexts,
        "aggregate": {
            "train": aggregate_train,
            "tune": aggregate_tune,
            "validation": aggregate_validation,
            "final": final_stats if final_stats is not None else {"withheld": True},
        },
        "currentFourPickBaseline": baseline,
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "releaseRule": "selected contexts profitable in train+tune, aggregate Jul-Aug ROI > 100% with >=50 buys, then Sep-latest ROI > 100% with >=20 buys",
        "topContextDiagnostics": diagnostics[:20],
        "notes": [
            "Point count and stake allocation can differ by race context.",
            "Jul-Aug results are not used to choose contexts or allocations.",
            "Sep results are not evaluated unless Jul-Aug validation is already positive.",
            "Historical closing odds are unavailable, so live final-odds filtering remains excluded.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "selectedContexts": len(selected_contexts),
        "aggregate": result["aggregate"],
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "baselineValidation": baseline["validation"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
