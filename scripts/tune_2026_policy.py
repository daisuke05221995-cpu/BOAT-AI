#!/usr/bin/env python3
"""Tune BOAT AI purchase policy with an out-of-time holdout.

Training: 2026-01-01..2026-06-30
Validation: 2026-07-01..latest settled day

Learning and performance memory are walk-forward and leakage-safe. Historical
closing odds are unavailable, so the live odds final gate is excluded.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor, as_completed

from build_2026_backtest import (
    JST,
    BUDGET,
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
    top_picks,
)

TRAIN_END = date(2026, 6, 30)
VALIDATION_START = date(2026, 7, 1)

STAKE_PLANS: dict[str, tuple[int, ...]] = {
    "weighted4": (500, 400, 200, 100),
    "equal4": (300, 300, 300, 300),
    "balanced4": (400, 300, 300, 200),
    "weighted3": (600, 400, 200),
    "balanced3": (500, 400, 300),
    "equal3": (400, 400, 400),
}


@dataclass(frozen=True)
class Candidate:
    base_threshold: int
    lane_mode: str
    max_wind: int
    max_wave: int
    allow_course_change: bool
    stake_plan: str


@dataclass
class Bucket:
    races: int = 0
    hits: int = 0
    stake: int = 0
    payout: int = 0

    def add(self, hit: bool, payout: int) -> None:
        self.races += 1
        self.hits += int(hit)
        self.stake += BUDGET
        self.payout += payout

    def payload(self) -> dict[str, Any]:
        return {
            "races": self.races,
            "hits": self.hits,
            "hitRate": round(self.hits * 100.0 / self.races, 1) if self.races else 0.0,
            "stake": self.stake,
            "payout": self.payout,
            "profit": self.payout - self.stake,
            "roi": round(self.payout * 100.0 / self.stake, 1) if self.stake else 0.0,
        }


def allowed_lane(mode: str, lane: int | None) -> bool:
    if lane is None:
        return False
    if mode == "all":
        return True
    limit = int(mode.split("-")[-1])
    return 1 <= lane <= limit


def course_changed(race: dict[str, Any], leader_lane: int | None) -> bool:
    if leader_lane is None:
        return False
    leader = next((r for r in race_racers(race) if r["lane"] == leader_lane), None)
    return bool(leader and leader.get("course") is not None and leader["course"] != leader_lane)


def threshold_for(base: int, race: dict[str, Any], leader_lane: int | None) -> int:
    return min(97, base + max(0, buy_threshold(race, leader_lane) - 80))


def candidate_grid() -> list[Candidate]:
    result: list[Candidate] = []
    for threshold in (80, 84, 88, 90, 92, 94, 96):
        for lane_mode in ("all", "1-1", "1-2", "1-3"):
            for max_wind in (99, 4, 2):
                for max_wave in (99, 7):
                    for allow_change in (True, False):
                        for stake_plan in STAKE_PLANS:
                            result.append(Candidate(
                                threshold,
                                lane_mode,
                                max_wind,
                                max_wave,
                                allow_change,
                                stake_plan,
                            ))
    return result


def plan_outcome(combo: str, trifecta_amount: int, picks: list[str], plan_name: str) -> tuple[bool, int]:
    stakes = STAKE_PLANS[plan_name]
    considered = picks[:len(stakes)]
    if combo not in considered:
        return False, 0
    idx = considered.index(combo)
    return True, trifecta_amount * (stakes[idx] // 100)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    today_jst = datetime.now(JST).date()
    end = args.end or min(today_jst - timedelta(days=1), date(2026, 12, 31))
    if end < VALIDATION_START:
        raise SystemExit("validation period has not started")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    performance = PerformanceProfile()
    candidates = candidate_grid()
    train = {candidate: Bucket() for candidate in candidates}
    validation = {candidate: Bucket() for candidate in candidates}

    dates: list[date] = []
    cursor = args.start
    while cursor <= end:
        dates.append(cursor)
        cursor += timedelta(days=1)

    payloads: dict[date, dict[str, Any]] = {}
    failed: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_day, day): day for day in dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                payloads[day] = payload
            elif error != "404":
                failed[day.isoformat()] = error or "unknown"
    if failed:
        raise SystemExit(f"download failures: {failed}")

    evaluated = 0
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
            picks = top_picks(score_map)
            if raw == 0 or len(picks) < 4:
                continue

            evaluated += 1
            venue = as_int(race.get("stadium_number"), 0) or 0
            first_lane = as_int(picks[0].split("-")[0])
            penalty = performance.penalty(venue, raw, first_lane)
            confidence = max(20, min(97, raw + penalty))
            skip_by_history = performance.auto_skip(venue, raw, first_lane)

            # Keep production performance-memory semantics unchanged while tuning.
            perf_hit = combo in picks
            perf_payout = trifecta_amount * 3 if perf_hit else 0
            observations.append((venue, raw, first_lane, perf_hit, BUDGET, perf_payout))

            preview = race.get("preview") or {}
            wind = as_int(preview.get("wind_speed"), 0) or 0
            wave = as_int(preview.get("wave_height"), 0) or 0
            changed = course_changed(race, leader_lane)
            outcomes = {
                name: plan_outcome(combo, trifecta_amount, picks, name)
                for name in STAKE_PLANS
            }

            target = train if day <= TRAIN_END else validation
            for candidate in candidates:
                if skip_by_history:
                    continue
                if confidence < threshold_for(candidate.base_threshold, race, leader_lane):
                    continue
                if not allowed_lane(candidate.lane_mode, first_lane):
                    continue
                if wind > candidate.max_wind or wave > candidate.max_wave:
                    continue
                if changed and not candidate.allow_course_change:
                    continue
                hit, payout = outcomes[candidate.stake_plan]
                target[candidate].add(hit, payout)

        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)

    rows: list[dict[str, Any]] = []
    for candidate in candidates:
        tr = train[candidate].payload()
        va = validation[candidate].payload()
        robust_roi = min(tr["roi"], va["roi"]) if tr["races"] and va["races"] else 0.0
        rows.append({
            "policy": asdict(candidate),
            "stakes": list(STAKE_PLANS[candidate.stake_plan]),
            "train": tr,
            "validation": va,
            "robustRoi": robust_roi,
            "positiveBoth": tr["roi"] > 100.0 and va["roi"] > 100.0,
        })

    robust = [r for r in rows if r["train"]["races"] >= 250 and r["validation"]["races"] >= 120]
    robust.sort(key=lambda r: (r["positiveBoth"], r["robustRoi"], r["validation"]["races"]), reverse=True)
    all_ranked = sorted(rows, key=lambda r: (r["robustRoi"], r["validation"]["races"]), reverse=True)

    payload = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataFrom": args.start.isoformat(),
        "dataThrough": end.isoformat(),
        "trainThrough": TRAIN_END.isoformat(),
        "validationFrom": VALIDATION_START.isoformat(),
        "evaluatedRaces": evaluated,
        "candidateCount": len(candidates),
        "oddsFinalGateIncluded": False,
        "minimumRobustSamples": {"train": 250, "validation": 120},
        "positiveRobustCount": sum(1 for r in robust if r["positiveBoth"]),
        "topRobust": robust[:40],
        "topAnySample": all_ranked[:20],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    print(json.dumps({
        "evaluatedRaces": evaluated,
        "candidateCount": len(candidates),
        "positiveRobustCount": payload["positiveRobustCount"],
        "best": payload["topRobust"][0] if payload["topRobust"] else None,
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
