#!/usr/bin/env python3
"""Walk-forward BOAT AI value-betting search using archived historical trifecta odds.

Protocol:
- Jan-Apr starts the conditional finish-order model.
- May-Aug are walk-forward development months; each month is predicted by a model
  trained only through the preceding month.
- Archived trifecta odds are joined by date/stadium/race and are used only as
  pre-race market information for ticket selection.
- Sep-latest is evaluated only after May-Aug strategy selection is frozen.

Production remains on official BOAT RACE odds. This backtest uses the public
BoatraceOdds archive solely to evaluate the same value-selection concept historically.
"""

from __future__ import annotations

import argparse
import json
import math
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_2026_strategy as v6
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

BUDGET = 1200
BUDGET_UNITS = 12
DEV_MONTHS = (5, 6, 7, 8)
ALPHAS = (0.35, 0.50, 0.65, 0.80, 1.00)
MIN_EV_OPTIONS = (1.02, 1.05, 1.10, 1.15, 1.20, 1.30)
MIN_PROB_OPTIONS = (0.005, 0.010, 0.020, 0.030)
MAX_ODDS_OPTIONS = (20.0, 40.0, 80.0, 150.0, 9999.0)
POINT_OPTIONS = (1, 2, 3, 4, 6, 8, 10)
ALLOCATION_MODES = ("equal", "probability", "edge")
KEEP_GATES = 50
MIN_MONTH_BUYS = 20
MIN_DEV_BUYS = 120
ODDS_URL = "https://raw.githubusercontent.com/lamrongol/BoatraceOdds/gh-pages/docs/v3/2026/{day}.json"
USER_AGENT = "BOAT-AI-Value-Backtest/1.0"


def month_end(month: int) -> date:
    return date(2026, month + 1, 1) - timedelta(days=1) if month < 12 else date(2026, 12, 31)


def empty_stats() -> dict[str, int]:
    return {"purchaseRaces": 0, "hits": 0, "stake": 0, "payout": 0, "bets": 0}


def finalize(raw: dict[str, int]) -> dict[str, Any]:
    stake = int(raw["stake"])
    payout = int(raw["payout"])
    buys = int(raw["purchaseRaces"])
    hits = int(raw["hits"])
    return {
        **raw,
        "profit": payout - stake,
        "roi": round(payout * 100.0 / stake, 1) if stake else 0.0,
        "hitRate": round(hits * 100.0 / buys, 1) if buys else 0.0,
        "avgPoints": round(raw["bets"] / buys, 2) if buys else 0.0,
    }


def combine(items: list[dict[str, Any]]) -> dict[str, Any]:
    raw = empty_stats()
    for item in items:
        for key in raw:
            raw[key] += int(item.get(key, 0))
    return finalize(raw)


def profitable(stats: dict[str, Any]) -> bool:
    return int(stats["purchaseRaces"]) > 0 and int(stats["profit"]) > 0 and float(stats["roi"]) > 100.0


def fetch_odds_day(day: date) -> tuple[date, dict[tuple[int, int], dict[str, float]], str | None]:
    url = ODDS_URL.format(day=day.strftime("%Y%m%d"))
    last_error: str | None = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            races: dict[tuple[int, int], dict[str, float]] = {}
            for race in payload.get("odds", []):
                venue = as_int(race.get("stadium_number"))
                number = as_int(race.get("number"))
                tri = race.get("trifecta_odds") or {}
                if venue is None or number is None or not isinstance(tri, dict):
                    continue
                flat: dict[str, float] = {}
                for first, seconds in tri.items():
                    if not isinstance(seconds, dict):
                        continue
                    for second, thirds in seconds.items():
                        if not isinstance(thirds, dict):
                            continue
                        for third, odd in thirds.items():
                            try:
                                value = float(odd)
                            except (TypeError, ValueError):
                                continue
                            if value > 0:
                                flat[f"{int(first)}-{int(second)}-{int(third)}"] = value
                if flat:
                    races[(int(venue), int(number))] = flat
            return day, races, None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return day, {}, "404"
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.8 * (attempt + 1))
    return day, {}, last_error or "unknown"


def fetch_odds_range(start: date, end: date, workers: int) -> tuple[dict[date, dict[tuple[int, int], dict[str, float]]], dict[str, str]]:
    days: list[date] = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    result: dict[date, dict[tuple[int, int], dict[str, float]]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as pool:
        futures = {pool.submit(fetch_odds_day, day): day for day in days}
        for future in as_completed(futures):
            day, races, error = future.result()
            if races:
                result[day] = races
            elif error and error != "404":
                errors[day.isoformat()] = error
    return result, errors


def build_records(start: date, end: date, learning: LearningProfile, workers: int) -> tuple[list[dict[str, Any]], dict[str, str]]:
    dates: list[date] = []
    cursor = start
    while cursor <= end:
        dates.append(cursor)
        cursor += timedelta(days=1)

    payloads: dict[date, dict[str, Any]] = {}
    failed_days: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(fetch_day, day): day for day in dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                payloads[day] = payload
            elif error != "404":
                failed_days[day.isoformat()] = error or "unknown"

    performance = PerformanceProfile()
    records: list[dict[str, Any]] = []
    for day in dates:
        root = payloads.get(day)
        if root is None:
            continue
        races = parse_day(root)
        observations: list[tuple[int, int, int | None, bool, int, int]] = []
        for race in races:
            combo, amount = race_result(race)
            if not combo or amount <= 0 or not decision_ready(race):
                continue
            racers = race_racers(race)
            if len(racers) != 6:
                continue
            raw, leader_lane, score_map = raw_confidence(race, learning)
            if raw == 0 or len(score_map) != 6:
                continue
            try:
                result_lanes = [int(value) for value in combo.split("-")]
            except ValueError:
                continue
            if len(result_lanes) != 3 or any(lane < 1 or lane > 6 for lane in result_lanes):
                continue

            venue = as_int(race.get("stadium_number"), 0) or 0
            race_number = as_int(race.get("race_number"), 0) or 0
            if not (1 <= venue <= 24 and 1 <= race_number <= 12):
                continue
            preview = race.get("preview") or {}
            wind = as_int(preview.get("wind_speed"), 0) or 0
            wave = as_int(preview.get("wave_height"), 0) or 0
            features = [v6.feature_row(racer, venue, wind, wave, learning) for racer in racers]
            baseline_picks = v6.score_top_picks(score_map, 10)
            first_lane = as_int(baseline_picks[0].split("-")[0]) if baseline_picks else None
            penalty = performance.penalty(venue, raw, first_lane)
            confidence = max(20, min(97, raw + penalty))
            history_skip = performance.auto_skip(venue, raw, first_lane)
            course_changes = sum(
                1 for racer in racers
                if int(racer.get("course") or racer["lane"]) != int(racer["lane"])
            )

            records.append({
                "day": day,
                "venue": venue,
                "raceNumber": race_number,
                "features": features,
                "targets": [lane - 1 for lane in result_lanes],
                "combo": combo,
                "amount": int(amount),
                "wind": wind,
                "wave": wave,
                "courseChanges": course_changes,
                "confidence": confidence,
                "baseThreshold": buy_threshold(race, leader_lane),
                "historySkip": history_skip,
                "baselinePicks": baseline_picks,
            })

            current_hit = combo in baseline_picks[:4]
            perf_payout = int(amount) * 3 if current_hit else 0
            observations.append((venue, raw, first_lane, current_hit, 1200, perf_payout))

        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)
    return records, failed_days


def full_distribution(model: v6.ConditionalPositionModel, rec: dict[str, Any]) -> list[dict[str, Any]]:
    base = rec["features"]
    first_probs = model.first_probabilities(base)
    rows: list[dict[str, Any]] = []
    total = 0.0
    for first in range(6):
        second_probs = model.second_probabilities(base, first)
        for second in range(6):
            if second == first:
                continue
            third_probs = model.third_probabilities(base, first, second)
            for third in range(6):
                if third in (first, second):
                    continue
                p = float(first_probs[first] * second_probs[second] * third_probs[third])
                rows.append({"combo": f"{first + 1}-{second + 1}-{third + 1}", "modelP": p})
                total += p
    if total <= 0:
        return []
    for row in rows:
        row["modelP"] = float(row["modelP"]) / total
    return rows


def make_signals(
    model: v6.ConditionalPositionModel,
    records: list[dict[str, Any]],
    start: date,
    end: date,
    odds_by_day: dict[date, dict[tuple[int, int], dict[str, float]]],
) -> tuple[list[dict[str, Any]], int]:
    signals: list[dict[str, Any]] = []
    missing = 0
    for rec in records:
        if not (start <= rec["day"] <= end):
            continue
        race_odds = odds_by_day.get(rec["day"], {}).get((int(rec["venue"]), int(rec["raceNumber"])))
        if not race_odds:
            missing += 1
            continue
        distribution = full_distribution(model, rec)
        market_raw: dict[str, float] = {}
        market_sum = 0.0
        for combo, odd in race_odds.items():
            if odd > 0:
                q = 1.0 / float(odd)
                market_raw[combo] = q
                market_sum += q
        if market_sum <= 0:
            missing += 1
            continue
        items: list[dict[str, Any]] = []
        for row in distribution:
            combo = str(row["combo"])
            odd = race_odds.get(combo)
            q = market_raw.get(combo)
            if odd is None or q is None or odd <= 0:
                continue
            items.append({
                "combo": combo,
                "modelP": float(row["modelP"]),
                "marketP": float(q / market_sum),
                "odds": float(odd),
            })
        if len(items) < 100:
            missing += 1
            continue
        signals.append({
            "day": rec["day"],
            "venue": int(rec["venue"]),
            "raceNumber": int(rec["raceNumber"]),
            "items": items,
            "combo": str(rec["combo"]),
            "amount": int(rec["amount"]),
        })
    return signals, missing


def blended_items(signal: dict[str, Any], alpha: float) -> list[dict[str, Any]]:
    weighted: list[tuple[dict[str, Any], float]] = []
    denom = 0.0
    for item in signal["items"]:
        mp = max(float(item["modelP"]), 1e-12)
        qp = max(float(item["marketP"]), 1e-12)
        value = math.exp(alpha * math.log(mp) + (1.0 - alpha) * math.log(qp))
        weighted.append((item, value))
        denom += value
    result: list[dict[str, Any]] = []
    if denom <= 0:
        return result
    for item, value in weighted:
        p = value / denom
        odd = float(item["odds"])
        ev = p * odd
        result.append({**item, "blendP": p, "ev": ev})
    result.sort(key=lambda row: (float(row["ev"]), float(row["blendP"])), reverse=True)
    return result


def allocate_units(items: list[dict[str, Any]], mode: str) -> list[int]:
    points = len(items)
    if points <= 0:
        return []
    units = [1] * points
    remaining = BUDGET_UNITS - points
    if remaining <= 0:
        return units
    if mode == "equal":
        for idx in range(remaining):
            units[idx % points] += 1
        return units
    if mode == "probability":
        weights = [max(float(item["blendP"]), 0.0) for item in items]
    else:
        weights = []
        for item in items:
            odd = max(float(item["odds"]), 1.0001)
            p = float(item["blendP"])
            kelly = max(0.0, (p * odd - 1.0) / (odd - 1.0))
            weights.append(kelly)
    total = sum(weights)
    if total <= 0:
        for idx in range(remaining):
            units[idx % points] += 1
        return units
    raw = [remaining * weight / total for weight in weights]
    floors = [int(math.floor(value)) for value in raw]
    for idx, value in enumerate(floors):
        units[idx] += value
    leftover = BUDGET_UNITS - sum(units)
    order = sorted(range(points), key=lambda idx: raw[idx] - floors[idx], reverse=True)
    for idx in order[:leftover]:
        units[idx] += 1
    return units


def choose_ticket(signal: dict[str, Any], cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[int]]:
    ranked = blended_items(signal, float(cfg["alpha"]))
    eligible = [
        item for item in ranked
        if float(item["ev"]) >= float(cfg["minEv"])
        and float(item["blendP"]) >= float(cfg["minProbability"])
        and float(item["odds"]) <= float(cfg["maxOdds"])
    ]
    picked = eligible[: int(cfg["maxPoints"])]
    if not picked:
        return [], []
    return picked, allocate_units(picked, str(cfg["allocationMode"]))


def evaluate(signals: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    raw = empty_stats()
    for signal in signals:
        picks, units = choose_ticket(signal, cfg)
        if not picks:
            continue
        raw["purchaseRaces"] += 1
        raw["stake"] += BUDGET
        raw["bets"] += len(picks)
        for idx, item in enumerate(picks):
            if str(item["combo"]) == signal["combo"]:
                raw["hits"] += 1
                raw["payout"] += int(signal["amount"]) * int(units[idx])
                break
    return finalize(raw)


def robust_score(monthly: dict[str, dict[str, Any]], total: dict[str, Any]) -> tuple[Any, ...]:
    values = list(monthly.values())
    positive = sum(1 for value in values if profitable(value))
    valid = sum(1 for value in values if int(value["purchaseRaces"]) >= MIN_MONTH_BUYS)
    worst = min((float(value["roi"]) for value in values if int(value["purchaseRaces"]) > 0), default=0.0)
    return (valid, positive, worst, float(total["roi"]), int(total["purchaseRaces"]))


def build_month_signals(
    records: list[dict[str, Any]],
    odds_by_day: dict[date, dict[tuple[int, int], dict[str, float]]],
    months: tuple[int, ...],
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, int]]:
    output: dict[str, list[dict[str, Any]]] = {}
    missing: dict[str, int] = {}
    for month in months:
        previous_end = month_end(month - 1)
        model = v6.fit_conditional_model(records, date(2026, 1, 1), previous_end)
        key = f"2026-{month:02d}"
        signals, absent = make_signals(model, records, date(2026, month, 1), month_end(month), odds_by_day)
        output[key] = signals
        missing[key] = absent
    return output, missing


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
        raise SystemExit("September validation period has not started")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    records, race_errors = build_records(args.start, data_end, learning, args.workers)
    if race_errors:
        raise SystemExit(f"race download failures: {race_errors}")

    odds_start = date(2026, 5, 1)
    odds_by_day, odds_errors = fetch_odds_range(odds_start, data_end, args.workers)
    if odds_errors:
        raise SystemExit(f"odds download failures: {odds_errors}")

    dev, missing_dev = build_month_signals(records, odds_by_day, DEV_MONTHS)
    if any(len(dev[f"2026-{month:02d}"]) < 500 for month in DEV_MONTHS):
        raise RuntimeError(f"insufficient odds-matched development signals: { {k: len(v) for k, v in dev.items()} }")

    gate_candidates: list[dict[str, Any]] = []
    for alpha in ALPHAS:
        for min_ev in MIN_EV_OPTIONS:
            for min_prob in MIN_PROB_OPTIONS:
                for max_odds in MAX_ODDS_OPTIONS:
                    cfg = {
                        "alpha": alpha,
                        "minEv": min_ev,
                        "minProbability": min_prob,
                        "maxOdds": max_odds,
                        "maxPoints": 1,
                        "allocationMode": "equal",
                        "budget": BUDGET,
                    }
                    monthly = {key: evaluate(signals, cfg) for key, signals in dev.items()}
                    total = combine(list(monthly.values()))
                    if int(total["purchaseRaces"]) < MIN_DEV_BUYS:
                        continue
                    gate_candidates.append({"config": cfg, "monthly": monthly, "total": total, "score": robust_score(monthly, total)})

    if not gate_candidates:
        raise RuntimeError("no historical-odds gate candidates with enough purchases")
    gate_candidates.sort(key=lambda item: item["score"], reverse=True)
    gate_candidates = gate_candidates[:KEEP_GATES]

    candidates: list[dict[str, Any]] = []
    for gate in gate_candidates:
        base = gate["config"]
        for points in POINT_OPTIONS:
            for mode in ALLOCATION_MODES:
                cfg = {**base, "maxPoints": points, "allocationMode": mode}
                monthly = {key: evaluate(signals, cfg) for key, signals in dev.items()}
                total = combine(list(monthly.values()))
                score = robust_score(monthly, total)
                candidates.append({"config": cfg, "developmentMonths": monthly, "development": total, "score": score})

    def qualifies(item: dict[str, Any]) -> bool:
        months = list(item["developmentMonths"].values())
        return (
            int(item["development"]["purchaseRaces"]) >= MIN_DEV_BUYS
            and float(item["development"]["roi"]) >= 105.0
            and all(int(stats["purchaseRaces"]) >= MIN_MONTH_BUYS for stats in months)
            and all(profitable(stats) for stats in months)
        )

    eligible = [item for item in candidates if qualifies(item)]
    pool = eligible or candidates
    pool.sort(
        key=lambda item: (
            1 if item in eligible else 0,
            item["score"][1],
            item["score"][2],
            item["score"][3],
            item["score"][4],
        ),
        reverse=True,
    )
    selected = pool[0]
    cfg = selected["config"]
    qualified_for_final = selected in eligible

    final_stats: dict[str, Any] | None = None
    final_signal_count = 0
    final_missing = 0
    qualified_for_release = False
    if qualified_for_final:
        final_model = v6.fit_conditional_model(records, date(2026, 1, 1), date(2026, 8, 31))
        final_signals, final_missing = make_signals(final_model, records, date(2026, 9, 1), data_end, odds_by_day)
        final_signal_count = len(final_signals)
        final_stats = evaluate(final_signals, cfg)
        qualified_for_release = bool(
            int(final_stats["purchaseRaces"]) >= 20
            and profitable(final_stats)
            and float(combine([selected["development"], final_stats])["roi"]) > 100.0
        )

    result = {
        "schemaVersion": 9,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "walk-forward conditional finish-order model + archived trifecta odds + blended model/market probability value selection",
        "oddsFinalGateIncluded": True,
        "oddsSource": "lamrongol/BoatraceOdds v3 archive (production continues to use official BOAT RACE odds)",
        "periods": {
            "train": ["2026-01-01", "2026-04-30"],
            "development": ["2026-05-01", "2026-08-31"],
            "final": ["2026-09-01", data_end.isoformat()],
        },
        "selected": selected,
        "validationMonths": {
            "2026-07": selected["developmentMonths"].get("2026-07", {}),
            "2026-08": selected["developmentMonths"].get("2026-08", {}),
        },
        "validation": combine([
            selected["developmentMonths"].get("2026-07", empty_stats()),
            selected["developmentMonths"].get("2026-08", empty_stats()),
        ]),
        "final": final_stats if final_stats is not None else {"withheld": True},
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "oddsCoverage": {
            "daysLoaded": len(odds_by_day),
            "developmentSignals": {key: len(value) for key, value in dev.items()},
            "developmentMissingRaces": missing_dev,
            "finalSignals": final_signal_count,
            "finalMissingRaces": final_missing,
        },
        "searchSpace": {
            "alpha": list(ALPHAS),
            "minEv": list(MIN_EV_OPTIONS),
            "minProbability": list(MIN_PROB_OPTIONS),
            "maxOdds": list(MAX_ODDS_OPTIONS),
            "maxPoints": list(POINT_OPTIONS),
            "allocationMode": list(ALLOCATION_MODES),
        },
        "releaseRule": "May-Aug each profitable with >=20 purchases and combined >=105% ROI; then Sep-latest must be profitable with >=20 purchases and May-Sep combined >100%",
        "topCandidates": pool[:20],
        "notes": [
            "Archived odds are joined only by date/stadium/race and are never derived from race results.",
            "Ticket selection uses model probability, market-implied probability and archived trifecta odds.",
            "May-Aug select strategy parameters; September is evaluated only after the strategy is frozen.",
            "Archived odds snapshots may differ slightly from the exact second of a live purchase.",
            "Production app continues to fetch official BOAT RACE odds directly.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "selected": selected,
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "final": result["final"],
        "oddsCoverage": result["oddsCoverage"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
