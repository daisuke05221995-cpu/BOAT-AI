#!/usr/bin/env python3
"""Search robust race-selectivity gates on top of the schema-6 conditional model.

Leakage-safe protocol:
- Jan-Apr: fit sequential conditional finish-order model.
- May-Jun: choose ONLY race-selection gates. Ticket is deliberately fixed to one point
  (1200 yen) so point-count tuning cannot hide a weak race-selection rule.
- Jul-Aug: untouched validation after refitting model through Jun.
- Sep-latest: opened only if May, Jun, Jul and Aug all pass the predeclared rule.

Historical closing odds are unavailable, so the live final-odds gate is excluded.
"""

from __future__ import annotations

import argparse
import json
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
MIN_MONTH_BUYS = 50
QUANTILES = (0.45, 0.65, 0.80, 0.90)
MAX_WIND_OPTIONS = (2, 4, 99)
MAX_COURSE_CHANGES = (0, 1, 6)
LEADER_FILTERS = ("lane1", "all")


def q_options(values: list[float], include_zero: bool = False) -> list[float]:
    arr = np.asarray(values, dtype=np.float64)
    if len(arr) == 0:
        return [0.0]
    result = {round(float(np.quantile(arr, q)), 6) for q in QUANTILES}
    if include_zero:
        result.add(0.0)
    return sorted(result)


def make_signals(
    model: v6.ConditionalPositionModel,
    records: list[dict[str, Any]],
    start: date,
    end: date,
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for rec in records:
        if not (start <= rec["day"] <= end):
            continue
        first_probs = model.first_probabilities(rec["features"])
        ranked = v6.trifecta_distribution(model, rec)
        if len(ranked) < 3:
            continue
        winner_order = np.sort(first_probs)[::-1]
        top = float(ranked[0]["probability"])
        second = float(ranked[1]["probability"])
        signals.append({
            "day": rec["day"],
            "topCombo": str(ranked[0]["combo"]),
            "topProbability": top,
            "trifectaGap": max(0.0, top - second),
            "top3Share": float(sum(float(item["probability"]) for item in ranked[:3])),
            "winnerProbability": float(winner_order[0]),
            "winnerGap": float(max(0.0, winner_order[0] - winner_order[1])),
            "leaderLane": int(np.argmax(first_probs)) + 1,
            "wind": int(rec["wind"]),
            "courseChanges": int(rec["courseChanges"]),
            "combo": rec["combo"],
            "amount": int(rec["amount"]),
        })
    return signals


def passes(signal: dict[str, Any], cfg: dict[str, Any]) -> bool:
    if float(signal["topProbability"]) < float(cfg["minTopProbability"]):
        return False
    if float(signal["winnerProbability"]) < float(cfg["minWinnerProbability"]):
        return False
    if float(signal["winnerGap"]) < float(cfg["minWinnerGap"]):
        return False
    if float(signal["trifectaGap"]) < float(cfg["minTrifectaGap"]):
        return False
    if float(signal["top3Share"]) < float(cfg["minTop3Share"]):
        return False
    if int(signal["wind"]) > int(cfg["maxWind"]):
        return False
    if int(signal["courseChanges"]) > int(cfg["maxCourseChanges"]):
        return False
    if cfg["leaderFilter"] == "lane1" and int(signal["leaderLane"]) != 1:
        return False
    return True


def empty_stats() -> dict[str, int]:
    return {"purchaseRaces": 0, "hits": 0, "stake": 0, "payout": 0}


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
    }


def evaluate(signals: list[dict[str, Any]], cfg: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    raw = empty_stats()
    for signal in signals:
        if not (start <= signal["day"] <= end) or not passes(signal, cfg):
            continue
        raw["purchaseRaces"] += 1
        raw["stake"] += BUDGET
        if signal["topCombo"] == signal["combo"]:
            raw["hits"] += 1
            raw["payout"] += int(signal["amount"]) * 12
    return finalize(raw)


def combined(items: list[dict[str, Any]]) -> dict[str, Any]:
    raw = empty_stats()
    for item in items:
        for key in raw:
            raw[key] += int(item.get(key, 0))
    return finalize(raw)


def profitable(stats: dict[str, Any]) -> bool:
    return int(stats["purchaseRaces"]) > 0 and int(stats["profit"]) > 0 and float(stats["roi"]) > 100.0


def build_records(
    start: date,
    end: date,
    learning: LearningProfile,
    workers: int,
) -> tuple[list[dict[str, Any]], dict[str, str]]:
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
                "features": features,
                "targets": [lane - 1 for lane in result_lanes],
                "combo": combo,
                "amount": amount,
                "wind": wind,
                "wave": wave,
                "courseChanges": course_changes,
                "confidence": confidence,
                "baseThreshold": buy_threshold(race, leader_lane),
                "historySkip": history_skip,
                "baselinePicks": baseline_picks,
            })

            current_hit = combo in baseline_picks[:4]
            perf_payout = amount * 3 if current_hit else 0
            observations.append((venue, raw, first_lane, current_hit, 1200, perf_payout))

        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)

    return records, failed_days


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
    records, failed_days = build_records(args.start, data_end, learning, args.workers)
    if failed_days:
        raise SystemExit(f"download failures: {failed_days}")

    train_start, train_end = date(2026, 1, 1), date(2026, 4, 30)
    tune_start, tune_end = date(2026, 5, 1), date(2026, 6, 30)
    val_start, val_end = date(2026, 7, 1), date(2026, 8, 31)
    final_start, final_end = date(2026, 9, 1), data_end

    model_train = v6.fit_conditional_model(records, train_start, train_end)
    tune_signals = make_signals(model_train, records, tune_start, tune_end)
    if len(tune_signals) < 1000:
        raise RuntimeError("too few tuning signals")

    options = {
        "top": q_options([s["topProbability"] for s in tune_signals], include_zero=True),
        "winner": q_options([s["winnerProbability"] for s in tune_signals], include_zero=True),
        "winnerGap": q_options([s["winnerGap"] for s in tune_signals], include_zero=True),
        "trifectaGap": q_options([s["trifectaGap"] for s in tune_signals], include_zero=True),
        "top3": q_options([s["top3Share"] for s in tune_signals], include_zero=True),
    }

    candidates: list[dict[str, Any]] = []
    for min_top in options["top"]:
        for min_winner in options["winner"]:
            for min_winner_gap in options["winnerGap"]:
                for min_tri_gap in options["trifectaGap"]:
                    for min_top3 in options["top3"]:
                        for max_wind in MAX_WIND_OPTIONS:
                            for max_changes in MAX_COURSE_CHANGES:
                                for leader_filter in LEADER_FILTERS:
                                    cfg = {
                                        "minTopProbability": min_top,
                                        "minWinnerProbability": min_winner,
                                        "minWinnerGap": min_winner_gap,
                                        "minTrifectaGap": min_tri_gap,
                                        "minTop3Share": min_top3,
                                        "maxWind": max_wind,
                                        "maxCourseChanges": max_changes,
                                        "leaderFilter": leader_filter,
                                        "maxPoints": 1,
                                        "allocationMode": "equal",
                                        "budget": BUDGET,
                                    }
                                    may = evaluate(tune_signals, cfg, date(2026, 5, 1), date(2026, 5, 31))
                                    june = evaluate(tune_signals, cfg, date(2026, 6, 1), date(2026, 6, 30))
                                    total = combined([may, june])
                                    candidates.append({
                                        "config": cfg,
                                        "tuneMonths": {"2026-05": may, "2026-06": june},
                                        "tune": total,
                                        "worstMonthRoi": min(float(may["roi"]), float(june["roi"])),
                                    })

    eligible = [
        item for item in candidates
        if item["tuneMonths"]["2026-05"]["purchaseRaces"] >= MIN_MONTH_BUYS
        and item["tuneMonths"]["2026-06"]["purchaseRaces"] >= MIN_MONTH_BUYS
        and profitable(item["tuneMonths"]["2026-05"])
        and profitable(item["tuneMonths"]["2026-06"])
        and profitable(item["tune"])
    ]
    pool = eligible or candidates
    pool.sort(
        key=lambda item: (
            1 if item in eligible else 0,
            float(item["worstMonthRoi"]),
            float(item["tune"]["roi"]),
            int(item["tune"]["purchaseRaces"]),
        ),
        reverse=True,
    )
    selected = pool[0]
    cfg = selected["config"]

    model_val = v6.fit_conditional_model(records, train_start, tune_end)
    val_signals = make_signals(model_val, records, val_start, val_end)
    july = evaluate(val_signals, cfg, date(2026, 7, 1), date(2026, 7, 31))
    august = evaluate(val_signals, cfg, date(2026, 8, 1), date(2026, 8, 31))
    validation = combined([july, august])

    qualified_for_final = bool(
        selected in eligible
        and validation["purchaseRaces"] >= 50
        and profitable(july)
        and profitable(august)
        and profitable(validation)
    )

    final_stats: dict[str, Any] | None = None
    qualified_for_release = False
    if qualified_for_final and final_end >= final_start:
        model_final = v6.fit_conditional_model(records, train_start, val_end)
        final_signals = make_signals(model_final, records, final_start, final_end)
        final_stats = evaluate(final_signals, cfg, final_start, final_end)
        qualified_for_release = bool(final_stats["purchaseRaces"] >= 20 and profitable(final_stats))

    baseline = {
        "tune": v6.evaluate_current_baseline(records, tune_start, tune_end),
        "validation": v6.evaluate_current_baseline(records, val_start, val_end),
    }
    if qualified_for_final:
        baseline["final"] = v6.evaluate_current_baseline(records, final_start, final_end)

    result = {
        "schemaVersion": 7,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "schema6 conditional finish-order model + robust one-point race-selectivity gates",
        "oddsFinalGateIncluded": False,
        "periods": {
            "train": [train_start.isoformat(), train_end.isoformat()],
            "tune": [tune_start.isoformat(), tune_end.isoformat()],
            "validation": [val_start.isoformat(), val_end.isoformat()],
            "final": [final_start.isoformat(), final_end.isoformat()],
        },
        "selectionGrid": options,
        "selected": selected,
        "validationMonths": {"2026-07": july, "2026-08": august},
        "validation": validation,
        "final": final_stats if final_stats is not None else {"withheld": True},
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "currentFourPickBaseline": baseline,
        "releaseRule": "May and Jun each positive with >=50 buys; Jul and Aug each positive with combined >=50 buys; only then Sep-latest positive with >=20 buys",
        "topCandidates": pool[:20],
        "notes": [
            "Ticket count is intentionally fixed to one point in this stage; this isolates race selection quality.",
            "Gates use model concentration, winner/trifecta margins, wind and course-change count.",
            "All gate thresholds are chosen only from May-Jun; Jul-Aug are untouched validation.",
            "Sep remains withheld unless Jul and Aug both pass.",
            "Historical closing odds are unavailable, so live final-odds filtering remains excluded.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "selected": selected,
        "validationMonths": result["validationMonths"],
        "validation": validation,
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "final": result["final"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
