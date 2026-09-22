#!/usr/bin/env python3
"""Train conditional BOAT AI finish-order models and search 1-10 point tickets.

Leakage-safe protocol:
- Jan-Apr: train sequential models P(1st), P(2nd | 1st), P(3rd | 1st,2nd).
- May-Jun: choose ticket confidence, coverage, max-points and allocation rules.
- Jul-Aug: untouched validation using a model refit through Jun only.
- Sep-latest: evaluated only if BOTH Jul and Aug are profitable; model may then be
  refit through Aug as a pre-declared walk-forward update.

Historical closing odds are unavailable, so the live final-odds gate is excluded from
this historical test.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

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
REGULARIZATION = 0.05
EPOCHS = 150
LEARNING_RATE = 0.22
MAX_COMBOS = 10
MAX_POINTS_OPTIONS = (1, 2, 4, 6, 10)
COVERAGE_OPTIONS = (0.10, 0.15, 0.20, 0.30)
WINNER_PROB_THRESHOLDS = (0.0, 0.35, 0.45, 0.55)
ALLOCATION_MODES = ("equal", "probability")
LEADER_FILTERS = ("all", "lane1")
COMBOS = tuple(itertools.permutations(range(6), 3))
BASE_NUMERIC = 8


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


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


def feature_row(
    racer: dict[str, Any],
    venue: int,
    wind: int,
    wave: int,
    learning: LearningProfile,
) -> list[float]:
    lane = int(racer["lane"])
    course = int(racer.get("course") or lane)
    national = racer.get("national_win")
    local = racer.get("local_win")
    motor = racer.get("motor_top2")
    boat = racer.get("boat_top2")
    avg_start = racer.get("average_start")
    exhibition = racer.get("exhibition")
    preview_start = racer.get("preview_start")

    missing = [
        national is None,
        local is None,
        motor is None,
        boat is None,
        avg_start is None,
        exhibition is None,
        preview_start is None,
    ]

    national_v = clamp(float(national if national is not None else 5.0), 0.0, 10.0)
    local_v = clamp(float(local if local is not None else 5.0), 0.0, 10.0)
    motor_v = clamp(float(motor if motor is not None else 30.0), 0.0, 100.0)
    boat_v = clamp(float(boat if boat is not None else 30.0), 0.0, 100.0)
    avg_start_v = clamp(float(avg_start if avg_start is not None else 0.18), 0.0, 0.50)
    exhibition_v = clamp(float(exhibition if exhibition is not None else 6.90), 6.0, 8.0)
    preview_start_v = clamp(float(preview_start if preview_start is not None else 0.18), -0.20, 0.60)
    learning_bonus = learning.bonus(venue, lane, wind, course)

    values = [
        national_v,
        local_v,
        motor_v,
        boat_v,
        avg_start_v,
        exhibition_v,
        preview_start_v,
        float(learning_bonus),
    ]
    values += [1.0 if lane == value else 0.0 for value in range(1, 7)]
    values += [1.0 if course == value else 0.0 for value in range(1, 7)]
    values += [
        1.0 if course != lane else 0.0,
        float(wind) * (1.0 if lane == 1 else 0.0),
        float(wind) * (1.0 if lane >= 4 else 0.0),
        float(wave) * (1.0 if lane == 1 else 0.0),
        float(wave) * (1.0 if lane >= 4 else 0.0),
    ]
    values += [1.0 if flag else 0.0 for flag in missing]
    return values


def selected_lane_one_hot(index: int) -> list[float]:
    return [1.0 if index == value else 0.0 for value in range(6)]


def second_rows(base: list[list[float]], first: int) -> list[list[float]]:
    first_values = base[first]
    rows: list[list[float]] = []
    for candidate in range(6):
        values = list(base[candidate])
        values += [base[candidate][idx] - first_values[idx] for idx in range(BASE_NUMERIC)]
        values += selected_lane_one_hot(first)
        delta = candidate - first
        values += [
            delta / 5.0,
            abs(delta) / 5.0,
            1.0 if candidate < first else 0.0,
            1.0 if candidate > first else 0.0,
        ]
        rows.append(values)
    return rows


def third_rows(base: list[list[float]], first: int, second: int) -> list[list[float]]:
    first_values = base[first]
    second_values = base[second]
    rows: list[list[float]] = []
    low = min(first, second)
    high = max(first, second)
    for candidate in range(6):
        values = list(base[candidate])
        values += [base[candidate][idx] - first_values[idx] for idx in range(BASE_NUMERIC)]
        values += [base[candidate][idx] - second_values[idx] for idx in range(BASE_NUMERIC)]
        values += selected_lane_one_hot(first)
        values += selected_lane_one_hot(second)
        d_first = candidate - first
        d_second = candidate - second
        values += [
            d_first / 5.0,
            abs(d_first) / 5.0,
            d_second / 5.0,
            abs(d_second) / 5.0,
            1.0 if low < candidate < high else 0.0,
        ]
        rows.append(values)
    return rows


def masked_softmax(logits: np.ndarray, invalid: np.ndarray) -> np.ndarray:
    masked = np.where(invalid, -1.0e9, logits)
    shifted = masked - np.max(masked, axis=1, keepdims=True)
    exp = np.exp(np.clip(shifted, -40.0, 40.0))
    exp = np.where(invalid, 0.0, exp)
    denom = np.sum(exp, axis=1, keepdims=True)
    return exp / np.maximum(denom, 1.0e-12)


def fit_choice_weights(xs: np.ndarray, targets: np.ndarray, invalid: np.ndarray) -> np.ndarray:
    weights = np.zeros(xs.shape[-1], dtype=np.float64)
    rows = np.arange(len(xs))
    for epoch in range(EPOCHS):
        logits = np.einsum("rsf,f->rs", xs, weights)
        probs = masked_softmax(logits, invalid)
        diff = probs.copy()
        diff[rows, targets] -= 1.0
        diff = np.where(invalid, 0.0, diff)
        grad = np.einsum("rs,rsf->f", diff, xs) / len(xs)
        grad += REGULARIZATION * weights
        step = LEARNING_RATE / math.sqrt(1.0 + epoch / 45.0)
        weights -= step * grad
    return weights


def standardize_tensor(x: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    flat = x.reshape(-1, x.shape[-1])
    mean = flat.mean(axis=0)
    std = flat.std(axis=0)
    std = np.where(std < 1e-6, 1.0, std)
    return (x - mean) / std, mean, std


class ConditionalPositionModel:
    def __init__(
        self,
        first_mean: np.ndarray,
        first_std: np.ndarray,
        first_weights: np.ndarray,
        second_mean: np.ndarray,
        second_std: np.ndarray,
        second_weights: np.ndarray,
        third_mean: np.ndarray,
        third_std: np.ndarray,
        third_weights: np.ndarray,
    ) -> None:
        self.first_mean = first_mean
        self.first_std = first_std
        self.first_weights = first_weights
        self.second_mean = second_mean
        self.second_std = second_std
        self.second_weights = second_weights
        self.third_mean = third_mean
        self.third_std = third_std
        self.third_weights = third_weights

    @staticmethod
    def _probabilities(
        rows: list[list[float]],
        mean: np.ndarray,
        std: np.ndarray,
        weights: np.ndarray,
        excluded: set[int],
    ) -> np.ndarray:
        x = np.asarray(rows, dtype=np.float64)
        xs = (x - mean) / std
        logits = xs @ weights
        invalid = np.asarray([[idx in excluded for idx in range(6)]], dtype=bool)
        return masked_softmax(logits.reshape(1, 6), invalid)[0]

    def first_probabilities(self, base: list[list[float]]) -> np.ndarray:
        return self._probabilities(base, self.first_mean, self.first_std, self.first_weights, set())

    def second_probabilities(self, base: list[list[float]], first: int) -> np.ndarray:
        return self._probabilities(
            second_rows(base, first),
            self.second_mean,
            self.second_std,
            self.second_weights,
            {first},
        )

    def third_probabilities(self, base: list[list[float]], first: int, second: int) -> np.ndarray:
        return self._probabilities(
            third_rows(base, first, second),
            self.third_mean,
            self.third_std,
            self.third_weights,
            {first, second},
        )


def fit_conditional_model(records: list[dict[str, Any]], start: date, end: date) -> ConditionalPositionModel:
    subset = [rec for rec in records if start <= rec["day"] <= end]
    if len(subset) < 1000:
        raise RuntimeError(f"not enough model training races: {len(subset)}")

    base = np.asarray([rec["features"] for rec in subset], dtype=np.float64)
    targets = np.asarray([rec["targets"] for rec in subset], dtype=np.int64)
    first_targets = targets[:, 0]
    second_targets = targets[:, 1]
    third_targets = targets[:, 2]

    first_xs, first_mean, first_std = standardize_tensor(base)
    first_invalid = np.zeros((len(subset), 6), dtype=bool)
    first_weights = fit_choice_weights(first_xs, first_targets, first_invalid)

    second_raw = np.asarray(
        [second_rows(rec["features"], int(rec["targets"][0])) for rec in subset],
        dtype=np.float64,
    )
    second_xs, second_mean, second_std = standardize_tensor(second_raw)
    second_invalid = np.zeros((len(subset), 6), dtype=bool)
    second_invalid[np.arange(len(subset)), first_targets] = True
    second_weights = fit_choice_weights(second_xs, second_targets, second_invalid)

    third_raw = np.asarray(
        [third_rows(rec["features"], int(rec["targets"][0]), int(rec["targets"][1])) for rec in subset],
        dtype=np.float64,
    )
    third_xs, third_mean, third_std = standardize_tensor(third_raw)
    third_invalid = np.zeros((len(subset), 6), dtype=bool)
    rows = np.arange(len(subset))
    third_invalid[rows, first_targets] = True
    third_invalid[rows, second_targets] = True
    third_weights = fit_choice_weights(third_xs, third_targets, third_invalid)

    return ConditionalPositionModel(
        first_mean,
        first_std,
        first_weights,
        second_mean,
        second_std,
        second_weights,
        third_mean,
        third_std,
        third_weights,
    )


def trifecta_distribution(model: ConditionalPositionModel, rec: dict[str, Any]) -> list[dict[str, Any]]:
    base = rec["features"]
    first_probs = model.first_probabilities(base)
    ranked: list[tuple[str, float]] = []
    for first in range(6):
        second_probs = model.second_probabilities(base, first)
        for second in range(6):
            if second == first:
                continue
            third_probs = model.third_probabilities(base, first, second)
            for third in range(6):
                if third in (first, second):
                    continue
                value = float(first_probs[first] * second_probs[second] * third_probs[third])
                ranked.append((f"{first + 1}-{second + 1}-{third + 1}", value))
    total = sum(value for _, value in ranked)
    if total <= 0.0:
        return []
    ranked.sort(key=lambda item: item[1], reverse=True)
    return [
        {"combo": combo, "probability": value / total}
        for combo, value in ranked[:MAX_COMBOS]
    ]


def make_signals(model: ConditionalPositionModel, records: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    for rec in records:
        if not (start <= rec["day"] <= end):
            continue
        first_probs = model.first_probabilities(rec["features"])
        ranked = trifecta_distribution(model, rec)
        if not ranked:
            continue
        signals.append({
            "day": rec["day"],
            "ranked": ranked,
            "topProbability": float(ranked[0]["probability"]),
            "winnerProbability": float(np.max(first_probs)),
            "leaderLane": int(np.argmax(first_probs)) + 1,
            "combo": rec["combo"],
            "amount": rec["amount"],
        })
    return signals


def allocate_units(probabilities: list[float], mode: str) -> list[int]:
    points = len(probabilities)
    if points <= 0:
        return []
    if mode == "equal":
        base = BUDGET_UNITS // points
        remainder = BUDGET_UNITS - base * points
        return [base + (1 if idx < remainder else 0) for idx in range(points)]

    units = [1] * points
    remaining = BUDGET_UNITS - points
    if remaining <= 0:
        return units
    total = sum(probabilities)
    if total <= 0:
        return units
    raw = [remaining * value / total for value in probabilities]
    floors = [int(math.floor(value)) for value in raw]
    for idx, value in enumerate(floors):
        units[idx] += value
    leftover = BUDGET_UNITS - sum(units)
    order = sorted(range(points), key=lambda idx: raw[idx] - floors[idx], reverse=True)
    for idx in order[:leftover]:
        units[idx] += 1
    return units


def ticket(signal: dict[str, Any], cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[int]]:
    if float(signal["topProbability"]) < float(cfg["minTopProbability"]):
        return [], []
    if float(signal["winnerProbability"]) < float(cfg["minWinnerProbability"]):
        return [], []
    if cfg["leaderFilter"] == "lane1" and int(signal["leaderLane"]) != 1:
        return [], []

    picked: list[dict[str, Any]] = []
    cumulative = 0.0
    for item in signal["ranked"]:
        if len(picked) >= int(cfg["maxPoints"]):
            break
        picked.append(item)
        cumulative += float(item["probability"])
        if cumulative >= float(cfg["coverage"]):
            break
    if not picked:
        return [], []
    probabilities = [float(item["probability"]) for item in picked]
    return picked, allocate_units(probabilities, str(cfg["allocationMode"]))


def empty_stats() -> dict[str, int]:
    return {"purchaseRaces": 0, "hits": 0, "stake": 0, "payout": 0}


def finalize_stats(raw: dict[str, int]) -> dict[str, Any]:
    buys = raw["purchaseRaces"]
    stake = raw["stake"]
    payout = raw["payout"]
    hits = raw["hits"]
    return {
        **raw,
        "profit": payout - stake,
        "roi": round(payout * 100.0 / stake, 1) if stake else 0.0,
        "hitRate": round(hits * 100.0 / buys, 1) if buys else 0.0,
    }


def evaluate(signals: list[dict[str, Any]], cfg: dict[str, Any], start: date, end: date) -> dict[str, Any]:
    raw = empty_stats()
    for signal in signals:
        if not (start <= signal["day"] <= end):
            continue
        picks, units = ticket(signal, cfg)
        if not picks:
            continue
        raw["purchaseRaces"] += 1
        raw["stake"] += BUDGET_UNITS * 100
        for idx, item in enumerate(picks):
            if item["combo"] == signal["combo"]:
                raw["hits"] += 1
                raw["payout"] += int(signal["amount"]) * units[idx]
                break
    return finalize_stats(raw)


def combined(stats_list: list[dict[str, Any]]) -> dict[str, Any]:
    raw = empty_stats()
    for stats in stats_list:
        for key in raw:
            raw[key] += int(stats.get(key, 0))
    return finalize_stats(raw)


def profitable(stats: dict[str, Any]) -> bool:
    return stats["purchaseRaces"] > 0 and stats["profit"] > 0 and stats["roi"] > 100.0


def evaluate_current_baseline(records: list[dict[str, Any]], start: date, end: date) -> dict[str, Any]:
    raw = empty_stats()
    stakes = (5, 4, 2, 1)
    for rec in records:
        if not (start <= rec["day"] <= end):
            continue
        if rec["historySkip"] or int(rec["confidence"]) < int(rec["baseThreshold"]):
            continue
        raw["purchaseRaces"] += 1
        raw["stake"] += 1200
        picks = rec["baselinePicks"][:4]
        if rec["combo"] in picks:
            idx = picks.index(rec["combo"])
            raw["hits"] += 1
            raw["payout"] += int(rec["amount"]) * stakes[idx]
    return finalize_stats(raw)


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
            features = [feature_row(racer, venue, wind, wave, learning) for racer in racers]
            baseline_picks = score_top_picks(score_map, 10)
            first_lane = as_int(baseline_picks[0].split("-")[0]) if baseline_picks else None
            penalty = performance.penalty(venue, raw, first_lane)
            confidence = max(20, min(97, raw + penalty))
            history_skip = performance.auto_skip(venue, raw, first_lane)

            records.append({
                "day": day,
                "features": features,
                "targets": [lane - 1 for lane in result_lanes],
                "combo": combo,
                "amount": trifecta_amount,
                "confidence": confidence,
                "baseThreshold": buy_threshold(race, leader_lane),
                "historySkip": history_skip,
                "baselinePicks": baseline_picks,
            })

            current_hit = combo in baseline_picks[:4]
            perf_payout = trifecta_amount * 3 if current_hit else 0
            observations.append((venue, raw, first_lane, current_hit, 1200, perf_payout))

        for race in races:
            learning.observe_race(race)
        for observation in observations:
            performance.observe(*observation)

    train_start, train_end = date(2026, 1, 1), date(2026, 4, 30)
    tune_start, tune_end = date(2026, 5, 1), date(2026, 6, 30)
    validation_start, validation_end = date(2026, 7, 1), date(2026, 8, 31)
    final_start, final_end = date(2026, 9, 1), data_end

    model_train = fit_conditional_model(records, train_start, train_end)
    tune_signals = make_signals(model_train, records, tune_start, tune_end)
    if len(tune_signals) < 1000:
        raise RuntimeError("too few tuning signals")

    top_prob_values = np.asarray([signal["topProbability"] for signal in tune_signals], dtype=np.float64)
    quantiles = (0.0, 0.35, 0.55, 0.70, 0.82, 0.90)
    min_top_options = sorted({round(float(np.quantile(top_prob_values, q)), 5) for q in quantiles})

    candidates: list[dict[str, Any]] = []
    for min_top in min_top_options:
        for min_winner in WINNER_PROB_THRESHOLDS:
            for max_points in MAX_POINTS_OPTIONS:
                for coverage in COVERAGE_OPTIONS:
                    for allocation_mode in ALLOCATION_MODES:
                        for leader_filter in LEADER_FILTERS:
                            cfg = {
                                "minTopProbability": min_top,
                                "minWinnerProbability": min_winner,
                                "maxPoints": max_points,
                                "coverage": coverage,
                                "allocationMode": allocation_mode,
                                "leaderFilter": leader_filter,
                                "budget": 1200,
                            }
                            may = evaluate(tune_signals, cfg, date(2026, 5, 1), date(2026, 5, 31))
                            june = evaluate(tune_signals, cfg, date(2026, 6, 1), date(2026, 6, 30))
                            total = combined([may, june])
                            candidates.append({
                                "config": cfg,
                                "tuneMonths": {"2026-05": may, "2026-06": june},
                                "tune": total,
                                "worstMonthRoi": min(may["roi"], june["roi"]),
                            })

    eligible = [
        item for item in candidates
        if item["tuneMonths"]["2026-05"]["purchaseRaces"] >= 50
        and item["tuneMonths"]["2026-06"]["purchaseRaces"] >= 50
        and profitable(item["tuneMonths"]["2026-05"])
        and profitable(item["tuneMonths"]["2026-06"])
        and profitable(item["tune"])
    ]
    selection_pool = eligible or candidates
    selection_pool.sort(
        key=lambda item: (
            1 if item in eligible else 0,
            item["worstMonthRoi"],
            item["tune"]["roi"],
            item["tune"]["profit"],
            item["tune"]["purchaseRaces"],
        ),
        reverse=True,
    )
    selected = selection_pool[0]
    cfg = selected["config"]

    model_validation = fit_conditional_model(records, train_start, tune_end)
    validation_signals = make_signals(model_validation, records, validation_start, validation_end)
    july = evaluate(validation_signals, cfg, date(2026, 7, 1), date(2026, 7, 31))
    august = evaluate(validation_signals, cfg, date(2026, 8, 1), date(2026, 8, 31))
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
        model_final = fit_conditional_model(records, train_start, validation_end)
        final_signals = make_signals(model_final, records, final_start, final_end)
        final_stats = evaluate(final_signals, cfg, final_start, final_end)
        qualified_for_release = bool(
            final_stats["purchaseRaces"] >= 20 and profitable(final_stats)
        )

    baseline = {
        "tune": evaluate_current_baseline(records, tune_start, tune_end),
        "validation": evaluate_current_baseline(records, validation_start, validation_end),
    }
    if qualified_for_final:
        baseline["final"] = evaluate_current_baseline(records, final_start, final_end)

    result = {
        "schemaVersion": 6,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "sequential conditional softmax P(1st) * P(2nd|1st) * P(3rd|1st,2nd); variable 1-10 point ticket",
        "oddsFinalGateIncluded": False,
        "model": {
            "regularization": REGULARIZATION,
            "epochs": EPOCHS,
            "learningRate": LEARNING_RATE,
            "baseFeatureCount": len(records[0]["features"][0]) if records else 0,
            "secondFeatureCount": len(second_rows(records[0]["features"], 0)[0]) if records else 0,
            "thirdFeatureCount": len(third_rows(records[0]["features"], 0, 1)[0]) if records else 0,
            "trainingRacesJanApr": sum(1 for rec in records if train_start <= rec["day"] <= train_end),
            "trainingRacesJanJun": sum(1 for rec in records if train_start <= rec["day"] <= tune_end),
        },
        "periods": {
            "train": [train_start.isoformat(), train_end.isoformat()],
            "tune": [tune_start.isoformat(), tune_end.isoformat()],
            "validation": [validation_start.isoformat(), validation_end.isoformat()],
            "final": [final_start.isoformat(), final_end.isoformat()],
        },
        "selected": selected,
        "validationMonths": {"2026-07": july, "2026-08": august},
        "validation": validation,
        "final": final_stats if final_stats is not None else {"withheld": True},
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "currentFourPickBaseline": baseline,
        "releaseRule": "May and Jun each positive with >=50 buys; Jul and Aug each positive with combined >=50 buys; only then Sep-latest positive with >=20 buys",
        "topCandidates": selection_pool[:20],
        "notes": [
            "Second-place probabilities are conditioned on the selected first-place racer and exclude that racer.",
            "Third-place probabilities are conditioned on the selected first and second racers and exclude both.",
            "May-Jun choose ticket settings only; Jul-Aug remain untouched validation.",
            "Sep remains withheld unless both Jul and Aug pass; if opened, the model is refit only through Aug.",
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
