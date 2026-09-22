#!/usr/bin/env python3
"""Backtest BOAT AI purchase gates with archived pre-close trifecta odds.

Odds source: BoatraceCSV od3, one snapshot per race around five minutes before close.
Gate tuning: 2026-07-19..2026-08-31.
Final holdout: 2026-09-01..latest available day.

The race prediction model is walked forward from 2026-01-01 so the July model
state includes only prior settled races. Same-day outcomes update learning and
performance only after all races for that day have been predicted.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import time
import urllib.error
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from build_2026_backtest import (
    JST,
    BUDGET,
    STAKE_BY_RANK,
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
ODDS_URL = "https://raw.githubusercontent.com/BoatraceCSV/boatracecsv.github.io/main/data/previews/od3/{year}/{month:02d}/{day:02d}.csv"
USER_AGENT = "BOAT-AI-Odds-Backtest/1.0"


@dataclass(frozen=True)
class Gate:
    main_ratio: float
    secondary_ratio: float
    secondary_count: int


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


def gate_grid() -> list[Gate]:
    return [
        Gate(main, secondary, count)
        for main in (1.0, 1.2, 1.3, 1.5, 1.7, 2.0, 2.3)
        for secondary in (1.0, 1.2, 1.4, 1.6, 2.0, 2.5, 3.0)
        for count in (1, 2, 3, 4)
    ]


def current_android_gate(odds: list[float], stakes: list[int]) -> bool:
    if len(odds) != len(stakes) or not odds:
        return False
    total = max(1, sum(stakes))
    returns = [o * s for o, s in zip(odds, stakes)]
    main_return = returns[0]
    profitable_count = sum(1 for value in returns if value >= total * 1.20)
    strong_upside_count = sum(1 for value in returns if value >= total * 2.0)
    if all(value < total for value in returns):
        return False
    if main_return >= total * 1.50 and profitable_count >= 2:
        return True
    if main_return >= total * 1.30 and strong_upside_count >= 2:
        return True
    return False


def generic_gate(gate: Gate, odds: list[float], stakes: list[int]) -> bool:
    if len(odds) != len(stakes) or not odds:
        return False
    total = max(1, sum(stakes))
    returns = [o * s for o, s in zip(odds, stakes)]
    if returns[0] < total * gate.main_ratio:
        return False
    return sum(1 for value in returns if value >= total * gate.secondary_ratio) >= gate.secondary_count


def fetch_odds_day(day: date, attempts: int = 3) -> tuple[date, dict[str, dict[str, float]] | None, str | None]:
    url = ODDS_URL.format(year=day.year, month=day.month, day=day.day)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv"})
            with urllib.request.urlopen(req, timeout=30) as response:
                text = response.read().decode("utf-8-sig")
            rows: dict[str, dict[str, float]] = {}
            for row in csv.DictReader(io.StringIO(text)):
                code = (row.get("レースコード") or "").strip()
                if len(code) != 12:
                    continue
                values: dict[str, float] = {}
                for key, raw in row.items():
                    if not key.startswith("3連単_") or raw in (None, ""):
                        continue
                    try:
                        odds = float(raw)
                    except ValueError:
                        continue
                    if odds > 0:
                        values[key.removeprefix("3連単_")] = odds
                if values:
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
    rno = as_int(race.get("race_number"))
    if venue is None or rno is None:
        return None
    return f"{day:%Y%m%d}{venue:02d}{rno:02d}"


def winning_payout(combo: str, result_amount: int, picks: list[str], stakes: list[int]) -> tuple[bool, int]:
    if combo not in picks:
        return False, 0
    index = picks.index(combo)
    return True, result_amount * (stakes[index] // 100)


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
    if end < HOLDOUT_FROM:
        raise SystemExit("holdout period has not started")

    dates: list[date] = []
    cursor = args.start
    while cursor <= end:
        dates.append(cursor)
        cursor += timedelta(days=1)

    race_payloads: dict[date, dict[str, Any]] = {}
    race_failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_day, day): day for day in dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                race_payloads[day] = payload
            elif error != "404":
                race_failures[day.isoformat()] = error or "unknown"
    if race_failures:
        raise SystemExit(f"race download failures: {race_failures}")

    odds_dates = [day for day in dates if ODDS_FROM <= day <= end]
    odds_payloads: dict[date, dict[str, dict[str, float]]] = {}
    odds_failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
        futures = {pool.submit(fetch_odds_day, day): day for day in odds_dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                odds_payloads[day] = payload
            elif error != "404":
                odds_failures[day.isoformat()] = error or "unknown"
    if odds_failures:
        raise SystemExit(f"odds download failures: {odds_failures}")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    performance = PerformanceProfile()
    gates = gate_grid()
    tune_stats = {gate: Stats() for gate in gates}
    holdout_stats = {gate: Stats() for gate in gates}
    current_tune = Stats()
    current_holdout = Stats()

    settled = 0
    pre_odds_recommended = 0
    odds_matched = 0
    tune_matched = 0
    holdout_matched = 0

    for day in dates:
        root = race_payloads.get(day)
        if root is None:
            continue
        races = parse_day(root)
        observations: list[tuple[int, int, int | None, bool, int, int]] = []
        day_odds = odds_payloads.get(day, {})

        for race in races:
            combo, result_amount = race_result(race)
            if not combo or result_amount <= 0:
                continue
            settled += 1
            if not decision_ready(race):
                continue
            raw, leader_lane, score_map = raw_confidence(race, learning)
            picks = top_picks(score_map)
            if raw == 0 or len(picks) < 4:
                continue

            venue = as_int(race.get("stadium_number"), 0) or 0
            first_lane = as_int(picks[0].split("-")[0])
            penalty = performance.penalty(venue, raw, first_lane)
            confidence = max(20, min(97, raw + penalty))
            skip_by_history = performance.auto_skip(venue, raw, first_lane)
            recommended = (not skip_by_history) and confidence >= buy_threshold(race, leader_lane)

            perf_hit = combo in picks
            perf_paid = result_amount * 3 if perf_hit else 0
            observations.append((venue, raw, first_lane, perf_hit, BUDGET, perf_paid))
            if not recommended:
                continue
            pre_odds_recommended += 1

            code = race_code(day, race)
            odds_map = day_odds.get(code or "")
            if not odds_map:
                continue
            selected_odds = [odds_map.get(pick) for pick in picks]
            if any(value is None for value in selected_odds):
                continue
            odds = [float(value) for value in selected_odds if value is not None]
            stakes = list(STAKE_BY_RANK[:4])
            odds_matched += 1
            hit, paid = winning_payout(combo, result_amount, picks, stakes)

            target = None
            current_target = None
            if ODDS_FROM <= day <= TUNE_THROUGH:
                target = tune_stats
                current_target = current_tune
                tune_matched += 1
            elif day >= HOLDOUT_FROM:
                target = holdout_stats
                current_target = current_holdout
                holdout_matched += 1
            if target is None or current_target is None:
                continue

            if current_android_gate(odds, stakes):
                current_target.add(hit, paid)
            for gate in gates:
                if generic_gate(gate, odds, stakes):
                    target[gate].add(hit, paid)

        # No same-day outcome is available to another race prediction in the backtest.
        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)

    rows: list[dict[str, Any]] = []
    for gate in gates:
        tr = tune_stats[gate].payload()
        va = holdout_stats[gate].payload()
        robust_roi = min(tr["roi"], va["roi"]) if tr["races"] and va["races"] else 0.0
        rows.append({
            "gate": asdict(gate),
            "tune": tr,
            "holdout": va,
            "robustRoi": robust_roi,
            "positiveBoth": tr["roi"] > 100.0 and va["roi"] > 100.0,
        })

    robust = [row for row in rows if row["tune"]["races"] >= 100 and row["holdout"]["races"] >= 50]
    robust.sort(key=lambda row: (row["positiveBoth"], row["robustRoi"], row["holdout"]["races"]), reverse=True)
    positive = [row for row in robust if row["positiveBoth"]]

    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "oddsSource": "BoatraceCSV od3 pre-close snapshot",
        "oddsDataFrom": min(odds_payloads).isoformat() if odds_payloads else None,
        "oddsDataThrough": max(odds_payloads).isoformat() if odds_payloads else None,
        "tuneFrom": ODDS_FROM.isoformat(),
        "tuneThrough": TUNE_THROUGH.isoformat(),
        "holdoutFrom": HOLDOUT_FROM.isoformat(),
        "settledRaces": settled,
        "preOddsRecommendedRaces": pre_odds_recommended,
        "oddsMatchedRecommendedRaces": odds_matched,
        "tuneMatched": tune_matched,
        "holdoutMatched": holdout_matched,
        "gateCount": len(gates),
        "minimumRobustSamples": {"tune": 100, "holdout": 50},
        "currentAndroidGate": {
            "tune": current_tune.payload(),
            "holdout": current_holdout.payload(),
        },
        "positiveRobustCount": len(positive),
        "topPositive": positive[:30],
        "topRobust": robust[:40],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "oddsDataFrom": payload["oddsDataFrom"],
        "oddsDataThrough": payload["oddsDataThrough"],
        "oddsMatchedRecommendedRaces": odds_matched,
        "currentAndroidGate": payload["currentAndroidGate"],
        "positiveRobustCount": len(positive),
        "best": robust[0] if robust else None,
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
