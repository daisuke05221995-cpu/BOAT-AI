#!/usr/bin/env python3
"""Search a walk-forward expected-return BOAT AI betting strategy.

This version avoids selecting rare fixed jackpot patterns. Each race is scored using
only results available through the previous day. For each of the 120 permutations of
model rank positions, a shrunk expected return is estimated from global, race-context
and venue history. Large payouts are capped only for learning so one jackpot cannot
dominate the estimator; evaluation always uses the real payout.

Protocol:
- Jan-Feb: estimator warm-up only.
- Mar-Jun: choose threshold / max points / allocation mode from monthly OOS signals.
- Jul-Aug: untouched validation for this strategy family.
- Sep-latest: final confirmation is evaluated only if BOTH Jul and Aug are profitable.

Historical closing odds are unavailable, so the live final-odds gate is excluded.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
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

BUDGET_UNITS = 12
LEARNING_PAYOUT_CAP = 20_000
CONTEXT_SHRINK = 500.0
VENUE_SHRINK = 900.0
MIN_CONTEXT_HISTORY = 120
MIN_GLOBAL_HISTORY = 800
MAX_SIGNAL_PATTERNS = 10
RANK_PATTERNS = tuple(itertools.permutations(range(1, 7), 3))
THRESHOLDS = (95.0, 100.0, 105.0, 110.0, 115.0, 120.0, 130.0, 140.0)
MAX_POINTS_OPTIONS = (1, 2, 3, 4, 6, 8, 10)
ALLOCATION_MODES = ("equal", "edge")


def score_top_picks(score_map: dict[int, float], limit: int = 10) -> list[str]:
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


def confidence_band(value: int) -> str:
    if value < 65:
        return "<65"
    if value < 75:
        return "65-74"
    if value < 85:
        return "75-84"
    if value < 90:
        return "85-89"
    return "90+"


def first_group(lane: int | None) -> str:
    if lane == 1:
        return "1"
    if lane in (2, 3):
        return "2-3"
    return "4-6"


def gap_band(gap: float) -> str:
    if gap < 5.0:
        return "gap<5"
    if gap < 10.0:
        return "gap5-9"
    return "gap10+"


def context_key(rec: dict[str, Any]) -> str:
    return "|".join([
        confidence_band(int(rec["confidence"])),
        first_group(rec.get("firstLane")),
        gap_band(float(rec.get("scoreGap", 0.0))),
        "wind5+" if int(rec.get("wind", 0)) >= 5 else "wind0-4",
        "courseChange" if rec.get("courseChanged") else "courseStable",
        "historySkip" if rec.get("historySkip") else "historyKeep",
    ])


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


def add_stats(target: dict[str, Any], source: dict[str, Any]) -> None:
    for key in ("purchaseRaces", "hits", "stake", "payout"):
        target[key] += int(source.get(key, 0))


def winning_rank_pattern(combo: str, ranked_lanes: list[int]) -> tuple[int, int, int] | None:
    try:
        lanes = [int(v) for v in combo.split("-")]
    except ValueError:
        return None
    if len(lanes) != 3:
        return None
    rank_of = {lane: rank for rank, lane in enumerate(ranked_lanes, start=1)}
    try:
        return tuple(rank_of[lane] for lane in lanes)  # type: ignore[return-value]
    except KeyError:
        return None


def pattern_text(pattern: tuple[int, int, int]) -> str:
    return "-".join(str(v) for v in pattern)


def allocate_units(estimates: list[float], threshold: float, mode: str) -> list[int]:
    points = len(estimates)
    if points <= 0:
        return []
    if points > BUDGET_UNITS:
        estimates = estimates[:BUDGET_UNITS]
        points = len(estimates)

    if mode == "equal":
        base = BUDGET_UNITS // points
        remainder = BUDGET_UNITS - base * points
        return [base + (1 if idx < remainder else 0) for idx in range(points)]

    # Edge-proportional: every pick gets 100 yen, remaining units follow estimated edge.
    units = [1] * points
    remaining = BUDGET_UNITS - points
    edges = [max(1.0, value - threshold) for value in estimates]
    total_edge = sum(edges)
    if remaining <= 0 or total_edge <= 0:
        return units
    raw_extra = [remaining * edge / total_edge for edge in edges]
    floors = [int(math.floor(value)) for value in raw_extra]
    for idx, value in enumerate(floors):
        units[idx] += value
    leftover = BUDGET_UNITS - sum(units)
    order = sorted(range(points), key=lambda idx: raw_extra[idx] - floors[idx], reverse=True)
    for idx in order[:leftover]:
        units[idx] += 1
    return units


def evaluate_signals(
    signals: list[dict[str, Any]],
    start: date,
    end: date,
    threshold: float,
    max_points: int,
    allocation_mode: str,
) -> dict[str, Any]:
    stats = empty_stats()
    for signal in signals:
        day = signal["day"]
        if day < start or day > end:
            continue
        candidates = [item for item in signal["patterns"] if float(item["expectedReturn"]) >= threshold][:max_points]
        if not candidates:
            continue
        estimates = [float(item["expectedReturn"]) for item in candidates]
        units = allocate_units(estimates, threshold, allocation_mode)
        stats["purchaseRaces"] += 1
        stats["stake"] += BUDGET_UNITS * 100
        winning = signal["winningPattern"]
        for idx, item in enumerate(candidates):
            if item["pattern"] == winning:
                stats["hits"] += 1
                stats["payout"] += int(signal["amount"]) * units[idx]
                break
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
        picks = rec["baselinePicks"][:4]
        if rec["combo"] in picks:
            idx = picks.index(rec["combo"])
            stats["hits"] += 1
            stats["payout"] += int(rec["amount"]) * stakes[idx]
    return finalize_stats(stats)


def profitable(stats: dict[str, Any]) -> bool:
    return stats["profit"] > 0 and stats["roi"] > 100.0


def build_signals(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    global_count = 0
    global_payout: dict[tuple[int, int, int], float] = defaultdict(float)
    context_count: dict[str, int] = defaultdict(int)
    context_payout: dict[str, dict[tuple[int, int, int], float]] = defaultdict(lambda: defaultdict(float))
    venue_count: dict[int, int] = defaultdict(int)
    venue_payout: dict[int, dict[tuple[int, int, int], float]] = defaultdict(lambda: defaultdict(float))

    signals: list[dict[str, Any]] = []
    records_by_day: dict[date, list[dict[str, Any]]] = defaultdict(list)
    for rec in records:
        records_by_day[rec["day"]].append(rec)

    for day in sorted(records_by_day):
        day_records = records_by_day[day]
        for rec in day_records:
            key = rec["contextKey"]
            venue = int(rec["venue"])
            if global_count < MIN_GLOBAL_HISTORY or context_count[key] < MIN_CONTEXT_HISTORY:
                continue

            ranked: list[dict[str, Any]] = []
            for pattern in RANK_PATTERNS:
                global_mean = global_payout[pattern] / global_count if global_count else 0.0
                c_count = context_count[key]
                v_count = venue_count[venue]
                context_mean = (
                    context_payout[key][pattern] + CONTEXT_SHRINK * global_mean
                ) / (c_count + CONTEXT_SHRINK)
                venue_mean = (
                    venue_payout[venue][pattern] + VENUE_SHRINK * global_mean
                ) / (v_count + VENUE_SHRINK) if v_count else global_mean
                expected = context_mean * 0.65 + venue_mean * 0.25 + global_mean * 0.10
                ranked.append({"pattern": pattern_text(pattern), "expectedReturn": round(expected, 3)})

            ranked.sort(key=lambda item: float(item["expectedReturn"]), reverse=True)
            signals.append({
                "day": day,
                "patterns": ranked[:MAX_SIGNAL_PATTERNS],
                "winningPattern": rec["winningPattern"],
                "amount": rec["amount"],
            })

        # No same-day leakage: all outcomes are incorporated only after the day's signals are made.
        for rec in day_records:
            pattern = rec.get("winningPatternTuple")
            if pattern is None:
                continue
            key = rec["contextKey"]
            venue = int(rec["venue"])
            learned_payout = min(int(rec["amount"]), LEARNING_PAYOUT_CAP)
            global_count += 1
            context_count[key] += 1
            venue_count[venue] += 1
            global_payout[pattern] += learned_payout
            context_payout[key][pattern] += learned_payout
            venue_payout[venue][pattern] += learned_payout

    return signals


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
        raise SystemExit("final period has not started yet")

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
            if raw == 0 or len(score_map) != 6:
                continue

            ranked_lanes = [lane for lane, _ in sorted(score_map.items(), key=lambda item: item[1], reverse=True)]
            win_pattern = winning_rank_pattern(combo, ranked_lanes)
            if win_pattern is None:
                continue
            score_values = sorted(score_map.values(), reverse=True)
            first_lane = ranked_lanes[0]
            venue = as_int(race.get("stadium_number"), 0) or 0
            penalty = performance.penalty(venue, raw, first_lane)
            confidence = max(20, min(97, raw + penalty))
            history_skip = performance.auto_skip(venue, raw, first_lane)
            wind = as_int((race.get("preview") or {}).get("wind_speed"), 0) or 0
            first_racer = next((r for r in race_racers(race) if r["lane"] == first_lane), None)
            course = (first_racer or {}).get("course")
            baseline_picks = score_top_picks(score_map, 10)

            rec = {
                "day": day,
                "venue": venue,
                "confidence": confidence,
                "baseThreshold": buy_threshold(race, leader_lane),
                "historySkip": history_skip,
                "firstLane": first_lane,
                "scoreGap": score_values[0] - score_values[1],
                "wind": wind,
                "courseChanged": bool(course is not None and course != first_lane),
                "baselinePicks": baseline_picks,
                "combo": combo,
                "amount": trifecta_amount,
                "winningPattern": pattern_text(win_pattern),
                "winningPatternTuple": win_pattern,
            }
            rec["contextKey"] = context_key(rec)
            records.append(rec)

            current_hit = combo in baseline_picks[:4]
            perf_payout = trifecta_amount * 3 if current_hit else 0
            observations.append((venue, raw, first_lane, current_hit, 1200, perf_payout))

        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)

    signals = build_signals(records)

    dev_months = [(2026, 3), (2026, 4), (2026, 5), (2026, 6)]
    validation_months = [(2026, 7), (2026, 8)]
    final_start, final_end = date(2026, 9, 1), data_end

    candidates: list[dict[str, Any]] = []
    for threshold in THRESHOLDS:
        for max_points in MAX_POINTS_OPTIONS:
            for allocation_mode in ALLOCATION_MODES:
                monthly: dict[str, dict[str, Any]] = {}
                combined_raw = empty_stats()
                for year, month in dev_months:
                    start = date(year, month, 1)
                    end = (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1))
                    stats = evaluate_signals(signals, start, end, threshold, max_points, allocation_mode)
                    monthly[f"{year}-{month:02d}"] = stats
                    add_stats(combined_raw, stats)
                combined = finalize_stats(combined_raw)
                month_rois = [monthly[key]["roi"] for key in sorted(monthly)]
                positive_months = sum(1 for value in monthly.values() if profitable(value))
                worst_roi = min(month_rois) if month_rois else 0.0
                candidates.append({
                    "config": {
                        "threshold": threshold,
                        "maxPoints": max_points,
                        "allocationMode": allocation_mode,
                        "budget": 1200,
                    },
                    "developmentMonths": monthly,
                    "development": combined,
                    "positiveMonths": positive_months,
                    "worstMonthRoi": round(worst_roi, 1),
                })

    eligible = [
        item for item in candidates
        if item["development"]["purchaseRaces"] >= 200
        and item["positiveMonths"] >= 3
        and profitable(item["development"])
    ]
    selection_pool = eligible or candidates
    selection_pool.sort(
        key=lambda item: (
            item["positiveMonths"],
            item["worstMonthRoi"],
            item["development"]["roi"],
            item["development"]["profit"],
            item["development"]["purchaseRaces"],
        ),
        reverse=True,
    )
    selected = selection_pool[0]
    cfg = selected["config"]

    validation_detail: dict[str, dict[str, Any]] = {}
    validation_raw = empty_stats()
    for year, month in validation_months:
        start = date(year, month, 1)
        end = (date(year + (month == 12), 1 if month == 12 else month + 1, 1) - timedelta(days=1))
        stats = evaluate_signals(signals, start, end, cfg["threshold"], cfg["maxPoints"], cfg["allocationMode"])
        validation_detail[f"{year}-{month:02d}"] = stats
        add_stats(validation_raw, stats)
    validation = finalize_stats(validation_raw)

    qualified_for_final = bool(
        selected in eligible
        and validation["purchaseRaces"] >= 50
        and profitable(validation)
        and all(profitable(stats) for stats in validation_detail.values())
    )

    final_stats: dict[str, Any] | None = None
    qualified_for_release = False
    if qualified_for_final and final_end >= final_start:
        final_stats = evaluate_signals(
            signals, final_start, final_end,
            cfg["threshold"], cfg["maxPoints"], cfg["allocationMode"],
        )
        qualified_for_release = bool(
            final_stats["purchaseRaces"] >= 20 and profitable(final_stats)
        )

    baseline = {
        "development": evaluate_current_baseline(records, date(2026, 3, 1), date(2026, 6, 30)),
        "validation": evaluate_current_baseline(records, date(2026, 7, 1), date(2026, 8, 31)),
    }
    if qualified_for_final:
        baseline["final"] = evaluate_current_baseline(records, final_start, final_end)

    result = {
        "schemaVersion": 4,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "daily walk-forward shrunk expected return for 120 model-rank trifecta patterns; same-day results applied next day",
        "oddsFinalGateIncluded": False,
        "estimator": {
            "learningPayoutCapPer100": LEARNING_PAYOUT_CAP,
            "contextShrink": CONTEXT_SHRINK,
            "venueShrink": VENUE_SHRINK,
            "minimumContextHistory": MIN_CONTEXT_HISTORY,
            "minimumGlobalHistory": MIN_GLOBAL_HISTORY,
            "weights": {"context": 0.65, "venue": 0.25, "global": 0.10},
        },
        "periods": {
            "warmup": ["2026-01-01", "2026-02-28"],
            "development": ["2026-03-01", "2026-06-30"],
            "validation": ["2026-07-01", "2026-08-31"],
            "final": [final_start.isoformat(), final_end.isoformat()],
        },
        "selected": selected,
        "validationMonths": validation_detail,
        "validation": validation,
        "final": final_stats if final_stats is not None else {"withheld": True},
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "currentFourPickBaseline": baseline,
        "releaseRule": "development positive in >=3/4 months and combined; Jul and Aug each positive with combined >=50 buys; only then Sep-latest must be positive with >=20 buys",
        "topCandidates": selection_pool[:10],
        "notes": [
            "All estimates are made before the race using outcomes only through the previous day.",
            "Learning caps large payouts at 20,000 yen per 100 yen to reduce jackpot overfit; evaluation uses full actual payouts.",
            "Point count is variable from zero (skip) through the selected maxPoints; only patterns above the selected expected-return threshold are bought.",
            "Sep results remain hidden unless Jul and Aug both pass.",
            "Historical closing odds are unavailable, so live final-odds filtering remains excluded.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "selected": selected,
        "validationMonths": validation_detail,
        "validation": validation,
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "final": result["final"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
