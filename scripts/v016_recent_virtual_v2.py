#!/usr/bin/env python3
"""Flexible rolling retrospective Model A virtual P/L feed.

Forecast probabilities come from the frozen market-free v0.16 Model A with player
history strictly through the previous calendar day. Bet selection never sees the
race result. After a race is already over, archived final-like trifecta odds are
used only to choose retrospective point count / stake allocation, while official
settled payout from boatraceopenapi/results is used for settlement.

This is deliberately NOT a realizable pre-close ROI backtest. The odds archive has
no proven T-5 acquisition timestamp, so every output keeps preCloseOddsClaim=false
and automatic BUY remains disabled.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

import v016_recent_virtual as base
from v016_r4_player_history import PlayerHistory, enrich

ROOT = Path(__file__).resolve().parents[1]
STRATEGY_ID = "model-a-retro-flex-v2"
WINDOW_DAYS = 30
MIN_POINTS = 4
MAX_POINTS = 8
MIN_BUDGET = 1_000
MAX_BUDGET = 3_000
STAKE_STEP = 100
UTILITY_BANKROLL = 30_000.0
ODDS_REPO = "lamrongol/BoatraceOdds"
ODDS_BRANCH = "gh-pages"


def resolve_odds_commit() -> str:
    raw = base.request_bytes(f"https://api.github.com/repos/{ODDS_REPO}/commits/{ODDS_BRANCH}")
    return str(json.loads(raw)["sha"])


def read_odds_day(day: date, commit: str) -> dict[tuple[int, int], np.ndarray]:
    url = (
        f"https://raw.githubusercontent.com/{ODDS_REPO}/{commit}/"
        f"docs/v3/{day.year}/{day:%Y%m%d}.json"
    )
    raw = base.request_bytes(url, agent="BOAT-AI-v016-recent-virtual-v2")
    payload = json.loads(raw)
    rows = payload.get("odds", [])
    keyed: dict[tuple[int, int], np.ndarray] = {}
    for row in rows:
        if row.get("date") != day.isoformat():
            raise ValueError(f"odds date mismatch {day}")
        key = (int(row["stadium_number"]), int(row["number"]))
        if key in keyed:
            raise ValueError(f"duplicate odds race {day} {key}")
        tf = row.get("trifecta_odds") or {}
        values = np.zeros(120, dtype=np.float64)
        for ix, text in enumerate(base.COMBO_TEXT):
            a, b, c = str(text).split("-")
            value = ((tf.get(a) or {}).get(b) or {}).get(c)
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = 0.0
            values[ix] = value if math.isfinite(value) and value > 0 else 0.0
        keyed[key] = values
    return keyed


def load_odds(days: list[date], commit: str) -> tuple[dict[tuple[str, int, int], np.ndarray], Counter]:
    out: dict[tuple[str, int, int], np.ndarray] = {}
    counts = Counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        tasks = {pool.submit(read_odds_day, day, commit): day for day in days}
        for task in as_completed(tasks):
            day = tasks[task]
            try:
                races = task.result()
            except Exception:
                counts["oddsDayFetchFailure"] += 1
                continue
            counts["oddsDayFetched"] += 1
            for (venue, race_number), values in races.items():
                out[(day.isoformat(), venue, race_number)] = values
                if np.count_nonzero(values > 0) == 120:
                    counts["all120OddsRaces"] += 1
                else:
                    counts["incompleteOddsRaces"] += 1
    return out, counts


def first_lane_marginals(prob: np.ndarray) -> np.ndarray:
    marg = np.zeros(6, dtype=np.float64)
    for ix, text in enumerate(base.COMBO_TEXT):
        first = int(str(text).split("-")[0]) - 1
        marg[first] += float(prob[ix])
    return marg


def ranking_score(prob: np.ndarray, odds: np.ndarray) -> np.ndarray:
    edge = prob * odds
    value_factor = np.sqrt(np.clip(edge, 0.55, 1.75))
    return prob * value_factor


def target_conditional_coverage(first_probability: float) -> float:
    if first_probability >= 0.62:
        return 0.49
    if first_probability >= 0.55:
        return 0.54
    if first_probability >= 0.48:
        return 0.59
    if first_probability >= 0.42:
        return 0.64
    return 0.68


def choose_combinations(prob: np.ndarray, odds: np.ndarray) -> tuple[list[int], dict]:
    marg = first_lane_marginals(prob)
    lane_order = np.argsort(-marg, kind="stable")
    primary_lane = int(lane_order[0]) + 1
    second_lane = int(lane_order[1]) + 1
    primary_p = float(marg[lane_order[0]])
    second_p = float(marg[lane_order[1]])
    score = ranking_score(prob, odds)

    by_lane: dict[int, list[int]] = {lane: [] for lane in range(1, 7)}
    for ix, text in enumerate(base.COMBO_TEXT):
        by_lane[int(str(text).split("-")[0])].append(ix)
    for lane in by_lane:
        by_lane[lane].sort(key=lambda ix: (-float(score[ix]), -float(prob[ix]), ix))

    primary_rank = by_lane[primary_lane]
    target = target_conditional_coverage(primary_p)
    k = MAX_POINTS
    running = 0.0
    for candidate_k in range(MIN_POINTS, MAX_POINTS + 1):
        running = sum(float(prob[ix]) for ix in primary_rank[:candidate_k]) / max(primary_p, 1e-12)
        if running >= target:
            k = candidate_k
            break

    # When first-place uncertainty is genuinely broad, reserve only one or two
    # tickets for the second first-lane candidate. Most tickets still expand
    # 2nd/3rd-place patterns under the strongest first lane, matching the observed
    # failure mode without forcing a one-lane world.
    alt_count = 0
    if primary_p < 0.48 and second_p >= 0.25:
        alt_count = 1
    if primary_p < 0.40 and second_p >= 0.30:
        alt_count = 2
    alt_count = min(alt_count, max(0, k - MIN_POINTS))

    selected = primary_rank[: k - alt_count] + by_lane[second_lane][:alt_count]
    selected = sorted(set(selected), key=lambda ix: (-float(score[ix]), -float(prob[ix]), ix))
    while len(selected) < k:
        for ix in np.argsort(-score, kind="stable"):
            if int(ix) not in selected:
                selected.append(int(ix))
                break
    selected = selected[:k]

    coverage = float(sum(prob[ix] for ix in selected))
    primary_conditional = float(
        sum(prob[ix] for ix in selected if str(base.COMBO_TEXT[ix]).startswith(f"{primary_lane}-"))
        / max(primary_p, 1e-12)
    )
    meta = {
        "primaryFirstLane": primary_lane,
        "primaryFirstProbability": primary_p,
        "secondFirstLane": second_lane,
        "secondFirstProbability": second_p,
        "targetConditionalCoverage": target,
        "selectedProbabilityCoverage": coverage,
        "primaryConditionalCoverage": primary_conditional,
        "alternativeFirstTickets": alt_count,
    }
    return selected, meta


def expected_log_utility(prob: np.ndarray, odds: np.ndarray, stakes: list[int]) -> float:
    budget = float(sum(stakes))
    base_wealth = UTILITY_BANKROLL - budget
    if base_wealth <= 0:
        return -1e100
    selected_probability = float(np.sum(prob))
    no_hit_probability = max(0.0, 1.0 - selected_probability)
    utility = no_hit_probability * math.log(base_wealth)
    for p, o, stake in zip(prob, odds, stakes):
        outcome_wealth = base_wealth + float(stake) * float(o)
        if outcome_wealth <= 0:
            return -1e100
        utility += float(p) * math.log(outcome_wealth)
    return utility


def allocate_stakes(prob: np.ndarray, odds: np.ndarray) -> tuple[list[int], dict]:
    k = len(prob)
    stakes = [STAKE_STEP] * k
    snapshots: list[tuple[float, list[int]]] = []

    # Greedily add one 100-yen unit at a time by the largest increase in expected
    # log wealth. This gives a diversified Kelly-like allocation rather than
    # dumping every extra yen onto a single highest-EV combination.
    while sum(stakes) < MAX_BUDGET:
        best_j = None
        best_utility = -1e100
        for j in range(k):
            candidate = list(stakes)
            candidate[j] += STAKE_STEP
            utility = expected_log_utility(prob, odds, candidate)
            if utility > best_utility + 1e-15:
                best_utility = utility
                best_j = j
        if best_j is None:
            break
        stakes[best_j] += STAKE_STEP
        budget = sum(stakes)
        if budget >= MIN_BUDGET:
            snapshots.append((best_utility, list(stakes)))

    if not snapshots:
        raise ValueError("unable to reach minimum budget")
    best_utility, best_stakes = max(snapshots, key=lambda item: item[0])
    budget = sum(best_stakes)
    expected_return = float(
        sum(float(p) * float(o) * float(stake) for p, o, stake in zip(prob, odds, best_stakes))
    )
    expected_profit = expected_return - budget
    return best_stakes, {
        "budget": budget,
        "expectedReturn": expected_return,
        "expectedProfit": expected_profit,
        "expectedRoi": expected_return * 100.0 / budget if budget else 0.0,
        "expectedLogUtility": best_utility,
    }


def make_records(enriched: dict, q: np.ndarray, odds_map: dict[tuple[str, int, int], np.ndarray], counts: Counter) -> list[dict]:
    records = []
    for i in range(len(enriched["month"])):
        if not bool(enriched["usable"][i]):
            continue
        day = date.fromordinal(int(enriched["day_ordinal"][i]))
        venue = int(enriched["venue"][i])
        race_number = int(enriched["race_number"][i])
        odds = odds_map.get((day.isoformat(), venue, race_number))
        if odds is None or np.count_nonzero(odds > 0) != 120:
            counts["skippedMissingAll120Odds"] += 1
            continue

        selected, selection_meta = choose_combinations(q[i], odds)
        selected_prob = np.asarray([float(q[i, ix]) for ix in selected], dtype=np.float64)
        selected_odds = np.asarray([float(odds[ix]) for ix in selected], dtype=np.float64)
        stakes, stake_meta = allocate_stakes(selected_prob, selected_odds)

        combinations = [str(base.COMBO_TEXT[ix]) for ix in selected]
        result_combo = str(enriched["result_combination"][i])
        payout = int(enriched["trifecta_payout"][i])
        hit = result_combo in combinations
        virtual_stake = int(sum(stakes))
        if hit:
            hit_index = combinations.index(result_combo)
            winning_stake = int(stakes[hit_index])
            virtual_payout = payout * winning_stake // 100
        else:
            winning_stake = 0
            virtual_payout = 0

        first_margin = first_lane_marginals(q[i])
        confidence = int(round(float(np.max(first_margin)) * 100.0))
        record = {
            "id": f"{day.isoformat()}-{venue:02d}-{race_number}",
            "date": day.isoformat(),
            "stadiumNumber": venue,
            "raceNumber": race_number,
            "combinations": combinations,
            "probabilities": [float(x) for x in selected_prob],
            "endedOdds": [float(x) for x in selected_odds],
            "stakes": [int(x) for x in stakes],
            "stakePerPick": 100,
            "pointCount": len(combinations),
            "resultCombination": result_combo,
            "trifectaPayout": payout,
            "settlementMultiplier": payout / 100.0,
            "settled": True,
            "createdAt": 0,
            "confidence": confidence,
            "rank": "-",
            "firstLane": selection_meta["primaryFirstLane"],
            "evaluationEligible": True,
            "autoSkipped": True,
            "recommended": False,
            "recommendationReason": (
                "自動BUYはOFF。対象日前日までの履歴でModel A予想を固定し、終了後オッズだけで点数/100円単位の掛け金を配分"
            ),
            "strategyId": STRATEGY_ID,
            "virtualStake": virtual_stake,
            "winningStake": winning_stake,
            "virtualPayout": virtual_payout,
            "virtualProfit": virtual_payout - virtual_stake,
            "hit": hit,
            "selection": selection_meta,
            "allocation": stake_meta,
        }
        records.append(record)
        counts[f"points_{len(combinations)}"] += 1
        counts[f"budget_{virtual_stake}"] += 1
        counts["recordsBuilt"] += 1
    return records


def load_existing_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("strategyId") != STRATEGY_ID:
        return []
    return list(payload.get("records", []))


def write_outputs(args, history: PlayerHistory, records: list[dict], target: date, source_commits: dict[str, str], odds_commit: str, counts: Counter):
    window_start = target - timedelta(days=WINDOW_DAYS - 1)
    by_id = {
        record["id"]: record
        for record in records
        if window_start.isoformat() <= record["date"] <= target.isoformat()
    }
    records = sorted(by_id.values(), key=lambda item: (item["date"], item["stadiumNumber"], item["raceNumber"]))
    if any(record.get("strategyId") != STRATEGY_ID for record in records):
        raise ValueError("foreign strategy record")
    if any(not (MIN_POINTS <= len(record.get("combinations", [])) <= MAX_POINTS) for record in records):
        raise ValueError("unexpected pick count")
    if any(not (MIN_BUDGET <= int(record.get("virtualStake", 0)) <= MAX_BUDGET) for record in records):
        raise ValueError("unexpected stake budget")

    stake = sum(int(record["virtualStake"]) for record in records)
    payout = sum(int(record["virtualPayout"]) for record in records)
    hits = sum(bool(record["hit"]) for record in records)
    point_distribution = Counter(len(record["combinations"]) for record in records)
    budget_distribution = Counter(int(record["virtualStake"]) for record in records)
    avg_points = sum(k * v for k, v in point_distribution.items()) / max(len(records), 1)
    avg_stake = stake / max(len(records), 1)

    payload = {
        "schemaVersion": 2,
        "strategyId": STRATEGY_ID,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "throughDate": target.isoformat(),
        "windowStart": window_start.isoformat(),
        "windowDays": WINDOW_DAYS,
        "forecast": {
            "model": "v0.16 Model A",
            "marketInputs": False,
            "historyRule": "strictly through previous calendar day",
        },
        "allocation": {
            "postRaceOddsInputs": True,
            "oddsArchive": ODDS_REPO,
            "oddsCommit": odds_commit,
            "pointsMin": MIN_POINTS,
            "pointsMax": MAX_POINTS,
            "budgetMin": MIN_BUDGET,
            "budgetMax": MAX_BUDGET,
            "stakeStep": STAKE_STEP,
            "method": "2nd/3rd coverage expansion + expected-log/Kelly-like stake allocation",
            "resultUsedForSelection": False,
        },
        "settlement": {
            "basis": "official settled trifecta payout per 100 yen after race",
            "preCloseOddsClaim": False,
            "note": "Retrospective ended-race allocation only; not a realizable pre-close ROI claim.",
        },
        "summary": {
            "races": len(records),
            "hits": hits,
            "stake": stake,
            "payout": payout,
            "profit": payout - stake,
            "roi": (payout * 100.0 / stake) if stake else 0.0,
            "averagePoints": avg_points,
            "averageStake": avg_stake,
            "pointDistribution": {str(k): point_distribution[k] for k in sorted(point_distribution)},
            "budgetDistribution": {str(k): budget_distribution[k] for k in sorted(budget_distribution)},
        },
        "sourceCommits": {**source_commits, "oddsArchive": odds_commit},
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    state_sha, state_bytes = base.encode_state(history.state, args.state_bin)
    summary = {
        "strategyId": STRATEGY_ID,
        "throughDate": target.isoformat(),
        "windowStart": window_start.isoformat(),
        "records": len(records),
        "hits": hits,
        "stake": stake,
        "payout": payout,
        "profit": payout - stake,
        "roi": payload["summary"]["roi"],
        "averagePoints": avg_points,
        "averageStake": avg_stake,
        "pointDistribution": payload["summary"]["pointDistribution"],
        "budgetDistribution": payload["summary"]["budgetDistribution"],
        "historyLastDay": int(history.state["lastDay"]),
        "historyUpdateRaces": int(history.state["updateRaces"]),
        "historyStateBytes": state_bytes,
        "historyStateSha256": state_sha,
        "populationThisRun": dict(counts),
        "forecastMarketInputs": False,
        "postRaceOddsAllocation": True,
        "preCloseOddsClaim": False,
        "automaticBuy": False,
        "resultUsedForSelection": False,
        "oddsArchiveCommit": odds_commit,
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def run(args):
    target = date.fromisoformat(args.through)
    if target < base.START_2026:
        raise ValueError("through date must be in 2026")
    if target > date.today():
        raise ValueError("through date is in the future")

    source_commits = base.resolve_source_commits()
    odds_commit = resolve_odds_commit()
    models = base.load_models()
    counts = Counter()

    if args.rebuild:
        if args.seed_json is None or not args.seed_json.exists():
            raise ValueError("--rebuild requires --seed-json from Q4 final holdout")
        history = PlayerHistory(json.loads(args.seed_json.read_text(encoding="utf-8")))
        if int(history.state["lastDay"]) != date(2025, 12, 31).toordinal():
            raise ValueError("initial seed must be through 2025-12-31")
        existing_records: list[dict] = []
        next_day = base.START_2026
    elif args.state_bin.exists():
        history = PlayerHistory(base.decode_state(args.state_bin))
        state_day = date.fromordinal(int(history.state["lastDay"]))
        existing_records = load_existing_records(args.output)
        if state_day > target:
            write_outputs(args, history, existing_records, target, source_commits, odds_commit, counts)
            return
        next_day = state_day + timedelta(days=1)
    else:
        if args.seed_json is None or not args.seed_json.exists():
            raise ValueError("first run requires --seed-json from Q4 final holdout")
        history = PlayerHistory(json.loads(args.seed_json.read_text(encoding="utf-8")))
        if int(history.state["lastDay"]) != date(2025, 12, 31).toordinal():
            raise ValueError("initial seed must be through 2025-12-31")
        existing_records = []
        next_day = base.START_2026

    window_start = target - timedelta(days=WINDOW_DAYS - 1)
    if next_day < window_start:
        counts.update(base.advance_without_output(history, next_day, window_start - timedelta(days=1), source_commits))
        next_day = window_start

    new_records: list[dict] = []
    if next_day <= target:
        days = [next_day + timedelta(days=i) for i in range((target - next_day).days + 1)]
        cache, population = base.build_chunk(days, source_commits)
        counts.update(population)
        enriched = enrich(cache, history)
        if np.any(enriched["history_through"] >= enriched["day_ordinal"]):
            raise ValueError("same-day/future history leakage detected")
        q = base.probabilities(enriched, models)
        odds_map, odds_counts = load_odds(days, odds_commit)
        counts.update(odds_counts)
        new_records = make_records(enriched, q, odds_map, counts)

    if int(history.state["lastDay"]) != target.toordinal():
        raise ValueError("history did not advance through target")
    write_outputs(
        args,
        history,
        existing_records + new_records,
        target,
        source_commits,
        odds_commit,
        counts,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", required=True)
    parser.add_argument("--seed-json", type=Path)
    parser.add_argument("--state-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--rebuild", action="store_true")
    run(parser.parse_args())
