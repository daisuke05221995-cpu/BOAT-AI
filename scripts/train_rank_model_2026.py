#!/usr/bin/env python3
"""Train and validate a learned 3-position BOAT AI ranking model.

Model fitting uses only 2026-01-01..2026-06-30 settled races. Betting parameters
are selected only on archived odds from 2026-07-19..2026-08-31. September is a
strict untouched final holdout. Feature generation itself is walk-forward: the
historical-learning profile is updated only after all races for each day.
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

import numpy as np

from build_2026_backtest import (
    JST,
    BUDGET,
    LearningProfile,
    as_int,
    decision_ready,
    fetch_day,
    parse_day,
    race_racers,
    race_result,
)

TRAIN_THROUGH = date(2026, 6, 30)
ODDS_FROM = date(2026, 7, 19)
TUNE_THROUGH = date(2026, 8, 31)
HOLDOUT_FROM = date(2026, 9, 1)
ODDS_URL = (
    "https://raw.githubusercontent.com/BoatraceCSV/boatracecsv.github.io/"
    "main/data/previews/od3/{year}/{month:02d}/{day:02d}.csv"
)
USER_AGENT = "BOAT-AI-Learned-Rank/1.0"

STAKE_PLANS: dict[str, tuple[int, ...]] = {
    "equal3": (400, 400, 400),
    "balanced3": (500, 400, 300),
    "equal4": (300, 300, 300, 300),
}
PROB_TEMPS = (0.75, 1.0, 1.25, 1.5)
EV_MINS = (1.00, 1.05, 1.10, 1.20, 1.30, 1.40)
EDGE_MINS = (1.00, 1.10, 1.20)
MODEL_RANKS = (12, 20, 30)


@dataclass
class RaceSample:
    day: date
    venue: int
    features: np.ndarray
    finish: tuple[int, int, int]
    payout: int
    code: str


@dataclass(frozen=True)
class BetRule:
    probability_temperature: float
    ev_min: float
    edge_min: float
    max_model_rank: int
    plan: str


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


def race_code(day: date, race: dict[str, Any]) -> str:
    venue = as_int(race.get("stadium_number"), 0) or 0
    race_no = as_int(race.get("race_number"), 0) or 0
    return f"{day:%Y%m%d}{venue:02d}{race_no:02d}"


def fetch_odds_day(
    day: date, attempts: int = 3
) -> tuple[date, dict[str, dict[str, float]] | None, str | None]:
    url = ODDS_URL.format(year=day.year, month=day.month, day=day.day)
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": USER_AGENT, "Accept": "text/csv"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                text = response.read().decode("utf-8-sig")
            result: dict[str, dict[str, float]] = {}
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
                    result[code] = values
            return day, result, None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return day, None, "404"
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
        time.sleep(attempt * 0.7)
    return day, None, last_error or "unknown"


def feature_matrix(race: dict[str, Any], learning: LearningProfile) -> np.ndarray | None:
    racers = race_racers(race)
    if len(racers) != 6:
        return None
    racers = sorted(racers, key=lambda racer: racer["lane"])
    venue = as_int(race.get("stadium_number"), 0) or 0
    preview = race.get("preview") or {}
    wind = as_int(preview.get("wind_speed"), 0) or 0
    wave = as_int(preview.get("wave_height"), 0) or 0
    rows: list[list[float]] = []

    for racer in racers:
        lane = racer["lane"]
        course = racer.get("course") or lane
        lane_onehot = [1.0 if lane == index else 0.0 for index in range(1, 7)]
        course_onehot = [1.0 if course == index else 0.0 for index in range(1, 7)]
        avg_start = racer.get("average_start")
        exhibition = racer.get("exhibition")
        preview_start = racer.get("preview_start")
        learned_bonus = learning.bonus(venue, lane, wind, course)

        continuous = [
            (racer.get("national_win") or 0.0) / 10.0,
            (racer.get("local_win") or 0.0) / 10.0,
            (racer.get("motor_top2") or 0.0) / 100.0,
            (racer.get("boat_top2") or 0.0) / 100.0,
            ((0.25 - avg_start) if avg_start is not None else 0.0) * 4.0,
            ((7.05 - exhibition) if exhibition is not None else 0.0) * 2.0,
            ((0.25 - preview_start) if preview_start is not None else 0.0) * 4.0,
            learned_bonus / 10.0,
            1.0 if course != lane else 0.0,
            (7.0 - float(course)) / 6.0,
        ]
        wind_lane = [value * min(wind, 10) / 10.0 for value in lane_onehot]
        wave_lane = [value * min(wave, 20) / 20.0 for value in lane_onehot]
        rows.append(lane_onehot + course_onehot + continuous + wind_lane + wave_lane)
    return np.asarray(rows, dtype=np.float64)


def build_samples(
    dates: list[date],
    payloads: dict[date, dict[str, Any]],
    learning_payload: dict[str, Any],
) -> list[RaceSample]:
    learning = LearningProfile(learning_payload)
    samples: list[RaceSample] = []
    for day in dates:
        root = payloads.get(day)
        if root is None:
            continue
        races = parse_day(root)
        for race in races:
            combo, payout = race_result(race)
            if not combo or payout <= 0 or not decision_ready(race):
                continue
            parts = [as_int(value) for value in combo.split("-")]
            if len(parts) != 3 or any(value is None for value in parts):
                continue
            finish = tuple(int(value) for value in parts)  # type: ignore[arg-type]
            features = feature_matrix(race, learning)
            if features is None:
                continue
            samples.append(
                RaceSample(
                    day=day,
                    venue=as_int(race.get("stadium_number"), 0) or 0,
                    features=features,
                    finish=finish,
                    payout=payout,
                    code=race_code(day, race),
                )
            )
        for race in races:
            learning.observe_race(race)
    return samples


def softmax(values: np.ndarray) -> np.ndarray:
    shifted = values - np.max(values)
    exp_values = np.exp(np.clip(shifted, -40.0, 40.0))
    return exp_values / np.sum(exp_values)


def fit_position_models(
    train_samples: list[RaceSample], feature_count: int, epochs: int = 45
) -> np.ndarray:
    weights = np.zeros((3, feature_count), dtype=np.float64)
    first_moment = np.zeros_like(weights)
    second_moment = np.zeros_like(weights)
    beta1 = 0.9
    beta2 = 0.999
    learning_rate = 0.035
    l2 = 0.002
    step = 0

    for epoch in range(epochs):
        gradient = np.zeros_like(weights)
        loss = 0.0
        terms = 0
        for sample in train_samples:
            remaining = [0, 1, 2, 3, 4, 5]
            actual = [lane - 1 for lane in sample.finish]
            for position in range(3):
                target_lane_index = actual[position]
                if target_lane_index not in remaining:
                    continue
                x_available = sample.features[remaining]
                logits = x_available @ weights[position]
                probabilities = softmax(logits)
                target_local = remaining.index(target_lane_index)
                loss -= math.log(max(1e-12, float(probabilities[target_local])))
                expected = probabilities @ x_available
                gradient[position] += sample.features[target_lane_index] - expected
                remaining.remove(target_lane_index)
                terms += 1

        if not terms:
            raise SystemExit("no training terms")
        gradient = gradient / float(terms) - l2 * weights
        step += 1
        first_moment = beta1 * first_moment + (1.0 - beta1) * gradient
        second_moment = beta2 * second_moment + (1.0 - beta2) * (gradient * gradient)
        m_hat = first_moment / (1.0 - beta1**step)
        v_hat = second_moment / (1.0 - beta2**step)
        weights += learning_rate * m_hat / (np.sqrt(v_hat) + 1e-8)

        if epoch in (0, 4, 9, 19, 29, 44):
            print(
                json.dumps(
                    {
                        "epoch": epoch + 1,
                        "avgTop3Nll": round(loss / terms, 6),
                        "weightNorm": round(float(np.linalg.norm(weights)), 4),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )
    return weights


def trifecta_probabilities(
    features: np.ndarray, weights: np.ndarray, probability_temperature: float
) -> dict[str, float]:
    logits = (features @ weights.T) / probability_temperature
    result: dict[str, float] = {}
    lanes = list(range(6))
    p_first = softmax(logits[:, 0])
    for first in lanes:
        remaining2 = [lane for lane in lanes if lane != first]
        p_second_local = softmax(logits[remaining2, 1])
        for second_local, second in enumerate(remaining2):
            remaining3 = [lane for lane in remaining2 if lane != second]
            p_third_local = softmax(logits[remaining3, 2])
            for third_local, third in enumerate(remaining3):
                probability = (
                    float(p_first[first])
                    * float(p_second_local[second_local])
                    * float(p_third_local[third_local])
                )
                result[f"{first + 1}-{second + 1}-{third + 1}"] = probability
    return result


def market_probabilities(odds: dict[str, float]) -> dict[str, float]:
    inverse = {combo: 1.0 / value for combo, value in odds.items() if value > 1.0}
    total = sum(inverse.values())
    return {combo: value / total for combo, value in inverse.items()} if total > 0 else {}


def rules() -> list[BetRule]:
    return [
        BetRule(temp, ev, edge, rank, plan)
        for temp in PROB_TEMPS
        for ev in EV_MINS
        for edge in EDGE_MINS
        for rank in MODEL_RANKS
        for plan in STAKE_PLANS
    ]


def picks_for_rule(
    model_probs: dict[str, float],
    market_probs: dict[str, float],
    odds: dict[str, float],
    rule: BetRule,
) -> list[str]:
    model_ranked = sorted(model_probs, key=model_probs.get, reverse=True)
    rows: list[tuple[str, float, float, float]] = []
    for combo in model_ranked[: rule.max_model_rank]:
        probability = model_probs[combo]
        price = odds.get(combo, 0.0)
        market_probability = market_probs.get(combo, 0.0)
        if price <= 1.0 or market_probability <= 0:
            continue
        expected_return = probability * price
        edge = probability / market_probability
        if expected_return >= rule.ev_min and edge >= rule.edge_min:
            rows.append((combo, expected_return, edge, probability))
    rows.sort(key=lambda row: (row[1], row[2], row[3]), reverse=True)
    needed = len(STAKE_PLANS[rule.plan])
    return [row[0] for row in rows[:needed]]


def evaluate_rule(
    rule: BetRule,
    samples: list[RaceSample],
    odds_by_code: dict[str, dict[str, float]],
    weights: np.ndarray,
) -> Stats:
    stats = Stats()
    for sample in samples:
        odds = odds_by_code.get(sample.code)
        if not odds:
            continue
        market_probs = market_probabilities(odds)
        if len(market_probs) < 100:
            continue
        model_probs = trifecta_probabilities(
            sample.features, weights, rule.probability_temperature
        )
        picks = picks_for_rule(model_probs, market_probs, odds, rule)
        stakes = STAKE_PLANS[rule.plan]
        if len(picks) != len(stakes):
            continue
        actual = "-".join(str(lane) for lane in sample.finish)
        if actual in picks:
            index = picks.index(actual)
            paid = sample.payout * (stakes[index] // 100)
            stats.add(True, paid)
        else:
            stats.add(False, 0)
    return stats


def top3_hit_rate(samples: list[RaceSample], weights: np.ndarray) -> float:
    hits = 0
    for sample in samples:
        probabilities = trifecta_probabilities(sample.features, weights, 1.0)
        picks = sorted(probabilities, key=probabilities.get, reverse=True)[:4]
        actual = "-".join(str(lane) for lane in sample.finish)
        hits += int(actual in picks)
    return hits * 100.0 / len(samples) if samples else 0.0


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

    payloads: dict[date, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_day, day): day for day in dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                payloads[day] = payload
            elif error != "404":
                raise SystemExit(f"race download failed {day}: {error}")

    learning_payload = json.loads(args.learning.read_text(encoding="utf-8"))
    samples = build_samples(dates, payloads, learning_payload)
    train_samples = [sample for sample in samples if sample.day <= TRAIN_THROUGH]
    tune_samples = [sample for sample in samples if ODDS_FROM <= sample.day <= TUNE_THROUGH]
    holdout_samples = [sample for sample in samples if sample.day >= HOLDOUT_FROM]
    if len(train_samples) < 20000:
        raise SystemExit(f"not enough training races: {len(train_samples)}")

    feature_count = int(train_samples[0].features.shape[1])
    weights = fit_position_models(train_samples, feature_count)

    odds_dates = [day for day in dates if day >= ODDS_FROM]
    odds_by_code: dict[str, dict[str, float]] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 12))) as pool:
        futures = {pool.submit(fetch_odds_day, day): day for day in odds_dates}
        for future in as_completed(futures):
            day, payload, error = future.result()
            if payload is not None:
                for code, values in payload.items():
                    odds_by_code[code] = values
            elif error != "404":
                raise SystemExit(f"odds download failed {day}: {error}")

    rule_grid = rules()
    rows: list[dict[str, Any]] = []
    for index, rule in enumerate(rule_grid, 1):
        tune_stats = evaluate_rule(rule, tune_samples, odds_by_code, weights)
        rows.append({
            "rule": asdict(rule),
            "stakes": list(STAKE_PLANS[rule.plan]),
            "tune": tune_stats.payload(),
        })
        if index % 100 == 0:
            print(f"evaluated {index}/{len(rule_grid)} betting rules", flush=True)

    eligible = [row for row in rows if row["tune"]["races"] >= 120]
    eligible.sort(key=lambda row: (row["tune"]["roi"], row["tune"]["races"]), reverse=True)
    selected = eligible[0] if eligible else None
    if selected is None:
        raise SystemExit("no betting rule met the tune sample minimum")

    selected_rule = BetRule(**selected["rule"])
    holdout_stats = evaluate_rule(selected_rule, holdout_samples, odds_by_code, weights)
    selected["holdout"] = holdout_stats.payload()
    passes = (
        selected["tune"]["roi"] > 100.0
        and holdout_stats.races >= 60
        and holdout_stats.payload()["roi"] > 100.0
    )

    # Diagnostic only: calculate holdout for top 20 tune rules, not for selection.
    diagnostics: list[dict[str, Any]] = []
    for row in eligible[:20]:
        rule = BetRule(**row["rule"])
        holdout = evaluate_rule(rule, holdout_samples, odds_by_code, weights).payload()
        diagnostics.append({**row, "holdout": holdout})

    payload = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "trainFrom": "2026-01-01",
        "trainThrough": TRAIN_THROUGH.isoformat(),
        "tuneFrom": ODDS_FROM.isoformat(),
        "tuneThrough": TUNE_THROUGH.isoformat(),
        "holdoutFrom": HOLDOUT_FROM.isoformat(),
        "trainRaces": len(train_samples),
        "tuneRacesWithProgram": len(tune_samples),
        "holdoutRacesWithProgram": len(holdout_samples),
        "featureCount": feature_count,
        "betRuleCount": len(rule_grid),
        "modelTop4HitRateTrain": round(top3_hit_rate(train_samples, weights), 2),
        "modelTop4HitRateTune": round(top3_hit_rate(tune_samples, weights), 2),
        "modelTop4HitRateHoldout": round(top3_hit_rate(holdout_samples, weights), 2),
        "weights": weights.round(8).tolist(),
        "selectionRule": "model fit Jan-Jun; highest Jul19-Aug ROI with >=120 races; Sep never used to select",
        "selectedFromTune": selected,
        "selectedPassesHoldout": passes,
        "topTuneDiagnostics": diagnostics,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps({
        "trainRaces": len(train_samples),
        "featureCount": feature_count,
        "modelTop4HitRateHoldout": payload["modelTop4HitRateHoldout"],
        "selected": selected,
        "passesHoldout": passes,
    }, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
