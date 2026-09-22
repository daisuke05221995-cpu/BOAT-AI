#!/usr/bin/env python3
"""Search variable 1-10 pick BOAT AI strategies without leaking holdout results.

Selection protocol:
- 2026-01-01..04-30: search/training
- 2026-05-01..06-30: tuning/selection
- 2026-07-01..latest: untouched holdout validation

The selected strategy is chosen before holdout results are inspected. Historical
closing odds are unavailable, so the live odds final gate is not included.
"""

from __future__ import annotations

import argparse
import json
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
    race_result,
    raw_confidence,
)

BUDGET_UNITS = 12  # 12 x 100 yen = 1,200 yen
MIN_TRAIN_BUYS = 100
MIN_TUNE_BUYS = 50
MIN_HOLDOUT_BUYS = 50
THRESHOLD_EXTRAS = tuple(range(0, 17, 2))


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
    """All non-increasing 100-yen allocations with at least 100 yen per pick."""
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


def evaluate(records: list[dict[str, Any]], start: date, end: date, points: int, extra: int, stakes: tuple[int, ...]) -> dict[str, Any]:
    buys = hits = stake = payout = 0
    for rec in records:
        day = rec["day"]
        if day < start or day > end:
            continue
        if rec["historySkip"]:
            continue
        threshold = min(97, int(rec["baseThreshold"]) + extra)
        if int(rec["confidence"]) < threshold:
            continue
        buys += 1
        stake += BUDGET_UNITS * 100
        picks = rec["picks"][:points]
        combo = rec["combo"]
        if combo in picks:
            hits += 1
            idx = picks.index(combo)
            payout += int(rec["amount"]) * stakes[idx]
    roi = payout * 100.0 / stake if stake else 0.0
    return {
        "purchaseRaces": buys,
        "hits": hits,
        "hitRate": round(hits * 100.0 / buys, 1) if buys else 0.0,
        "stake": stake,
        "payout": payout,
        "profit": payout - stake,
        "roi": round(roi, 1),
    }


def config_payload(points: int, extra: int, stakes: tuple[int, ...]) -> dict[str, Any]:
    return {
        "points": points,
        "thresholdExtra": extra,
        "stakes": [unit * 100 for unit in stakes],
        "budget": BUDGET_UNITS * 100,
    }


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
    if data_end < date(2026, 7, 1):
        raise SystemExit("holdout period has not started yet")

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

            records.append({
                "day": day,
                "confidence": confidence,
                "baseThreshold": buy_threshold(race, leader_lane),
                "historySkip": history_skip,
                "picks": picks,
                "combo": combo,
                "amount": trifecta_amount,
            })

            # Preserve current app performance-memory semantics while searching a new bet strategy.
            current_hit = combo in picks[:4]
            perf_payout = trifecta_amount * 3 if current_hit else 0
            observations.append((venue, raw, first_lane, current_hit, 1200, perf_payout))

        # Same-day outcomes are applied only after every race for that day was scored.
        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)

    train_start, train_end = date(2026, 1, 1), date(2026, 4, 30)
    tune_start, tune_end = date(2026, 5, 1), date(2026, 6, 30)
    holdout_start, holdout_end = date(2026, 7, 1), data_end

    train_candidates: list[dict[str, Any]] = []
    for points in range(1, 11):
        for stakes in stake_patterns(points):
            for extra in THRESHOLD_EXTRAS:
                train = evaluate(records, train_start, train_end, points, extra, stakes)
                if train["purchaseRaces"] < MIN_TRAIN_BUYS:
                    continue
                train_candidates.append({
                    "config": config_payload(points, extra, stakes),
                    "train": train,
                })

    if not train_candidates:
        raise SystemExit("no strategy met the minimum training sample")

    train_candidates.sort(key=lambda item: (item["train"]["roi"], item["train"]["profit"]), reverse=True)
    top_train = train_candidates[:200]

    tuned: list[dict[str, Any]] = []
    for candidate in top_train:
        cfg = candidate["config"]
        stakes = tuple(value // 100 for value in cfg["stakes"])
        tune = evaluate(records, tune_start, tune_end, cfg["points"], cfg["thresholdExtra"], stakes)
        if tune["purchaseRaces"] < MIN_TUNE_BUYS:
            continue
        tuned.append({**candidate, "tune": tune})

    if not tuned:
        raise SystemExit("no strategy met the minimum tuning sample")

    positive_both = [item for item in tuned if item["train"]["roi"] > 100.0 and item["tune"]["roi"] > 100.0]
    selection_pool = positive_both or tuned
    selection_pool.sort(
        key=lambda item: (
            min(item["train"]["roi"], item["tune"]["roi"]),
            item["tune"]["roi"],
            item["train"]["roi"],
            item["tune"]["profit"],
        ),
        reverse=True,
    )
    selected = selection_pool[0]
    cfg = selected["config"]
    stakes = tuple(value // 100 for value in cfg["stakes"])
    holdout = evaluate(records, holdout_start, holdout_end, cfg["points"], cfg["thresholdExtra"], stakes)

    current_cfg = {"points": 4, "thresholdExtra": 0, "stakes": [500, 400, 200, 100], "budget": 1200}
    current_stakes = (5, 4, 2, 1)
    current = {
        "config": current_cfg,
        "train": evaluate(records, train_start, train_end, 4, 0, current_stakes),
        "tune": evaluate(records, tune_start, tune_end, 4, 0, current_stakes),
        "holdout": evaluate(records, holdout_start, holdout_end, 4, 0, current_stakes),
    }

    qualified = bool(
        selected["train"]["roi"] > 100.0
        and selected["tune"]["roi"] > 100.0
        and holdout["roi"] > 100.0
        and selected["train"]["profit"] > 0
        and selected["tune"]["profit"] > 0
        and holdout["profit"] > 0
        and holdout["purchaseRaces"] >= MIN_HOLDOUT_BUYS
    )

    result = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "walk-forward prediction; strategy chosen on Jan-Apr training + May-Jun tuning; Jul-latest holdout untouched during selection",
        "oddsFinalGateIncluded": False,
        "searchSpace": {
            "points": [1, 10],
            "thresholdExtras": list(THRESHOLD_EXTRAS),
            "budget": 1200,
            "stakeUnit": 100,
            "allocationRule": "all non-increasing positive 100-yen allocations summing to 1,200 yen",
            "trainCandidates": len(train_candidates),
            "tunedCandidates": len(tuned),
        },
        "periods": {
            "train": [train_start.isoformat(), train_end.isoformat()],
            "tune": [tune_start.isoformat(), tune_end.isoformat()],
            "holdout": [holdout_start.isoformat(), holdout_end.isoformat()],
        },
        "currentFourPickBaseline": current,
        "selected": {**selected, "holdout": holdout},
        "qualifiedForRelease": qualified,
        "releaseRule": "ROI > 100% and positive profit in train, tune, and holdout; holdout has at least 50 purchases",
        "notes": [
            "The holdout period is not used to choose the strategy.",
            "Historical closing odds are unavailable, so live final-odds filtering is excluded.",
            "Performance-memory auto-skip behavior is preserved from the current app while bet point count/allocation/threshold are searched.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "selected": result["selected"],
        "qualifiedForRelease": qualified,
        "currentHoldout": current["holdout"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
