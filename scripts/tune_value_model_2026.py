#!/usr/bin/env python3
"""Tune a leakage-safe probability x payout-value pick model for BOAT AI.

Every race is predicted with information available before its result. Trifecta
payout tendencies are updated only after all races for that calendar day have
been evaluated, so the same day's result can never improve its own prediction.
Historical closing odds are unavailable and the live odds final gate is excluded.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

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
    scored_racers,
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
class PickModel:
    temperature: int
    value_alpha: float
    payout_cap: int
    first_fixed: bool


@dataclass(frozen=True)
class BuyFilter:
    name: str
    base_threshold: int
    max_wind: int = 99
    allow_course_change: bool = True
    max_first_lane: int = 6


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


class PayoutValueProfile:
    """Shrunk exact-combination payout means using previous days only."""

    CAPS = (30000, 60000)
    PRIOR_WEIGHT = 18
    START_MEAN = 7000.0

    def __init__(self) -> None:
        self.counts: dict[str, int] = defaultdict(int)
        self.sums: dict[int, dict[str, int]] = {cap: defaultdict(int) for cap in self.CAPS}
        self.global_count = 0
        self.global_sums: dict[int, int] = {cap: 0 for cap in self.CAPS}

    def expected(self, combo: str, cap: int) -> float:
        global_mean = (
            self.global_sums[cap] / self.global_count
            if self.global_count > 0
            else self.START_MEAN
        )
        count = self.counts.get(combo, 0)
        total = self.sums[cap].get(combo, 0)
        return (total + global_mean * self.PRIOR_WEIGHT) / (count + self.PRIOR_WEIGHT)

    def observe(self, combo: str | None, payout: int) -> None:
        if not combo or payout <= 0:
            return
        self.counts[combo] += 1
        self.global_count += 1
        for cap in self.CAPS:
            value = min(payout, cap)
            self.sums[cap][combo] += value
            self.global_sums[cap] += value


def pick_models() -> list[PickModel]:
    return [
        PickModel(temp, alpha, cap, first_fixed)
        for temp in (10, 16, 24)
        for alpha in (0.0, 0.35, 0.60, 0.85, 1.10)
        for cap in PayoutValueProfile.CAPS
        for first_fixed in (False, True)
    ]


def buy_filters() -> list[BuyFilter]:
    return [
        BuyFilter("base80", 80),
        BuyFilter("calm80", 80, max_wind=4, allow_course_change=False),
        BuyFilter("calm12_80", 80, max_wind=4, allow_course_change=False, max_first_lane=2),
        BuyFilter("calm88", 88, max_wind=4, allow_course_change=False),
        BuyFilter("calm12_88", 88, max_wind=4, allow_course_change=False, max_first_lane=2),
        BuyFilter("calm12_94", 94, max_wind=4, allow_course_change=False, max_first_lane=2),
    ]


def all_probability_rows(score_map: dict[int, float], temperature: int) -> list[tuple[str, float]]:
    lanes = sorted(score_map)
    if len(lanes) < 3:
        return []
    max_score = max(score_map.values())
    weights = {lane: math.exp((score_map[lane] - max_score) / temperature) for lane in lanes}
    total = sum(weights.values())
    rows: list[tuple[str, float]] = []
    for first in lanes:
        p1 = weights[first] / total
        rem1 = total - weights[first]
        if rem1 <= 0:
            continue
        for second in lanes:
            if second == first:
                continue
            p2 = weights[second] / rem1
            rem2 = rem1 - weights[second]
            if rem2 <= 0:
                continue
            for third in lanes:
                if third in (first, second):
                    continue
                p3 = weights[third] / rem2
                probability = max(1e-12, p1 * p2 * p3)
                rows.append((f"{first}-{second}-{third}", math.log(probability)))
    rows.sort(key=lambda item: item[1], reverse=True)
    return rows


def value_picks(
    probability_rows: list[tuple[str, float]],
    leader_lane: int | None,
    profile: PayoutValueProfile,
    model: PickModel,
) -> list[str]:
    # Restrict the value search to plausible outcomes so payout alone cannot promote extreme tails.
    plausible = probability_rows[:30]
    ranked: list[tuple[str, float]] = []
    for combo, log_probability in plausible:
        if model.first_fixed and leader_lane is not None and not combo.startswith(f"{leader_lane}-"):
            continue
        expected_payout = profile.expected(combo, model.payout_cap)
        value_term = math.log(max(100.0, expected_payout) / 7000.0)
        metric = log_probability + model.value_alpha * value_term
        ranked.append((combo, metric))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [combo for combo, _ in ranked[:4]]


def course_changed(race: dict[str, Any], leader_lane: int | None) -> bool:
    if leader_lane is None:
        return False
    leader = next((r for r in race_racers(race) if r["lane"] == leader_lane), None)
    return bool(leader and leader.get("course") is not None and leader["course"] != leader_lane)


def threshold_for(base: int, race: dict[str, Any], leader_lane: int | None) -> int:
    return min(97, base + max(0, buy_threshold(race, leader_lane) - 80))


def outcome(combo: str, result_payout: int, picks: list[str], stakes: tuple[int, ...]) -> tuple[bool, int]:
    considered = picks[:len(stakes)]
    if combo not in considered:
        return False, 0
    idx = considered.index(combo)
    return True, result_payout * (stakes[idx] // 100)


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
    payout_profile = PayoutValueProfile()
    models = pick_models()
    filters = buy_filters()
    keys = [(model, f, plan) for model in models for f in filters for plan in STAKE_PLANS]
    train = {key: Bucket() for key in keys}
    validation = {key: Bucket() for key in keys}

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
        performance_observations: list[tuple[int, int, int | None, bool, int, int]] = []
        payout_observations: list[tuple[str | None, int]] = []

        for race in races:
            combo, result_payout = race_result(race)
            if combo and result_payout > 0:
                payout_observations.append((combo, result_payout))
            if not combo or result_payout <= 0 or not decision_ready(race):
                continue

            raw, leader_lane, base_score_map = raw_confidence(race, learning)
            if raw == 0 or len(base_score_map) < 6:
                continue
            evaluated += 1

            venue = as_int(race.get("stadium_number"), 0) or 0
            penalty = performance.penalty(venue, raw, leader_lane)
            confidence = max(20, min(97, raw + penalty))
            skip_by_history = performance.auto_skip(venue, raw, leader_lane)

            # Keep performance-memory semantics comparable to the current engine: top four by base score.
            base_rows = all_probability_rows(base_score_map, 16)
            base_picks = [c for c, _ in base_rows[:4]]
            perf_hit = combo in base_picks
            perf_payout = result_payout * 3 if perf_hit else 0
            performance_observations.append((venue, raw, leader_lane, perf_hit, BUDGET, perf_payout))
            if skip_by_history:
                continue

            preview = race.get("preview") or {}
            wind = as_int(preview.get("wind_speed"), 0) or 0
            changed = course_changed(race, leader_lane)
            target = train if day <= TRAIN_END else validation

            probability_cache = {
                temp: all_probability_rows(base_score_map, temp)
                for temp in {model.temperature for model in models}
            }
            pick_cache: dict[PickModel, list[str]] = {}
            for model in models:
                picks = value_picks(probability_cache[model.temperature], leader_lane, payout_profile, model)
                if len(picks) < 3:
                    continue
                pick_cache[model] = picks

            for f in filters:
                if confidence < threshold_for(f.base_threshold, race, leader_lane):
                    continue
                if wind > f.max_wind:
                    continue
                if changed and not f.allow_course_change:
                    continue
                if leader_lane is None or leader_lane > f.max_first_lane:
                    continue
                for model, picks in pick_cache.items():
                    for plan, stakes in STAKE_PLANS.items():
                        hit, paid = outcome(combo, result_payout, picks, stakes)
                        target[(model, f, plan)].add(hit, paid)

        # All same-day outcomes become available only after every race on that day was predicted.
        for race in races:
            learning.observe_race(race)
        for observation in performance_observations:
            performance.observe(*observation)
        for combo, paid in payout_observations:
            payout_profile.observe(combo, paid)

    rows: list[dict[str, Any]] = []
    for model, f, plan in keys:
        tr = train[(model, f, plan)].payload()
        va = validation[(model, f, plan)].payload()
        robust_roi = min(tr["roi"], va["roi"]) if tr["races"] and va["races"] else 0.0
        rows.append({
            "pickModel": asdict(model),
            "buyFilter": asdict(f),
            "stakePlan": plan,
            "stakes": list(STAKE_PLANS[plan]),
            "train": tr,
            "validation": va,
            "robustRoi": robust_roi,
            "positiveBoth": tr["roi"] > 100.0 and va["roi"] > 100.0,
        })

    robust = [r for r in rows if r["train"]["races"] >= 250 and r["validation"]["races"] >= 120]
    robust.sort(key=lambda r: (r["positiveBoth"], r["robustRoi"], r["validation"]["races"]), reverse=True)
    positive = [r for r in robust if r["positiveBoth"]]

    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataFrom": args.start.isoformat(),
        "dataThrough": end.isoformat(),
        "trainThrough": TRAIN_END.isoformat(),
        "validationFrom": VALIDATION_START.isoformat(),
        "evaluatedRaces": evaluated,
        "modelCount": len(models),
        "filterCount": len(filters),
        "candidateCount": len(rows),
        "oddsFinalGateIncluded": False,
        "minimumRobustSamples": {"train": 250, "validation": 120},
        "positiveRobustCount": len(positive),
        "topPositive": positive[:30],
        "topRobust": robust[:40],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "evaluatedRaces": evaluated,
        "modelCount": len(models),
        "candidateCount": len(rows),
        "positiveRobustCount": len(positive),
        "best": robust[0] if robust else None,
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
