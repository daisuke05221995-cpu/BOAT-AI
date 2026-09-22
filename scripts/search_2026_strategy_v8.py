#!/usr/bin/env python3
"""Walk-forward strategy search with September kept as the final holdout.

Protocol:
- Jan-Apr starts the conditional finish-order model.
- May, Jun, Jul and Aug are generated walk-forward: each month is predicted by a model
  trained only through the preceding month.
- May-Aug are development months used to choose race-selectivity gates and variable
  1-10 point ticket rules.
- Sep-latest is evaluated exactly once, and only when the predeclared development rule
  passes. September is never used to choose thresholds, point count or allocation.

Historical closing odds are unavailable, so the live final-odds gate is excluded.
"""

from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_2026_strategy as v6
import search_2026_strategy_v7 as v7
from build_2026_backtest import JST, LearningProfile

BUDGET_UNITS = 12
BUDGET = 1200
DEV_MONTHS = (5, 6, 7, 8)
POINT_OPTIONS = (1, 2, 3, 4, 6, 8, 10)
COVERAGE_OPTIONS = (0.10, 0.15, 0.20, 0.30, 0.40)
ALLOCATION_MODES = ("equal", "probability")
MAX_WIND_OPTIONS = (2, 4, 99)
MAX_COURSE_CHANGES = (0, 1, 6)
LEADER_FILTERS = ("lane1", "all")
QUANTILES = (0.0, 0.50, 0.70, 0.85, 0.93)
KEEP_GATES = 60
MIN_MONTH_BUYS = 20
MIN_DEV_BUYS = 150


def month_end(month: int) -> date:
    return date(2026, month + 1, 1) - timedelta(days=1) if month < 12 else date(2026, 12, 31)


def q_options(values: list[float]) -> list[float]:
    arr = np.asarray(values, dtype=np.float64)
    if len(arr) == 0:
        return [0.0]
    return sorted({round(float(np.quantile(arr, q)), 6) for q in QUANTILES})


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
            "ranked": ranked,
            "topProbability": top,
            "trifectaGap": max(0.0, top - second),
            "top3Share": float(sum(float(item["probability"]) for item in ranked[:3])),
            "winnerProbability": float(winner_order[0]),
            "winnerGap": float(max(0.0, winner_order[0] - winner_order[1])),
            "leaderLane": int(np.argmax(first_probs)) + 1,
            "wind": int(rec["wind"]),
            "courseChanges": int(rec["courseChanges"]),
            "combo": str(rec["combo"]),
            "amount": int(rec["amount"]),
        })
    return signals


def passes_gate(signal: dict[str, Any], cfg: dict[str, Any]) -> bool:
    return (
        float(signal["topProbability"]) >= float(cfg["minTopProbability"])
        and float(signal["winnerProbability"]) >= float(cfg["minWinnerProbability"])
        and float(signal["winnerGap"]) >= float(cfg["minWinnerGap"])
        and float(signal["trifectaGap"]) >= float(cfg["minTrifectaGap"])
        and float(signal["top3Share"]) >= float(cfg["minTop3Share"])
        and int(signal["wind"]) <= int(cfg["maxWind"])
        and int(signal["courseChanges"]) <= int(cfg["maxCourseChanges"])
        and (cfg["leaderFilter"] != "lane1" or int(signal["leaderLane"]) == 1)
    )


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


def combine(items: list[dict[str, Any]]) -> dict[str, Any]:
    raw = empty_stats()
    for item in items:
        for key in raw:
            raw[key] += int(item.get(key, 0))
    return finalize(raw)


def allocate(probabilities: list[float], mode: str) -> list[int]:
    return v6.allocate_units(probabilities, mode)


def choose_ticket(signal: dict[str, Any], cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], list[int]]:
    if not passes_gate(signal, cfg):
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
    probs = [float(item["probability"]) for item in picked]
    return picked, allocate(probs, str(cfg["allocationMode"]))


def evaluate(signals: list[dict[str, Any]], cfg: dict[str, Any]) -> dict[str, Any]:
    raw = empty_stats()
    for signal in signals:
        picks, units = choose_ticket(signal, cfg)
        if not picks:
            continue
        raw["purchaseRaces"] += 1
        raw["stake"] += BUDGET
        for idx, item in enumerate(picks):
            if str(item["combo"]) == signal["combo"]:
                raw["hits"] += 1
                raw["payout"] += int(signal["amount"]) * int(units[idx])
                break
    return finalize(raw)


def one_point_stats(signals: list[dict[str, Any]], gate: dict[str, Any]) -> dict[str, Any]:
    cfg = {
        **gate,
        "maxPoints": 1,
        "coverage": 1.0,
        "allocationMode": "equal",
        "budget": BUDGET,
    }
    return evaluate(signals, cfg)


def profitable(stats: dict[str, Any]) -> bool:
    return int(stats["purchaseRaces"]) > 0 and int(stats["profit"]) > 0 and float(stats["roi"]) > 100.0


def robust_score(monthly: dict[str, dict[str, Any]], total: dict[str, Any]) -> tuple[Any, ...]:
    values = list(monthly.values())
    positive = sum(1 for item in values if profitable(item))
    valid = sum(1 for item in values if int(item["purchaseRaces"]) >= MIN_MONTH_BUYS)
    worst = min((float(item["roi"]) for item in values if int(item["purchaseRaces"]) > 0), default=0.0)
    return (valid, positive, worst, float(total["roi"]), int(total["purchaseRaces"]))


def walk_forward_signals(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    train_start = date(2026, 1, 1)
    for month in DEV_MONTHS:
        previous_end = month_end(month - 1)
        model = v6.fit_conditional_model(records, train_start, previous_end)
        key = f"2026-{month:02d}"
        result[key] = make_signals(model, records, date(2026, month, 1), month_end(month))
    return result


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
        raise SystemExit("September holdout has not started")

    learning = LearningProfile(json.loads(args.learning.read_text(encoding="utf-8")))
    records, failed_days = v7.build_records(args.start, data_end, learning, args.workers)
    if failed_days:
        raise SystemExit(f"download failures: {failed_days}")

    dev = walk_forward_signals(records)
    all_dev = [signal for month in DEV_MONTHS for signal in dev[f"2026-{month:02d}"]]
    if len(all_dev) < 3000:
        raise RuntimeError(f"too few development signals: {len(all_dev)}")

    options = {
        "top": q_options([s["topProbability"] for s in all_dev]),
        "winner": q_options([s["winnerProbability"] for s in all_dev]),
        "winnerGap": q_options([s["winnerGap"] for s in all_dev]),
        "trifectaGap": q_options([s["trifectaGap"] for s in all_dev]),
        "top3": q_options([s["top3Share"] for s in all_dev]),
    }

    gate_candidates: list[dict[str, Any]] = []
    for min_top in options["top"]:
        for min_winner in options["winner"]:
            for min_winner_gap in options["winnerGap"]:
                for min_tri_gap in options["trifectaGap"]:
                    for min_top3 in options["top3"]:
                        for max_wind in MAX_WIND_OPTIONS:
                            for max_changes in MAX_COURSE_CHANGES:
                                for leader_filter in LEADER_FILTERS:
                                    gate = {
                                        "minTopProbability": min_top,
                                        "minWinnerProbability": min_winner,
                                        "minWinnerGap": min_winner_gap,
                                        "minTrifectaGap": min_tri_gap,
                                        "minTop3Share": min_top3,
                                        "maxWind": max_wind,
                                        "maxCourseChanges": max_changes,
                                        "leaderFilter": leader_filter,
                                    }
                                    monthly = {key: one_point_stats(signals, gate) for key, signals in dev.items()}
                                    total = combine(list(monthly.values()))
                                    if total["purchaseRaces"] < MIN_DEV_BUYS:
                                        continue
                                    gate_candidates.append({
                                        "gate": gate,
                                        "monthly": monthly,
                                        "total": total,
                                        "score": robust_score(monthly, total),
                                    })

    if not gate_candidates:
        raise RuntimeError("no gate candidates with enough purchases")
    gate_candidates.sort(key=lambda item: item["score"], reverse=True)
    gate_candidates = gate_candidates[:KEEP_GATES]

    ticket_candidates: list[dict[str, Any]] = []
    for gate_item in gate_candidates:
        gate = gate_item["gate"]
        for max_points in POINT_OPTIONS:
            for coverage in COVERAGE_OPTIONS:
                for allocation_mode in ALLOCATION_MODES:
                    cfg = {
                        **gate,
                        "maxPoints": max_points,
                        "coverage": coverage,
                        "allocationMode": allocation_mode,
                        "budget": BUDGET,
                    }
                    monthly = {key: evaluate(signals, cfg) for key, signals in dev.items()}
                    total = combine(list(monthly.values()))
                    score = robust_score(monthly, total)
                    ticket_candidates.append({
                        "config": cfg,
                        "developmentMonths": monthly,
                        "development": total,
                        "score": score,
                    })

    def qualifies(item: dict[str, Any]) -> bool:
        months = list(item["developmentMonths"].values())
        positive = sum(1 for stats in months if profitable(stats))
        return (
            int(item["development"]["purchaseRaces"]) >= MIN_DEV_BUYS
            and float(item["development"]["roi"]) >= 103.0
            and positive >= 3
            and all(int(stats["purchaseRaces"]) >= MIN_MONTH_BUYS for stats in months)
            and min(float(stats["roi"]) for stats in months) >= 90.0
        )

    eligible = [item for item in ticket_candidates if qualifies(item)]
    pool = eligible or ticket_candidates
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

    final_start = date(2026, 9, 1)
    final_end = data_end
    final_stats: dict[str, Any] | None = None
    qualified_for_release = False
    if qualified_for_final and final_end >= final_start:
        model_final = v6.fit_conditional_model(records, date(2026, 1, 1), date(2026, 8, 31))
        final_signals = make_signals(model_final, records, final_start, final_end)
        final_stats = evaluate(final_signals, cfg)
        qualified_for_release = bool(
            int(final_stats["purchaseRaces"]) >= 20
            and profitable(final_stats)
        )

    may = selected["developmentMonths"]["2026-05"]
    june = selected["developmentMonths"]["2026-06"]
    july = selected["developmentMonths"]["2026-07"]
    august = selected["developmentMonths"]["2026-08"]

    result = {
        "schemaVersion": 8,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "dataThrough": data_end.isoformat(),
        "method": "walk-forward May-Aug development + staged race gate and variable 1-10 point ticket search; September untouched final holdout",
        "oddsFinalGateIncluded": False,
        "periods": {
            "train": ["2026-01-01", "2026-04-30"],
            "tune": ["2026-05-01", "2026-06-30"],
            "validation": ["2026-07-01", "2026-08-31"],
            "development": ["2026-05-01", "2026-08-31"],
            "final": [final_start.isoformat(), final_end.isoformat()],
        },
        "selected": {
            "config": cfg,
            "tuneMonths": {"2026-05": may, "2026-06": june},
            "tune": combine([may, june]),
            "developmentMonths": selected["developmentMonths"],
            "development": selected["development"],
        },
        "validationMonths": {"2026-07": july, "2026-08": august},
        "validation": combine([july, august]),
        "final": final_stats if final_stats is not None else {"withheld": True},
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "releaseRule": "May-Aug walk-forward development >=103% ROI, at least 3/4 positive months, every month >=20 buys and >=90% ROI; only then Sep-latest must be >100% with >=20 buys",
        "gateCandidatesRetained": len(gate_candidates),
        "ticketCandidates": len(ticket_candidates),
        "topCandidates": pool[:20],
        "notes": [
            "Jul-Aug are development data in schema 8 because earlier experiments already inspected them.",
            "September is the untouched final holdout and is not used for threshold, point-count or allocation selection.",
            "Each May-Aug month is predicted by a model trained only through the preceding month.",
            "Ticket count varies by race through cumulative probability coverage, capped at 1-10 points.",
            "Historical closing odds are unavailable, so the live final-odds filter is excluded from this test.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "selected": result["selected"],
        "validationMonths": result["validationMonths"],
        "qualifiedForFinal": qualified_for_final,
        "qualifiedForRelease": qualified_for_release,
        "final": result["final"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
