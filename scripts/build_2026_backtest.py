#!/usr/bin/env python3
"""Generate BOAT AI 2026 month/year backtest data from public historical race JSON.

The simulation is intentionally walk-forward and leakage-safe:
- starts from a learning snapshot trained only through 2025-12-31;
- predicts every decision-ready race using only program/preview data;
- applies that day's results to learning/performance only after all predictions for the day;
- never feeds a race's result back into its own prediction;
- uses the current 4-pick / 1,200-yen allocation for purchase ROI reporting.

Historical closing odds are not part of the public JSON source, so the live odds
final gate is explicitly excluded from this backtest.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

JST = timezone(timedelta(hours=9))
API = "https://boatraceopenapi.github.io/api/v1/{year}/{day}.json"
USER_AGENT = "BOAT-AI-Historical-Backtest/1.0"
LANE_PRIOR = [0.55, 0.15, 0.12, 0.10, 0.05, 0.03]
BUY_THRESHOLD = 80
BUDGET = 1200
STAKE_BY_RANK = [500, 400, 200, 100]


def as_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        result = float(value)
        return default if math.isnan(result) else result
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_combo(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip().replace("=", "-").replace(" ", "")
    nums = re.findall(r"[1-6]", text)
    return "-".join(nums[:3]) if len(nums) >= 3 else None


def wind_bucket(wind: int) -> str:
    if wind <= 2:
        return "0-2"
    if wind <= 4:
        return "3-4"
    return "5+"


@dataclass
class Stats:
    races: int = 0
    hits: int = 0
    stake: int = 0
    payout: int = 0

    @property
    def hit_rate(self) -> float:
        return self.hits * 100.0 / self.races if self.races else 0.0

    @property
    def roi(self) -> float:
        return self.payout * 100.0 / self.stake if self.stake else 0.0

    def add(self, hit: bool, stake: int, payout: int) -> None:
        self.races += 1
        self.hits += int(hit)
        self.stake += stake
        self.payout += payout


class PerformanceProfile:
    def __init__(self) -> None:
        self.overall = Stats()
        self.by_rank: dict[str, Stats] = defaultdict(Stats)
        self.by_venue: dict[int, Stats] = defaultdict(Stats)
        self.by_lane: dict[int, Stats] = defaultdict(Stats)
        self.by_context: dict[str, Stats] = defaultdict(Stats)

    @staticmethod
    def rank_for(confidence: int) -> str:
        if confidence >= 90:
            return "S"
        if confidence >= 80:
            return "A"
        if confidence >= 70:
            return "B"
        if confidence >= 60:
            return "C"
        return "D"

    @staticmethod
    def poor_penalty(stats: Stats | None, minimum: int) -> int:
        if stats is None or stats.races < minimum:
            return 0
        if stats.roi < 60:
            return -7
        if stats.roi < 75:
            return -5
        if stats.roi < 88:
            return -3
        if stats.roi < 95:
            return -1
        return 0

    @staticmethod
    def should_skip(stats: Stats | None, minimum: int) -> bool:
        return bool(
            stats
            and stats.races >= minimum
            and (stats.roi < 65.0 or (stats.roi < 80.0 and stats.hit_rate < 10.0))
        )

    def penalty(self, venue: int, raw: int, lane: int | None) -> int:
        rank = self.rank_for(raw)
        values = [
            self.poor_penalty(self.by_venue.get(venue), 20),
            self.poor_penalty(self.by_rank.get(rank), 24),
            self.poor_penalty(self.by_lane.get(lane) if lane else None, 24),
            self.poor_penalty(self.by_context.get(f"{venue}:{rank}:{lane}") if lane else None, 12),
        ]
        return max(-18, min(0, sum(values)))

    def auto_skip(self, venue: int, raw: int, lane: int | None) -> bool:
        if lane is None:
            return False
        rank = self.rank_for(raw)
        if self.should_skip(self.by_context.get(f"{venue}:{rank}:{lane}"), 18):
            return True
        if self.should_skip(self.by_venue.get(venue), 40):
            return True
        if self.should_skip(self.by_rank.get(rank), 50):
            return True
        if self.should_skip(self.by_lane.get(lane), 40):
            return True
        return False

    def observe(self, venue: int, raw: int, lane: int | None, hit: bool, stake: int, payout: int) -> None:
        rank = self.rank_for(raw)
        targets = [self.overall, self.by_rank[rank], self.by_venue[venue]]
        if lane is not None:
            targets += [self.by_lane[lane], self.by_context[f"{venue}:{rank}:{lane}"]]
        for stats in targets:
            stats.add(hit, stake, payout)


class LearningProfile:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.starts = {str(k): int(v) for k, v in payload.get("starts", {}).items()}
        self.wins = {str(k): int(v) for k, v in payload.get("wins", {}).items()}
        self.wind_starts = {str(k): int(v) for k, v in payload.get("windCourseStarts", {}).items()}
        self.wind_wins = {str(k): int(v) for k, v in payload.get("windCourseWins", {}).items()}
        self.historical_race_count = int(payload.get("historicalRaceCount", 0))

    def lane_bonus(self, venue: int, lane: int) -> float:
        lane = max(1, min(6, lane))
        key = f"{venue}-{lane}"
        baseline = LANE_PRIOR[lane - 1]
        count = self.starts.get(key, 0)
        won = self.wins.get(key, 0)
        posterior = (won + baseline * 12.0) / (count + 12.0)
        return max(-8.0, min(8.0, (posterior - baseline) * 40.0))

    def bonus(self, venue: int, lane: int, wind: int | None, course: int | None) -> float:
        venue_lane = self.lane_bonus(venue, lane)
        if wind is None:
            return venue_lane
        actual_course = course if course and 1 <= course <= 6 else max(1, min(6, lane))
        key = f"{venue}-{wind_bucket(wind)}-{actual_course}"
        count = self.wind_starts.get(key, 0)
        if count < 4:
            return venue_lane
        won = self.wind_wins.get(key, 0)
        baseline = LANE_PRIOR[actual_course - 1]
        posterior = (won + baseline * 10.0) / (count + 10.0)
        contextual = max(-5.0, min(5.0, (posterior - baseline) * 30.0))
        return max(-10.0, min(10.0, venue_lane + contextual))

    def observe_race(self, race: dict[str, Any]) -> None:
        result_combo, _ = race_result(race)
        if not result_combo:
            return
        winner = as_int(result_combo.split("-")[0])
        venue = as_int(race.get("stadium_number"))
        if venue is None or winner is None or not (1 <= venue <= 24 and 1 <= winner <= 6):
            return
        racers = race_racers(race)
        if len(racers) < 3:
            return
        self.historical_race_count += 1
        for racer in racers:
            lane = racer["lane"]
            key = f"{venue}-{lane}"
            self.starts[key] = self.starts.get(key, 0) + 1
        winner_key = f"{venue}-{winner}"
        self.wins[winner_key] = self.wins.get(winner_key, 0) + 1

        preview = race.get("preview") or {}
        wind = as_int(preview.get("wind_speed"))
        if wind is None:
            return
        for racer in racers:
            course = racer.get("course") or racer["lane"]
            if 1 <= course <= 6:
                key = f"{venue}-{wind_bucket(wind)}-{course}"
                self.wind_starts[key] = self.wind_starts.get(key, 0) + 1
        winner_racer = next((r for r in racers if r["lane"] == winner), None)
        winning_course = (winner_racer or {}).get("course") or winner
        key = f"{venue}-{wind_bucket(wind)}-{winning_course}"
        self.wind_wins[key] = self.wind_wins.get(key, 0) + 1


def race_racers(race: dict[str, Any]) -> list[dict[str, Any]]:
    racers_obj = race.get("racers") or {}
    preview_racers = ((race.get("preview") or {}).get("racers") or {})
    racers: list[dict[str, Any]] = []
    for lane in range(1, 7):
        raw = racers_obj.get(str(lane)) or racers_obj.get(lane)
        if not isinstance(raw, dict):
            continue
        pr = preview_racers.get(str(lane)) or preview_racers.get(lane) or {}
        racers.append(
            {
                "lane": lane,
                "average_start": as_float(raw.get("average_start_timing")),
                "national_win": as_float(raw.get("national_win_rate")),
                "local_win": as_float(raw.get("local_win_rate")),
                "motor_top2": as_float(raw.get("motor_top_2_percent")),
                "boat_top2": as_float(raw.get("boat_top_2_percent")),
                "course": as_int(pr.get("course_number")),
                "preview_start": as_float(pr.get("start_timing")),
                "exhibition": as_float(pr.get("exhibition_time")),
            }
        )
    return racers


def racer_score(r: dict[str, Any]) -> float:
    lane = r["lane"]
    lane_base = {1: 30.0, 2: 18.0, 3: 14.0, 4: 10.0, 5: 7.0}.get(lane, 5.0)
    national = (r.get("national_win") or 0.0) * 5.2
    local = (r.get("local_win") or 0.0) * 2.6
    motor = (r.get("motor_top2") or 0.0) * 0.22
    boat = (r.get("boat_top2") or 0.0) * 0.08
    avg_start = r.get("average_start")
    start = max(0.0, (0.22 - avg_start) * 58.0) if avg_start is not None else 0.0
    exhibition = r.get("exhibition")
    exhibition_score = max(-5.0, (6.95 - exhibition) * 18.0) if exhibition is not None else 0.0
    preview_start = r.get("preview_start")
    preview_start_score = max(-4.0, (0.18 - preview_start) * 32.0) if preview_start is not None else 0.0
    course = r.get("course")
    course_score = {1: 7.0, 2: 3.5, 3: 2.0, 4: 0.5, 5: -1.0, 6: -2.0}.get(course, 0.0)
    return lane_base + national + local + motor + boat + start + exhibition_score + preview_start_score + course_score


def scored_racers(race: dict[str, Any], learning: LearningProfile) -> list[tuple[dict[str, Any], float]]:
    venue = as_int(race.get("stadium_number"), 0) or 0
    wind = as_int((race.get("preview") or {}).get("wind_speed"))
    values = []
    for racer in race_racers(race):
        score = racer_score(racer) + learning.bonus(venue, racer["lane"], wind, racer.get("course"))
        values.append((racer, score))
    return sorted(values, key=lambda x: x[1], reverse=True)


def raw_confidence(race: dict[str, Any], learning: LearningProfile) -> tuple[int, int | None, dict[int, float]]:
    scored = scored_racers(race, learning)
    if len(scored) < 3:
        return 0, None, {}
    leader, runner = scored[0], scored[1]
    score_gap = max(0.0, leader[1] - runner[1])
    win_gap = max(0.0, (leader[0].get("national_win") or 0.0) - (runner[0].get("national_win") or 0.0))
    motor_gap = max(0.0, (leader[0].get("motor_top2") or 0.0) - (runner[0].get("motor_top2") or 0.0))
    start_edge = max(0.0, (runner[0].get("average_start") or 0.20) - (leader[0].get("average_start") or 0.20))
    lane_bonus = {1: 12.0, 2: 5.0, 3: 2.0}.get(leader[0]["lane"], 0.0)
    times = [r.get("exhibition") for r, _ in scored if r.get("exhibition") is not None]
    preview_spread = (max(times) - min(times)) * 18.0 if len(times) >= 3 else 0.0
    raw = int(32.0 + score_gap * 2.25 + win_gap * 2.8 + motor_gap * 0.32 + start_edge * 90.0 + lane_bonus + preview_spread)
    raw = max(35, min(97, raw))
    return raw, leader[0]["lane"], {r["lane"]: score for r, score in scored}


def decision_ready(race: dict[str, Any]) -> bool:
    racers = race_racers(race)
    if len(racers) != 6 or not isinstance(race.get("preview"), dict):
        return False
    ready = sum(1 for r in racers if r.get("exhibition") is not None and r.get("course") is not None)
    return ready >= 5


def buy_threshold(race: dict[str, Any], leader_lane: int | None) -> int:
    threshold = BUY_THRESHOLD
    preview = race.get("preview") or {}
    wind = as_int(preview.get("wind_speed"), 0) or 0
    wave = as_int(preview.get("wave_height"), 0) or 0
    if wind >= 5:
        threshold += 4
    if wave >= 8:
        threshold += 2
    if leader_lane is not None:
        leader = next((r for r in race_racers(race) if r["lane"] == leader_lane), None)
        if leader and leader.get("course") is not None and leader["course"] != leader_lane:
            threshold += 3
    return min(90, threshold)


def top_picks(score_map: dict[int, float]) -> list[str]:
    picks: list[tuple[str, float]] = []
    lanes = sorted(score_map)
    for first in lanes:
        for second in lanes:
            if second == first:
                continue
            for third in lanes:
                if third in (first, second):
                    continue
                score = score_map[first] + score_map[second] * 0.58 + score_map[third] * 0.31
                picks.append((f"{first}-{second}-{third}", score))
    picks.sort(key=lambda x: x[1], reverse=True)
    return [combo for combo, _ in picks[:4]]


def race_result(race: dict[str, Any]) -> tuple[str | None, int]:
    result = race.get("result") or {}
    payouts = result.get("payouts") or {}
    trifecta = payouts.get("trifecta") or []
    first = trifecta[0] if isinstance(trifecta, list) and trifecta else None
    if not isinstance(first, dict):
        return None, 0
    return normalize_combo(first.get("combination")), as_int(first.get("amount"), 0) or 0


def parse_day(root: dict[str, Any]) -> list[dict[str, Any]]:
    stadiums = (((root.get("programs") or {}).get("stadiums")) or {})
    races: list[dict[str, Any]] = []
    for venue_key, stadium in stadiums.items():
        if not isinstance(stadium, dict):
            continue
        venue = as_int(venue_key)
        for race_key, race in ((stadium.get("races") or {}).items()):
            if not isinstance(race, dict):
                continue
            copy = dict(race)
            copy["stadium_number"] = as_int(copy.get("stadium_number"), venue) or venue
            copy["race_number"] = as_int(copy.get("race_number"), as_int(race_key))
            races.append(copy)
    return races


def fetch_day(day: date, attempts: int = 3) -> tuple[date, dict[str, Any] | None, str | None]:
    url = API.format(year=day.year, day=day.strftime("%Y%m%d"))
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=30) as response:
                return day, json.load(response), None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return day, None, "404"
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(attempt * 0.8)
    return day, None, last_error or "unknown error"


def monthly_bucket(year: int, month: int) -> dict[str, Any]:
    return {
        "year": year,
        "month": month,
        "totalSettledRaces": 0,
        "evaluatedRaces": 0,
        "purchaseRaces": 0,
        "skippedRaces": 0,
        "unavailableRaces": 0,
        "purchaseHits": 0,
        "allPredictionHits": 0,
        "skippedPredictionHits": 0,
        "stake": 0,
        "payout": 0,
    }


def finalize(bucket: dict[str, Any]) -> dict[str, Any]:
    out = dict(bucket)
    stake = int(out.get("stake", 0))
    payout = int(out.get("payout", 0))
    purchase = int(out.get("purchaseRaces", 0))
    hits = int(out.get("purchaseHits", 0))
    out["profit"] = payout - stake
    out["roi"] = round(payout * 100.0 / stake, 1) if stake else 0.0
    out["hitRate"] = round(hits * 100.0 / purchase, 1) if purchase else 0.0
    evaluated = int(out.get("evaluatedRaces", 0))
    out["purchaseRate"] = round(purchase * 100.0 / evaluated, 1) if evaluated else 0.0
    return out


def merge_buckets(buckets: list[dict[str, Any]], year: int) -> dict[str, Any]:
    result = monthly_bucket(year, 0)
    result.pop("month", None)
    for bucket in buckets:
        for key in (
            "totalSettledRaces", "evaluatedRaces", "purchaseRaces", "skippedRaces",
            "unavailableRaces", "purchaseHits", "allPredictionHits", "skippedPredictionHits",
            "stake", "payout",
        ):
            result[key] += int(bucket.get(key, 0))
    return finalize(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, default=2026)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2026, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat)
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    today_jst = datetime.now(JST).date()
    data_end = args.end or min(today_jst - timedelta(days=1), date(args.year, 12, 31))
    if data_end < args.start:
        raise SystemExit("backtest end is before start")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    performance = PerformanceProfile()

    dates: list[date] = []
    cursor = args.start
    while cursor <= data_end:
        dates.append(cursor)
        cursor += timedelta(days=1)

    day_payloads: dict[date, dict[str, Any]] = {}
    failed_days: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_day, day): day for day in dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                day_payloads[day] = payload
            elif error != "404":
                failed_days[day.isoformat()] = error or "unknown"

    months: dict[int, dict[str, Any]] = {
        month: monthly_bucket(args.year, month)
        for month in range(args.start.month, data_end.month + 1)
    }

    processed_days = 0
    for day in dates:
        root = day_payloads.get(day)
        if root is None:
            continue
        processed_days += 1
        races = parse_day(root)
        day_observations: list[tuple[int, int, int | None, bool, int, int]] = []

        for race in races:
            combo, trifecta_amount = race_result(race)
            if not combo or trifecta_amount <= 0:
                continue
            month = day.month
            bucket = months.setdefault(month, monthly_bucket(args.year, month))
            bucket["totalSettledRaces"] += 1

            if not decision_ready(race):
                bucket["unavailableRaces"] += 1
                continue

            raw, leader_lane, score_map = raw_confidence(race, learning)
            picks = top_picks(score_map)
            if raw == 0 or not picks:
                bucket["unavailableRaces"] += 1
                continue

            venue = as_int(race.get("stadium_number"), 0) or 0
            first_lane = as_int(picks[0].split("-")[0])
            penalty = performance.penalty(venue, raw, first_lane)
            confidence = max(20, min(97, raw + penalty))
            skip_by_history = performance.auto_skip(venue, raw, first_lane)
            recommended = (not skip_by_history) and confidence >= buy_threshold(race, leader_lane)

            bucket["evaluatedRaces"] += 1
            hit = combo in picks
            if hit:
                bucket["allPredictionHits"] += 1

            # Match current app's performance-memory semantics: 300 yen per each of four picks.
            perf_payout = trifecta_amount * 3 if hit else 0
            day_observations.append((venue, raw, first_lane, hit, 1200, perf_payout))

            if recommended:
                bucket["purchaseRaces"] += 1
                bucket["stake"] += BUDGET
                if hit:
                    bucket["purchaseHits"] += 1
                    winning_index = picks.index(combo)
                    winning_stake = STAKE_BY_RANK[min(winning_index, len(STAKE_BY_RANK) - 1)]
                    bucket["payout"] += trifecta_amount * (winning_stake // 100)
            else:
                bucket["skippedRaces"] += 1
                if hit:
                    bucket["skippedPredictionHits"] += 1

        # Apply same-day outcomes only after every race on that day has been predicted.
        for race in races:
            learning.observe_race(race)
        for observation in day_observations:
            performance.observe(*observation)

    finalized_months = [finalize(months[m]) for m in sorted(months)]
    year_summary = merge_buckets(finalized_months, args.year)

    payload = {
        "schemaVersion": 1,
        "year": args.year,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataFrom": args.start.isoformat(),
        "dataThrough": data_end.isoformat(),
        "processedDays": processed_days,
        "failedDays": failed_days,
        "simulationBudget": BUDGET,
        "oddsFinalGateIncluded": False,
        "method": "walk-forward daily; pre-2026 learning only; same-day results applied next day",
        "notes": [
            "Official historical program, preview, weather and result data are used.",
            "Results are never used to predict the same day; each day's outcomes update the next day's model.",
            "Historical closing odds are unavailable in this source, so the live odds final gate is excluded.",
            "Purchase ROI uses the current 4-pick 1,200-yen allocation: 500/400/200/100 yen by prediction rank.",
        ],
        "months": finalized_months,
        "yearSummary": year_summary,
    }

    if year_summary["totalSettledRaces"] <= 0:
        raise SystemExit("no settled races were found")
    if year_summary["evaluatedRaces"] <= 0:
        raise SystemExit("no decision-ready races were evaluated")
    if failed_days:
        print(f"warning: {len(failed_days)} download failures", flush=True)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "dataThrough": payload["dataThrough"],
        "processedDays": processed_days,
        "totalSettledRaces": year_summary["totalSettledRaces"],
        "evaluatedRaces": year_summary["evaluatedRaces"],
        "purchaseRaces": year_summary["purchaseRaces"],
        "skippedRaces": year_summary["skippedRaces"],
        "purchaseHits": year_summary["purchaseHits"],
        "hitRate": year_summary["hitRate"],
        "roi": year_summary["roi"],
        "profit": year_summary["profit"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
