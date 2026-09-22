#!/usr/bin/env python3
"""Tune a market-edge betting strategy with archived pre-close trifecta odds.

Parameters are fitted ONLY on 2026-07-19..2026-08-31. September is an untouched
holdout and is never used to choose a candidate. Race learning and performance
memory remain walk-forward; same-day results are applied after the whole day.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import math
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
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
    race_result,
    raw_confidence,
    top_picks,
)

ODDS_FROM = date(2026, 7, 19)
TUNE_THROUGH = date(2026, 8, 31)
HOLDOUT_FROM = date(2026, 9, 1)
ODDS_URL = (
    "https://raw.githubusercontent.com/BoatraceCSV/boatracecsv.github.io/"
    "main/data/previews/od3/{year}/{month:02d}/{day:02d}.csv"
)
USER_AGENT = "BOAT-AI-Market-Edge/1.1"

STAKE_PLANS: dict[str, tuple[int, ...]] = {
    "equal3": (400, 400, 400),
    "balanced3": (500, 400, 300),
    "equal4": (300, 300, 300, 300),
}
TEMPERATURES = (8, 12, 16, 20, 24, 32)
EDGE_MINS = (1.00, 1.10, 1.20, 1.30, 1.45, 1.60)
EV_MINS = (1.00, 1.05, 1.10, 1.20)
MODEL_RANKS = (12, 20, 30)


@dataclass(frozen=True)
class Candidate:
    temperature: int
    edge_min: float
    ev_min: float
    max_model_rank: int
    plan: str
    require_pre_recommend: bool


@dataclass
class Stats:
    races: int = 0
    hits: int = 0
    stake: int = 0
    payout: int = 0

    def add(self, hit: bool, paid: int) -> None:
        self.races += 1
        self.hits += int(hit)
        self.stake += BUDGET
        self.payout += paid

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


def candidate_grid() -> list[Candidate]:
    return [
        Candidate(temp, edge, ev, rank, plan, require)
        for temp in TEMPERATURES
        for edge in EDGE_MINS
        for ev in EV_MINS
        for rank in MODEL_RANKS
        for plan in STAKE_PLANS
        for require in (True, False)
    ]


def fetch_odds_day(
    day: date, attempts: int = 3
) -> tuple[date, dict[str, dict[str, float]] | None, str | None]:
    url = ODDS_URL.format(year=day.year, month=day.month, day=day.day)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv"}
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                text = response.read().decode("utf-8-sig")
            rows: dict[str, dict[str, float]] = {}
            for row in csv.DictReader(io.StringIO(text)):
                code = (row.get("レースコード") or "").strip()
                if len(code) != 12:
                    continue
                values: dict[str, float] = {}
                for key, raw in row.items():
                    if not key.startswith("3連単_") or not raw:
                        continue
                    try:
                        value = float(raw)
                    except ValueError:
                        continue
                    if value > 1.0:
                        values[key.removeprefix("3連単_")] = value
                if len(values) >= 100:
                    rows[code] = values
            return day, rows, None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return day, None, "404"
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(attempt * 0.7)
    return day, None, last_error or "unknown"


def race_code(day: date, race: dict[str, Any]) -> str | None:
    venue = as_int(race.get("stadium_number"))
    race_no = as_int(race.get("race_number"))
    if venue is None or race_no is None:
        return None
    return f"{day:%Y%m%d}{venue:02d}{race_no:02d}"


def trifecta_probabilities(
    score_map: dict[int, float], temperature: int
) -> dict[str, float]:
    lanes = sorted(score_map)
    if len(lanes) != 6:
        return {}
    max_score = max(score_map.values())
    weights = {
        lane: math.exp((score_map[lane] - max_score) / float(temperature))
        for lane in lanes
    }
    total = sum(weights.values())
    result: dict[str, float] = {}
    for first in lanes:
        p1 = weights[first] / total
        rem1 = total - weights[first]
        for second in lanes:
            if second == first:
                continue
            p2 = weights[second] / rem1
            rem2 = rem1 - weights[second]
            for third in lanes:
                if third in (first, second):
                    continue
                p3 = weights[third] / rem2
                result[f"{first}-{second}-{third}"] = p1 * p2 * p3
    return result


def market_probabilities(odds: dict[str, float]) -> dict[str, float]:
    inverse = {combo: 1.0 / value for combo, value in odds.items() if value > 1.0}
    total = sum(inverse.values())
    if total <= 0:
        return {}
    return {combo: value / total for combo, value in inverse.items()}


def selection_cache_for_race(
    probability_cache: dict[int, dict[str, float]],
    market_probs: dict[str, float],
    odds: dict[str, float],
) -> dict[tuple[int, float, float, int], list[str]]:
    cache: dict[tuple[int, float, float, int], list[str]] = {}
    for temp, model_probs in probability_cache.items():
        ranked = sorted(model_probs, key=model_probs.get, reverse=True)
        for max_rank in MODEL_RANKS:
            allowed = ranked[:max_rank]
            rows: list[tuple[str, float, float, float]] = []
            for combo in allowed:
                model_p = model_probs.get(combo, 0.0)
                market_p = market_probs.get(combo, 0.0)
                price = odds.get(combo, 0.0)
                if model_p <= 0 or market_p <= 0 or price <= 1.0:
                    continue
                edge = model_p / market_p
                expected_return = model_p * price
                rows.append((combo, expected_return, edge, model_p))
            rows.sort(key=lambda row: (row[1], row[2], row[3]), reverse=True)
            for edge_min in EDGE_MINS:
                for ev_min in EV_MINS:
                    selected = [
                        combo
                        for combo, ev, edge, _ in rows
                        if edge >= edge_min and ev >= ev_min
                    ][:4]
                    cache[(temp, edge_min, ev_min, max_rank)] = selected
    return cache


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    today_jst = datetime.now(JST).date()
    end = min(today_jst - timedelta(days=1), date(2026, 12, 31))
    dates: list[date] = []
    cursor = date(2026, 1, 1)
    while cursor <= end:
        dates.append(cursor)
        cursor += timedelta(days=1)

    race_payloads: dict[date, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_day, day): day for day in dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                race_payloads[day] = payload
            elif error != "404":
                raise SystemExit(f"race download failed {day}: {error}")

    odds_dates = [day for day in dates if day >= ODDS_FROM]
    odds_payloads: dict[date, dict[str, dict[str, float]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
        futures = {pool.submit(fetch_odds_day, day): day for day in odds_dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                odds_payloads[day] = payload
            elif error != "404":
                raise SystemExit(f"odds download failed {day}: {error}")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    performance = PerformanceProfile()
    grid = candidate_grid()
    tune = {candidate: Stats() for candidate in grid}
    holdout = {candidate: Stats() for candidate in grid}
    matched = 0

    for day in dates:
        root = race_payloads.get(day)
        if root is None:
            continue
        races = parse_day(root)
        day_odds = odds_payloads.get(day, {})
        observations: list[tuple[int, int, int | None, bool, int, int]] = []

        for race in races:
            combo, result_amount = race_result(race)
            if not combo or result_amount <= 0 or not decision_ready(race):
                continue
            raw, leader_lane, score_map = raw_confidence(race, learning)
            if raw == 0 or len(score_map) != 6:
                continue

            venue = as_int(race.get("stadium_number"), 0) or 0
            penalty = performance.penalty(venue, raw, leader_lane)
            confidence = max(20, min(97, raw + penalty))
            skip_by_history = performance.auto_skip(venue, raw, leader_lane)
            pre_recommended = (
                not skip_by_history
                and confidence >= buy_threshold(race, leader_lane)
            )

            base_picks = top_picks(score_map)
            perf_hit = combo in base_picks
            perf_paid = result_amount * 3 if perf_hit else 0
            observations.append(
                (venue, raw, leader_lane, perf_hit, BUDGET, perf_paid)
            )

            if day < ODDS_FROM:
                continue
            code = race_code(day, race)
            odds = day_odds.get(code or "")
            if not odds:
                continue
            market_probs = market_probabilities(odds)
            if len(market_probs) < 100:
                continue

            matched += 1
            probability_cache = {
                temp: trifecta_probabilities(score_map, temp)
                for temp in TEMPERATURES
            }
            selections = selection_cache_for_race(
                probability_cache, market_probs, odds
            )
            target = tune if day <= TUNE_THROUGH else holdout

            for candidate in grid:
                if candidate.require_pre_recommend and not pre_recommended:
                    continue
                base_selection = selections[
                    (
                        candidate.temperature,
                        candidate.edge_min,
                        candidate.ev_min,
                        candidate.max_model_rank,
                    )
                ]
                stakes = STAKE_PLANS[candidate.plan]
                picks = base_selection[: len(stakes)]
                if len(picks) != len(stakes):
                    continue
                if combo in picks:
                    index = picks.index(combo)
                    paid = result_amount * (stakes[index] // 100)
                    target[candidate].add(True, paid)
                else:
                    target[candidate].add(False, 0)

        # Update only after all same-day predictions have been evaluated.
        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)

    rows: list[dict[str, Any]] = []
    for candidate in grid:
        train_payload = tune[candidate].payload()
        holdout_payload = holdout[candidate].payload()
        rows.append(
            {
                "candidate": asdict(candidate),
                "stakes": list(STAKE_PLANS[candidate.plan]),
                "tune": train_payload,
                "holdout": holdout_payload,
            }
        )

    # STRICT selection: only July-August is used to choose the one candidate.
    eligible_tune = [row for row in rows if row["tune"]["races"] >= 120]
    eligible_tune.sort(
        key=lambda row: (row["tune"]["roi"], row["tune"]["races"]),
        reverse=True,
    )
    selected = eligible_tune[0] if eligible_tune else None
    selected_passes_holdout = bool(
        selected
        and selected["tune"]["roi"] > 100.0
        and selected["holdout"]["races"] >= 60
        and selected["holdout"]["roi"] > 100.0
    )

    # Diagnostics only; never used for choosing production parameters.
    stable_positive = [
        row
        for row in rows
        if row["tune"]["races"] >= 120
        and row["holdout"]["races"] >= 60
        and row["tune"]["roi"] > 100.0
        and row["holdout"]["roi"] > 100.0
    ]
    stable_positive.sort(
        key=lambda row: min(row["tune"]["roi"], row["holdout"]["roi"]),
        reverse=True,
    )

    payload = {
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "oddsDataFrom": min(odds_payloads).isoformat() if odds_payloads else None,
        "oddsDataThrough": max(odds_payloads).isoformat() if odds_payloads else None,
        "tuneFrom": ODDS_FROM.isoformat(),
        "tuneThrough": TUNE_THROUGH.isoformat(),
        "holdoutFrom": HOLDOUT_FROM.isoformat(),
        "matchedRaces": matched,
        "candidateCount": len(grid),
        "selectionRule": (
            "highest July-August ROI with >=120 tune races; September never used "
            "to choose parameters"
        ),
        "selectedFromTune": selected,
        "selectedPassesHoldout": selected_passes_holdout,
        "diagnosticStablePositiveCount": len(stable_positive),
        "diagnosticStablePositive": stable_positive[:20],
        "topTune": eligible_tune[:30],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "matchedRaces": matched,
                "candidateCount": len(grid),
                "selectedFromTune": selected,
                "selectedPassesHoldout": selected_passes_holdout,
                "diagnosticStablePositiveCount": len(stable_positive),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
