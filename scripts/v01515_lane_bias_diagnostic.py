#!/usr/bin/env python3
"""Audit the Android v0.15.15 AI-first strategy on the sealed-safe r4 development cache.

This is a diagnostic only: it reproduces the production strategy as-is and DOES NOT
search/tune thresholds. It is restricted to 2025-07-01..2025-08-31 and refuses any
September/Q4 rows.
"""
from __future__ import annotations

import argparse
import itertools
import json
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np

COMBOS = np.asarray(list(itertools.permutations(range(6), 3)), dtype=np.int16)
COMBO_TEXT = np.asarray(["-".join(str(x + 1) for x in row) for row in COMBOS])

BUDGET = 1200
MAX_POINTS = 2
MODEL_WEIGHT = 0.80
MIN_EV = 1.05
MIN_PROBABILITY = 0.005
MAX_ODDS = 150.0
MIN_MARKET_EDGE_RATIO = 1.08
MAX_FIRST_FORM_RANK = 2
ALT_FIRST_SCORE_RATIO = 0.88
SCORE_TEMPERATURE = 14.0

COURSE_PRIOR = np.asarray([8.0, 4.0, 2.0, 0.0, -1.5, -3.0], dtype=np.float64)


def nvl(x: np.ndarray, value: float = 0.0) -> np.ndarray:
    return np.where(np.isfinite(x), x, value)


def form_score(boat: np.ndarray) -> np.ndarray:
    """Exact port of AverageRoiReferenceStrategy.formScore for cached pre-race fields."""
    national = nvl(boat[:, :, 0]) * 5.2
    local = nvl(boat[:, :, 1]) * 2.6
    motor = nvl(boat[:, :, 6]) * 0.22
    assigned_boat = nvl(boat[:, :, 8]) * 0.08
    avg_start = boat[:, :, 10]
    start = np.where(np.isfinite(avg_start), np.maximum(0.0, (0.22 - avg_start) * 58.0), 0.0)
    exhibition = boat[:, :, 15]
    exhibition_score = np.where(
        np.isfinite(exhibition), np.maximum(-5.0, (6.95 - exhibition) * 18.0), 0.0
    )
    preview_start = boat[:, :, 16]
    preview_start_score = np.where(
        np.isfinite(preview_start), np.maximum(-4.0, (0.18 - preview_start) * 32.0), 0.0
    )
    return national + local + motor + assigned_boat + start + exhibition_score + preview_start_score


def form_ranks(scores: np.ndarray) -> np.ndarray:
    ranks = np.empty_like(scores, dtype=np.int16)
    lanes = np.arange(6)
    for i, row in enumerate(scores):
        # Kotlin map iteration is lane 1..6 and sortedByDescending is stable.
        order = np.lexsort((lanes, -row))
        ranks[i, order] = np.arange(1, 7)
    return ranks


def summarize(stake: np.ndarray, payout: np.ndarray, hits: np.ndarray) -> dict:
    stake_sum = int(stake.sum())
    payout_sum = int(np.rint(payout.sum()))
    purchases = int(np.count_nonzero(stake))
    hit_count = int(np.count_nonzero(hits))
    return {
        "purchaseRaces": purchases,
        "hits": hit_count,
        "hitRate": round(hit_count * 100.0 / purchases, 3) if purchases else None,
        "stake": stake_sum,
        "payout": payout_sum,
        "profit": payout_sum - stake_sum,
        "roi": round(payout_sum * 100.0 / stake_sum, 3) if stake_sum else None,
    }


def lane_metrics(mask: np.ndarray, primary_first: np.ndarray, actual_first: np.ndarray,
                 stake: np.ndarray, payout: np.ndarray, trifecta_hit: np.ndarray) -> dict:
    out = {}
    base = int(np.count_nonzero(mask))
    for lane in range(1, 7):
        m = mask & (primary_first == lane)
        count = int(np.count_nonzero(m))
        first_hits = int(np.count_nonzero(m & (actual_first == lane)))
        accounting = summarize(stake[m], payout[m], trifecta_hit[m])
        out[str(lane)] = {
            "primaryPredictions": count,
            "primaryShare": round(count * 100.0 / base, 3) if base else None,
            "firstPlaceHits": first_hits,
            "firstPlaceHitRate": round(first_hits * 100.0 / count, 3) if count else None,
            "trifecta": accounting,
        }
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cache", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    args = ap.parse_args()

    with np.load(args.cache, allow_pickle=False) as z:
        required = [
            "day_ordinal", "month", "venue", "race_number", "actual_index", "amount",
            "current", "usable", "odds_usable", "odds", "combos",
        ]
        missing = [k for k in required if k not in z.files]
        if missing:
            raise SystemExit(f"cache missing: {missing}")
        c = {k: z[k] for k in required}

    dates = np.asarray([date.fromordinal(int(x)) for x in c["day_ordinal"]], dtype=object)
    if len(dates) == 0:
        raise SystemExit("empty development cache")
    if min(dates) < date(2025, 7, 1) or max(dates) > date(2025, 8, 31):
        raise SystemExit(f"date fence violated: {min(dates)}..{max(dates)}")
    if set(int(x) for x in c["month"]) != {7, 8}:
        raise SystemExit("diagnostic is July-August only")
    if not np.array_equal(c["combos"], COMBO_TEXT):
        raise SystemExit("combination order mismatch")

    boat = c["current"].astype(np.float64)
    if boat.ndim != 3 or boat.shape[1] != 6 or boat.shape[2] < 18:
        raise SystemExit(f"unexpected current feature shape {boat.shape}")
    odds = c["odds"].astype(np.float64)
    usable = c["usable"].astype(bool) & c["odds_usable"].astype(bool)
    usable &= np.isfinite(odds).all(axis=1) & (odds > 1.0).all(axis=1)

    form = form_score(boat)
    ranks = form_ranks(form)

    course = boat[:, :, 17]
    if np.any(usable & ~np.isfinite(course).all(axis=1)):
        raise SystemExit("usable race has missing preview course")
    course_idx = np.clip(np.nan_to_num(course, nan=6.0).astype(int) - 1, 0, 5)
    raw_score = form + COURSE_PRIOR[course_idx]
    max_score = np.max(raw_score, axis=1, keepdims=True)
    weights = np.exp((raw_score - max_score) / SCORE_TEMPERATURE)
    weight_total = weights.sum(axis=1)

    f = COMBOS[:, 0]
    s = COMBOS[:, 1]
    t = COMBOS[:, 2]
    wf = weights[:, f]
    ws = weights[:, s]
    wt = weights[:, t]
    d2 = weight_total[:, None] - wf
    d3 = d2 - ws
    model_p = (wf / weight_total[:, None]) * (ws / d2) * (wt / d3)
    model_p /= model_p.sum(axis=1, keepdims=True)

    inv = 1.0 / odds
    market_p = inv / inv.sum(axis=1, keepdims=True)
    raw_forecast = np.exp(
        MODEL_WEIGHT * np.log(np.maximum(model_p, 1e-12))
        + (1.0 - MODEL_WEIGHT) * np.log(np.maximum(market_p, 1e-12))
    )
    forecast_p = raw_forecast / raw_forecast.sum(axis=1, keepdims=True)
    edge = model_p / market_p
    ev = forecast_p * odds
    first_rank = ranks[:, f]

    candidate = (
        usable[:, None]
        & (first_rank <= MAX_FIRST_FORM_RANK)
        & (odds <= MAX_ODDS)
        & (forecast_p >= MIN_PROBABILITY)
        & (ev >= MIN_EV)
        & (edge >= MIN_MARKET_EDGE_RATIO)
    )
    ranking = np.where(candidate, ev * np.minimum(edge, 2.5), -np.inf)

    n = len(usable)
    primary_combo = np.full(n, -1, dtype=np.int16)
    second_combo = np.full(n, -1, dtype=np.int16)
    selected_count = np.zeros(n, dtype=np.int8)

    for i in np.flatnonzero(usable):
        valid = np.flatnonzero(candidate[i])
        if not len(valid):
            continue
        order = valid[np.lexsort((-forecast_p[i, valid], -ev[i, valid], -ranking[i, valid]))]
        primary = int(order[0])
        primary_combo[i] = primary
        selected = [primary]
        if MAX_POINTS > 1 and len(order) > 1:
            primary_first_lane = int(COMBOS[primary, 0])
            alternate = None
            for combo in order[1:]:
                combo = int(combo)
                if (
                    int(COMBOS[combo, 0]) != primary_first_lane
                    and ranking[i, combo] >= ranking[i, primary] * ALT_FIRST_SCORE_RATIO
                ):
                    alternate = combo
                    break
            second = alternate if alternate is not None else int(order[1])
            second_combo[i] = second
            selected.append(second)
        selected_count[i] = len(selected)

    buy = primary_combo >= 0
    actual_combo = c["actual_index"].astype(int)
    actual_first = COMBOS[actual_combo, 0] + 1
    primary_first = np.where(buy, COMBOS[np.maximum(primary_combo, 0), 0] + 1, 0)

    stake = np.where(buy, BUDGET, 0).astype(int)
    payout = np.zeros(n, dtype=np.float64)
    trifecta_hit = np.zeros(n, dtype=bool)
    for i in np.flatnonzero(buy):
        picks = [int(primary_combo[i])]
        if second_combo[i] >= 0:
            picks.append(int(second_combo[i]))
        point_count = len(picks)
        units_total = BUDGET // 100
        base = units_total // point_count
        rem = units_total % point_count
        stakes = [(base + (1 if j < rem else 0)) * 100 for j in range(point_count)]
        for combo, ticket_stake in zip(picks, stakes):
            if combo == actual_combo[i]:
                payout[i] = (ticket_stake // 100) * int(c["amount"][i])
                trifecta_hit[i] = True
                break

    primary_first_hit = buy & (primary_first == actual_first)

    model_first_marginal = np.column_stack([model_p[:, f == lane].sum(axis=1) for lane in range(6)])
    market_first_marginal = np.column_stack([market_p[:, f == lane].sum(axis=1) for lane in range(6)])
    model_top_first = model_first_marginal.argmax(axis=1) + 1
    market_top_first = market_first_marginal.argmax(axis=1) + 1

    ticket_first_counts = Counter()
    for i in np.flatnonzero(buy):
        ticket_first_counts[int(COMBOS[int(primary_combo[i]), 0] + 1)] += 1
        if second_combo[i] >= 0:
            ticket_first_counts[int(COMBOS[int(second_combo[i]), 0] + 1)] += 1
    total_tickets = sum(ticket_first_counts.values())

    monthly = {}
    for month in (7, 8):
        m = buy & (c["month"].astype(int) == month)
        month_total = int(np.count_nonzero(m))
        monthly[f"2025-{month:02d}"] = {
            "accounting": summarize(stake[m], payout[m], trifecta_hit[m]),
            "primaryLane1Share": round(np.count_nonzero(m & (primary_first == 1)) * 100.0 / month_total, 3) if month_total else None,
            "primaryFirstHitRate": round(np.count_nonzero(m & (primary_first == actual_first)) * 100.0 / month_total, 3) if month_total else None,
            "marketAgreementRate": round(np.count_nonzero(m & (primary_first == market_top_first)) * 100.0 / month_total, 3) if month_total else None,
        }

    buy_count = int(np.count_nonzero(buy))
    usable_count = int(np.count_nonzero(usable))
    lane1_buy = buy & (primary_first == 1)
    non1_buy = buy & (primary_first != 1)
    market_agree = buy & (primary_first == market_top_first)
    market_disagree = buy & (primary_first != market_top_first)

    def rate(num: int, den: int) -> float | None:
        return round(num * 100.0 / den, 3) if den else None

    result = {
        "schemaVersion": 1,
        "strategy": "Android v0.15.15 AverageRoiReferenceStrategy exact-formula audit",
        "period": "2025-07-01..2025-08-31",
        "holdoutOpened": False,
        "septemberOpened": False,
        "tuningPerformed": False,
        "thresholds": {
            "budget": BUDGET,
            "maxPoints": MAX_POINTS,
            "modelWeight": MODEL_WEIGHT,
            "minEv": MIN_EV,
            "minProbability": MIN_PROBABILITY,
            "maxOdds": MAX_ODDS,
            "minMarketEdgeRatio": MIN_MARKET_EDGE_RATIO,
            "maxFirstFormRank": MAX_FIRST_FORM_RANK,
            "alternateFirstScoreRatio": ALT_FIRST_SCORE_RATIO,
            "scoreTemperature": SCORE_TEMPERATURE,
        },
        "population": {
            "cacheRaces": int(n),
            "usableRaces": usable_count,
            "buyRaces": buy_count,
            "buyRate": rate(buy_count, usable_count),
        },
        "accounting": summarize(stake[buy], payout[buy], trifecta_hit[buy]),
        "primaryFirst": {
            "accuracy": rate(int(np.count_nonzero(primary_first_hit)), buy_count),
            "distribution": lane_metrics(buy, primary_first, actual_first, stake, payout, trifecta_hit),
        },
        "ticketFirstDistribution": {
            str(lane): {
                "tickets": int(ticket_first_counts.get(lane, 0)),
                "share": rate(int(ticket_first_counts.get(lane, 0)), total_tickets),
            }
            for lane in range(1, 7)
        },
        "actualWinnerDistribution": {
            "usablePopulation": {
                str(lane): rate(int(np.count_nonzero(usable & (actual_first == lane))), usable_count)
                for lane in range(1, 7)
            },
            "buyPopulation": {
                str(lane): rate(int(np.count_nonzero(buy & (actual_first == lane))), buy_count)
                for lane in range(1, 7)
            },
        },
        "laneOne": {
            "primaryPredictionShare": rate(int(np.count_nonzero(lane1_buy)), buy_count),
            "actualWinnerShareInBuyPopulation": rate(int(np.count_nonzero(buy & (actual_first == 1))), buy_count),
            "firstPlaceHitRateWhenPredicted": rate(int(np.count_nonzero(lane1_buy & (actual_first == 1))), int(np.count_nonzero(lane1_buy))),
            "firstPlaceHitRateWhenPredictingOther": rate(int(np.count_nonzero(non1_buy & (primary_first == actual_first))), int(np.count_nonzero(non1_buy))),
            "marketTopFirstLane1Share": rate(int(np.count_nonzero(buy & (market_top_first == 1))), buy_count),
            "modelTopFirstLane1Share": rate(int(np.count_nonzero(buy & (model_top_first == 1))), buy_count),
            "ticketFirstLane1Share": rate(int(ticket_first_counts.get(1, 0)), total_tickets),
            "accountingWhenPrimary1": summarize(stake[lane1_buy], payout[lane1_buy], trifecta_hit[lane1_buy]),
            "accountingWhenPrimaryOther": summarize(stake[non1_buy], payout[non1_buy], trifecta_hit[non1_buy]),
        },
        "marketAgreement": {
            "primaryFirstEqualsMarketTop": rate(int(np.count_nonzero(market_agree)), buy_count),
            "firstPlaceAccuracyWhenAgree": rate(int(np.count_nonzero(market_agree & (primary_first == actual_first))), int(np.count_nonzero(market_agree))),
            "firstPlaceAccuracyWhenDisagree": rate(int(np.count_nonzero(market_disagree & (primary_first == actual_first))), int(np.count_nonzero(market_disagree))),
            "racesAgree": int(np.count_nonzero(market_agree)),
            "racesDisagree": int(np.count_nonzero(market_disagree)),
        },
        "firstFormRank": {
            "rank1": int(np.count_nonzero(buy & (ranks[np.arange(n), np.maximum(primary_first - 1, 0)] == 1))),
            "rank2": int(np.count_nonzero(buy & (ranks[np.arange(n), np.maximum(primary_first - 1, 0)] == 2))),
        },
        "monthly": monthly,
        "notes": [
            "No threshold or parameter was changed after observing these outcomes.",
            "The diagnostic uses the r4 July-August development cache only; September and 2025 Q4 remain unopened.",
            "Archived odds capture time is not verified as exactly five minutes before close, so ROI is diagnostic rather than live-execution proof.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    l1 = result["laneOne"]
    acct = result["accounting"]
    lines = [
        "# v0.15.15 1着艇バイアス診断",
        "",
        "期間: 2025-07-01〜2025-08-31（r4開発期間のみ。9月/Q4未開封）",
        "",
        f"- 対象usable: {usable_count:,}レース / BUY: {buy_count:,}レース（{result['population']['buyRate']}%）",
        f"- 1号艇を主1着予想: {l1['primaryPredictionShare']}%",
        f"- BUY母集団で実際に1号艇が勝った率: {l1['actualWinnerShareInBuyPopulation']}%",
        f"- 市場が1号艇を最有力1着とした率: {l1['marketTopFirstLane1Share']}%",
        f"- AI単体が1号艇を最有力1着とした率: {l1['modelTopFirstLane1Share']}%",
        f"- 1号艇主予想時の1着的中率: {l1['firstPlaceHitRateWhenPredicted']}%",
        f"- 2〜6号艇主予想時の1着的中率: {l1['firstPlaceHitRateWhenPredictingOther']}%",
        f"- 市場と主1着候補が一致: {result['marketAgreement']['primaryFirstEqualsMarketTop']}%",
        f"- 3連単: {acct['purchaseRaces']:,}購入 / {acct['hits']:,}的中 / ROI {acct['roi']}%",
        "",
        "## 艇番別 主1着予想",
        "",
        "|艇|予想数|予想比率|1着的中率|3連単ROI|",
        "|---:|---:|---:|---:|---:|",
    ]
    for lane in range(1, 7):
        x = result["primaryFirst"]["distribution"][str(lane)]
        lines.append(
            f"|{lane}|{x['primaryPredictions']:,}|{x['primaryShare']}%|{x['firstPlaceHitRate']}%|{x['trifecta']['roi']}%|"
        )
    lines += [
        "",
        "## 月別",
        "",
        "|月|購入|ROI|1号艇主予想率|主1着的中率|市場一致率|",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for key, value in monthly.items():
        a = value["accounting"]
        lines.append(
            f"|{key}|{a['purchaseRaces']:,}|{a['roi']}%|{value['primaryLane1Share']}%|{value['primaryFirstHitRate']}%|{value['marketAgreementRate']}%|"
        )
    lines += [
        "",
        "この診断ではパラメータ探索・閾値調整を行っていない。結果を見てから同じ期間へ多数の閾値を当て直す用途には使わない。",
    ]
    args.report.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({
        "usable": usable_count,
        "buy": buy_count,
        "lane1PrimaryShare": l1["primaryPredictionShare"],
        "lane1ActualWinnerShare": l1["actualWinnerShareInBuyPopulation"],
        "marketAgreement": result["marketAgreement"]["primaryFirstEqualsMarketTop"],
        "roi": acct["roi"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
