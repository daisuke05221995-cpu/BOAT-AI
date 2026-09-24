#!/usr/bin/env python3
"""Build a rolling 30-day, leak-safe retrospective Model A virtual P/L feed.

Predictions are generated from the frozen market-free Model A using player history
strictly through the previous calendar day. Only after prediction features are
snapshotted are that day's settled results committed to history. Settlement P/L
uses the official result feed's trifecta payout (yen per 100-yen ticket). This is
retrospective forecast evaluation, not a realizable pre-close odds backtest.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from v016_r4_features import COMBOS, COMBO_TEXT, extract_pre
from v016_r4_model import inputs, calibrated
from v016_r2_model import predict
from v016_r4_player_history import PlayerHistory, enrich

ROOT = Path(__file__).resolve().parents[1]
START_2026 = date(2026, 1, 1)
WINDOW_DAYS = 30
POINTS = 4
STAKE_PER_PICK = 300
STRATEGY_ID = "model-a-retro-final-v1"
SOURCE_REPOS = {
    "programs": "boatraceopenapi/programs",
    "previews": "boatraceopenapi/previews",
    "results": "boatraceopenapi/results",
}
MODEL_PATHS = [ROOT / f"app/src/main/assets/model_a_stage{i}.txt" for i in range(3)]
MAGIC = b"BAH1"
VERSION = 1


def request_bytes(url: str, agent: str = "BOAT-AI-v016-recent-virtual") -> bytes:
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": agent})
            with urllib.request.urlopen(req, timeout=60) as response:
                return response.read()
        except Exception as exc:  # pragma: no cover - network retry
            last = exc
            if attempt == 3:
                raise
            time.sleep(attempt + 1)
    raise last  # type: ignore[misc]


def resolve_source_commits() -> dict[str, str]:
    commits = {}
    for kind, repo in SOURCE_REPOS.items():
        raw = request_bytes(f"https://api.github.com/repos/{repo}/commits/gh-pages")
        commits[kind] = json.loads(raw)["sha"]
    return commits


def normalize(kind: str, row: dict) -> dict:
    common = {
        "date": row.get("race_date"),
        "stadium_number": row.get("race_stadium_number"),
        "number": row.get("race_number"),
    }
    if kind == "programs":
        out = dict(row)
        out.update(common)
        return out
    if kind == "previews":
        boats = row.get("boats", {})
        if isinstance(boats, dict):
            boats = list(boats.values())
        out = dict(row)
        out.update(common)
        out.update(
            {
                "boats": boats,
                "wind_speed": row.get("race_wind"),
                "wind_direction_number": row.get("race_wind_direction_number"),
                "wave_height": row.get("race_wave"),
                "air_temperature": row.get("race_temperature"),
                "water_temperature": row.get("race_water_temperature"),
            }
        )
        return out
    if kind == "results":
        out = dict(row)
        out.update(common)
        return out
    raise ValueError(f"unknown source kind {kind}")


def read_day(day: date, commits: dict[str, str]) -> dict[str, dict]:
    if day < START_2026:
        raise ValueError("Recent virtual source fence requires 2026 data")
    out: dict[str, dict] = {}
    for kind, repo in SOURCE_REPOS.items():
        sha = commits[kind]
        url = f"https://raw.githubusercontent.com/{repo}/{sha}/docs/v2/2026/{day:%Y%m%d}.json"
        raw = request_bytes(url)
        records = json.loads(raw)[kind]
        keyed = {}
        for original in records:
            row = normalize(kind, original)
            if row.get("date") != day.isoformat():
                raise ValueError(f"source date mismatch {kind} {day}")
            key = (int(row["stadium_number"]), int(row["number"]))
            if key in keyed:
                raise ValueError(f"duplicate race {day} {kind} {key}")
            keyed[key] = row
        out[kind] = keyed
    missing_results = set(out["programs"]) - set(out["results"])
    if missing_results:
        raise ValueError(f"results not complete for {day}: {len(missing_results)} program races lack result rows")
    return out


def result_info(program: dict, result: dict | None):
    if not result:
        return None
    pb = {b["racer_boat_number"]: b for b in program.get("boats", [])}
    rb = {b["racer_boat_number"]: b for b in result.get("boats", [])}
    if len(pb) != 6 or len(rb) != 6 or set(pb) != set(range(1, 7)) or set(rb) != set(pb):
        return None
    places = [rb[i].get("racer_place_number") for i in range(1, 7)]
    if set(places) != set(range(1, 7)):
        return None
    if any(rb[i].get("racer_number") != pb[i].get("racer_number") for i in range(1, 7)):
        raise ValueError("settled racer ID mismatch")
    order = tuple(places.index(place) for place in (1, 2, 3))
    ix = np.flatnonzero(np.all(COMBOS == order, axis=1))
    if len(ix) != 1:
        return None
    combo = COMBO_TEXT[int(ix[0])]
    trifecta = result.get("payouts", {}).get("trifecta", []) or []
    matched = [item for item in trifecta if item.get("combination") == combo]
    if len(matched) != 1:
        return None
    payout = int(matched[0].get("payout") or 0)
    if payout <= 0:
        return None
    return int(ix[0]), combo, payout


def build_chunk(days: list[date], commits: dict[str, str]):
    rows = []
    counts = Counter()
    with ThreadPoolExecutor(max_workers=12) as pool:
        tasks = {pool.submit(read_day, day, commits): day for day in days}
        for task in as_completed(tasks):
            day = tasks[task]
            src = task.result()
            counts["sourceRaces"] += len(src["programs"])
            for venue, race_number in sorted(src["programs"]):
                program = src["programs"][venue, race_number]
                info = result_info(program, src["results"].get((venue, race_number)))
                if info is None:
                    counts["skippedUnsettledOrNonUnique"] += 1
                    continue
                label, combo, payout = info
                counts["eligibleSettled"] += 1
                try:
                    preview = src["previews"].get((venue, race_number))
                    if preview is not None and not isinstance(preview.get("boats", []), list):
                        raise TypeError("preview boats is not a list")
                    current, global_features, ids, classes, usable = extract_pre(
                        program, preview, day, venue, race_number
                    )
                except (TypeError, KeyError, IndexError, ValueError):
                    counts["malformedPreRaceInput"] += 1
                    continue
                if not usable:
                    counts["missingRequiredInput"] += 1
                rows.append(
                    (
                        day.toordinal(),
                        day.month,
                        venue,
                        race_number,
                        label,
                        current,
                        global_features,
                        ids,
                        classes,
                        usable,
                        combo,
                        payout,
                    )
                )
    rows.sort(key=lambda row: (row[0], row[2], row[3]))
    names = (
        "day_ordinal",
        "month",
        "venue",
        "race_number",
        "actual_index",
        "current",
        "global_features",
        "racer_id",
        "racer_class",
        "usable",
        "result_combination",
        "trifecta_payout",
    )
    cache = {name: np.asarray([row[i] for row in rows]) for i, name in enumerate(names)}
    cache["year"] = np.asarray([2026])
    cache["combos"] = COMBO_TEXT
    return cache, dict(counts)


def load_models():
    import lightgbm as lgb

    models = {}
    for stage, path in enumerate(MODEL_PATHS):
        if not path.exists():
            raise FileNotFoundError(path)
        models[stage] = lgb.Booster(model_file=str(path))
    return models


def probabilities(enriched: dict, models: dict):
    q = calibrated(predict(inputs(enriched, "reaction"), "fundamental", models), 1.0)
    if q.shape != (len(enriched["month"]), 120):
        raise ValueError(f"unexpected Model A shape {q.shape}")
    if not np.isfinite(q).all() or np.any(q < 0) or not np.allclose(q.sum(axis=1), 1.0, atol=1e-5):
        raise ValueError("invalid Model A probabilities")
    return q


def make_records(enriched: dict, q: np.ndarray) -> list[dict]:
    records = []
    for i in range(len(enriched["month"])):
        if not bool(enriched["usable"][i]):
            continue
        day = date.fromordinal(int(enriched["day_ordinal"][i]))
        venue = int(enriched["venue"][i])
        race_number = int(enriched["race_number"][i])
        ranking = np.lexsort((np.arange(120), -q[i]))[:POINTS]
        combinations = [str(COMBO_TEXT[int(ix)]) for ix in ranking]
        probs = [float(q[i, int(ix)]) for ix in ranking]
        result_combo = str(enriched["result_combination"][i])
        payout = int(enriched["trifecta_payout"][i])
        hit = result_combo in combinations
        virtual_stake = POINTS * STAKE_PER_PICK
        virtual_payout = payout * STAKE_PER_PICK // 100 if hit else 0
        records.append(
            {
                "id": f"{day.isoformat()}-{venue:02d}-{race_number}",
                "date": day.isoformat(),
                "stadiumNumber": venue,
                "raceNumber": race_number,
                "combinations": combinations,
                "probabilities": probs,
                "stakes": [STAKE_PER_PICK] * POINTS,
                "stakePerPick": STAKE_PER_PICK,
                "resultCombination": result_combo,
                "trifectaPayout": payout,
                "settlementMultiplier": payout / 100.0,
                "settled": True,
                "createdAt": 0,
                "confidence": 0,
                "rank": "-",
                "firstLane": int(combinations[0].split("-")[0]),
                "evaluationEligible": True,
                "autoSkipped": True,
                "recommended": False,
                "recommendationReason": "自動BUYはOFF。対象日前日までの履歴だけで再現したModel A上位4点を、終了後の確定払戻で仮想精算",
                "strategyId": STRATEGY_ID,
                "virtualStake": virtual_stake,
                "virtualPayout": virtual_payout,
                "virtualProfit": virtual_payout - virtual_stake,
                "hit": hit,
            }
        )
    return records


def read_uvarint(data: memoryview, offset: int):
    result = 0
    shift = 0
    while shift < 35:
        byte = int(data[offset])
        offset += 1
        result |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            return result, offset
        shift += 7
    raise ValueError("malformed unsigned varint")


def read_string(data: memoryview, offset: int):
    length, offset = read_uvarint(data, offset)
    raw = bytes(data[offset : offset + length])
    return raw.decode("utf-8"), offset + length


def decode_state(path: Path) -> dict:
    raw = memoryview(path.read_bytes())
    offset = 0
    if bytes(raw[:4]) != MAGIC:
        raise ValueError("invalid history magic")
    offset = 4
    version, last_day, update_races, stat_count = struct.unpack_from(">iiii", raw, offset)
    offset += 16
    if version != VERSION:
        raise ValueError("unsupported history version")
    stats = {}
    for _ in range(stat_count):
        key, offset = read_string(raw, offset)
        values = list(struct.unpack_from(">8d", raw, offset))
        offset += 64
        stats[key] = values
    (player_count,) = struct.unpack_from(">i", raw, offset)
    offset += 4
    recent = {}
    for _ in range(player_count):
        player, offset = read_string(raw, offset)
        count, offset = read_uvarint(raw, offset)
        days = []
        cumulative = [[0, 0, 0]]
        day_value = 0
        counts = [0, 0, 0]
        for _ in range(count):
            delta_day, offset = read_uvarint(raw, offset)
            day_value += delta_day
            packed = int(raw[offset])
            offset += 1
            delta = [packed & 1, (packed >> 1) & 1, (packed >> 2) & 1]
            counts = [counts[i] + delta[i] for i in range(3)]
            days.append(day_value)
            cumulative.append(list(counts))
        recent[player] = {"days": days, "cumulative": cumulative}
    if offset != len(raw):
        raise ValueError("trailing history bytes")
    return {"stats": stats, "recent": recent, "lastDay": last_day, "updateRaces": update_races}


def uvarint(value: int) -> bytes:
    if value < 0:
        raise ValueError("negative varint")
    out = bytearray()
    while value & ~0x7F:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def write_string(value: str) -> bytes:
    raw = value.encode("utf-8")
    return uvarint(len(raw)) + raw


def encode_state(state: dict, path: Path):
    out = bytearray(MAGIC)
    out += struct.pack(">i", VERSION)
    out += struct.pack(">i", int(state["lastDay"]))
    out += struct.pack(">i", int(state["updateRaces"]))
    stats = state["stats"]
    out += struct.pack(">i", len(stats))
    for key in sorted(stats):
        values = stats[key]
        if len(values) != 8:
            raise ValueError("history stats width")
        out += write_string(key)
        for value in values:
            out += struct.pack(">d", float(value))
    recent = state["recent"]
    out += struct.pack(">i", len(recent))
    for player in sorted(recent):
        record = recent[player]
        days = record["days"]
        cumulative = record["cumulative"]
        if len(cumulative) != len(days) + 1:
            raise ValueError("history cumulative length")
        out += write_string(player)
        out += uvarint(len(days))
        previous_day = 0
        previous = [0, 0, 0]
        for index, day_value in enumerate(days):
            day_value = int(day_value)
            out += uvarint(day_value - previous_day)
            previous_day = day_value
            current = [int(x) for x in cumulative[index + 1]]
            delta = [current[i] - previous[i] for i in range(3)]
            if not all(x in (0, 1) for x in delta) or not (delta[0] <= delta[1] <= delta[2]):
                raise ValueError("invalid history finish delta")
            out.append(delta[0] | (delta[1] << 1) | (delta[2] << 2))
            previous = current
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out)
    return hashlib.sha256(out).hexdigest(), len(out)


def month_end(day: date) -> date:
    if day.month == 12:
        return date(day.year + 1, 1, 1) - timedelta(days=1)
    return date(day.year, day.month + 1, 1) - timedelta(days=1)


def advance_without_output(history: PlayerHistory, start: date, end: date, commits: dict[str, str]):
    day = start
    counts = Counter()
    while day <= end:
        chunk_end = min(month_end(day), end)
        days = [day + timedelta(days=i) for i in range((chunk_end - day).days + 1)]
        cache, population = build_chunk(days, commits)
        if len(cache["month"]) == 0:
            raise ValueError(f"no eligible races in {day:%Y-%m}")
        enrich(cache, history)
        counts.update(population)
        print(f"history warmup through {chunk_end}: races={history.state['updateRaces']}", flush=True)
        day = chunk_end + timedelta(days=1)
    return counts


def load_existing_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("strategyId") != STRATEGY_ID:
        raise ValueError("recent virtual strategy ID mismatch")
    return list(payload.get("records", []))


def write_outputs(args, history: PlayerHistory, records: list[dict], target: date, commits: dict[str, str], population: Counter):
    window_start = target - timedelta(days=WINDOW_DAYS - 1)
    by_id = {record["id"]: record for record in records if window_start.isoformat() <= record["date"] <= target.isoformat()}
    records = sorted(by_id.values(), key=lambda item: (item["date"], item["stadiumNumber"], item["raceNumber"]))
    if any(record["strategyId"] != STRATEGY_ID for record in records):
        raise ValueError("foreign strategy record")
    if any(len(record["combinations"]) != POINTS for record in records):
        raise ValueError("unexpected pick count")
    stake = sum(int(record["virtualStake"]) for record in records)
    payout = sum(int(record["virtualPayout"]) for record in records)
    hits = sum(bool(record["hit"]) for record in records)
    payload = {
        "schemaVersion": 1,
        "strategyId": STRATEGY_ID,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "throughDate": target.isoformat(),
        "windowStart": window_start.isoformat(),
        "windowDays": WINDOW_DAYS,
        "forecast": {
            "model": "v0.16 Model A",
            "marketInputs": False,
            "points": POINTS,
            "stakePerPick": STAKE_PER_PICK,
            "stakePerRace": POINTS * STAKE_PER_PICK,
            "historyRule": "strictly through previous calendar day",
        },
        "settlement": {
            "basis": "official settled trifecta payout per 100 yen after race",
            "preCloseOddsClaim": False,
            "note": "Retrospective virtual P/L only; not a realizable pre-close ROI claim.",
        },
        "summary": {
            "races": len(records),
            "hits": hits,
            "stake": stake,
            "payout": payout,
            "profit": payout - stake,
            "roi": (payout * 100.0 / stake) if stake else 0.0,
        },
        "sourceCommits": commits,
        "records": records,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    state_sha, state_bytes = encode_state(history.state, args.state_bin)
    summary = {
        "throughDate": target.isoformat(),
        "windowStart": window_start.isoformat(),
        "records": len(records),
        "hits": hits,
        "stake": stake,
        "payout": payout,
        "profit": payout - stake,
        "roi": payload["summary"]["roi"],
        "historyLastDay": int(history.state["lastDay"]),
        "historyUpdateRaces": int(history.state["updateRaces"]),
        "historyStateBytes": state_bytes,
        "historyStateSha256": state_sha,
        "populationThisRun": dict(population),
        "marketInputs": False,
        "preCloseOddsClaim": False,
        "automaticBuy": False,
    }
    args.summary.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))


def run(args):
    target = date.fromisoformat(args.through)
    if target < START_2026:
        raise ValueError("through date must be in 2026")
    yesterday_utc_guard = date.today()  # workflow supplies JST yesterday; only blocks obviously future dates
    if target > yesterday_utc_guard:
        raise ValueError("through date is in the future")
    commits = resolve_source_commits()
    models = load_models()
    existing_records = load_existing_records(args.output)
    total_population = Counter()

    if args.state_bin.exists():
        history = PlayerHistory(decode_state(args.state_bin))
        state_day = date.fromordinal(int(history.state["lastDay"]))
        if state_day > target:
            write_outputs(args, history, existing_records, target, commits, total_population)
            return
        next_day = state_day + timedelta(days=1)
    else:
        if args.seed_json is None or not args.seed_json.exists():
            raise ValueError("first run requires --seed-json from Q4 final holdout")
        history = PlayerHistory(json.loads(args.seed_json.read_text(encoding="utf-8")))
        if int(history.state["lastDay"]) != date(2025, 12, 31).toordinal():
            raise ValueError("initial seed must be through 2025-12-31")
        next_day = START_2026

    window_start = target - timedelta(days=WINDOW_DAYS - 1)
    if next_day < window_start:
        warm_end = window_start - timedelta(days=1)
        total_population.update(advance_without_output(history, next_day, warm_end, commits))
        next_day = window_start

    new_records = []
    if next_day <= target:
        days = [next_day + timedelta(days=i) for i in range((target - next_day).days + 1)]
        cache, population = build_chunk(days, commits)
        total_population.update(population)
        enriched = enrich(cache, history)
        if np.any(enriched["history_through"] >= enriched["day_ordinal"]):
            raise ValueError("same-day/future history leakage detected")
        q = probabilities(enriched, models)
        new_records = make_records(enriched, q)
    if int(history.state["lastDay"]) != target.toordinal():
        raise ValueError("history did not advance through target")
    write_outputs(args, history, existing_records + new_records, target, commits, total_population)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--through", required=True)
    parser.add_argument("--seed-json", type=Path)
    parser.add_argument("--state-bin", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    run(parser.parse_args())
