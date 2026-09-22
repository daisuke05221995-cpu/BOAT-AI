#!/usr/bin/env python3
"""Build BOAT AI learning aggregates from historical race JSON for a date range.

This mirrors LearningStore.observe semantics and is used only to remove 2026
information from the packaged five-year aggregate before walk-forward backtesting.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import time
import urllib.error
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

API = "https://boatraceopenapi.github.io/api/v1/{year}/{day}.json"
UA = "BOAT-AI-Learning-Derivation/1.0"


def as_int(value: Any, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_combo(value: Any) -> str | None:
    if value is None:
        return None
    nums = re.findall(r"[1-6]", str(value))
    return "-".join(nums[:3]) if len(nums) >= 3 else None


def wind_bucket(wind: int) -> str:
    if wind <= 2:
        return "0-2"
    if wind <= 4:
        return "3-4"
    return "5+"


def fetch_day(day: date, attempts: int = 4) -> tuple[date, dict[str, Any] | None, str | None]:
    url = API.format(year=day.year, day=day.strftime("%Y%m%d"))
    last = None
    for attempt in range(1, attempts + 1):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                return day, json.load(response), None
        except urllib.error.HTTPError as exc:
            last = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last = str(exc)
        time.sleep(attempt * 0.7)
    return day, None, last or "unknown"


def iter_races(root: dict[str, Any]):
    stadiums = (((root.get("programs") or {}).get("stadiums")) or {})
    for venue_key, stadium in stadiums.items():
        if not isinstance(stadium, dict):
            continue
        venue = as_int(venue_key)
        if venue is None or not 1 <= venue <= 24:
            continue
        for race in (stadium.get("races") or {}).values():
            if isinstance(race, dict):
                yield venue, race


def aggregate_day(
    root: dict[str, Any],
    starts: Counter[str],
    wins: Counter[str],
    wind_starts: Counter[str],
    wind_wins: Counter[str],
    venue_counts: Counter[str],
) -> int:
    race_count = 0
    for venue, race in iter_races(root):
        result = race.get("result") or {}
        trifecta = ((result.get("payouts") or {}).get("trifecta") or [])
        if not trifecta or not isinstance(trifecta[0], dict):
            continue
        combo = normalize_combo(trifecta[0].get("combination"))
        winner = as_int(combo.split("-")[0]) if combo else None
        if winner is None or not 1 <= winner <= 6:
            continue

        racers_obj = race.get("racers") or {}
        valid_lanes = [lane for lane in range(1, 7) if isinstance(racers_obj.get(str(lane)) or racers_obj.get(lane), dict)]
        if len(valid_lanes) < 3:
            continue

        race_count += 1
        venue_counts[str(venue)] += 1
        for lane in valid_lanes:
            starts[f"{venue}-{lane}"] += 1
        wins[f"{venue}-{winner}"] += 1

        preview = race.get("preview") or {}
        wind = as_int(preview.get("wind_speed"))
        if wind is None:
            continue
        preview_racers = preview.get("racers") or {}
        bucket = wind_bucket(wind)
        for lane in valid_lanes:
            pr = preview_racers.get(str(lane)) or preview_racers.get(lane) or {}
            course = as_int(pr.get("course_number"), lane)
            if course is not None and 1 <= course <= 6:
                wind_starts[f"{venue}-{bucket}-{course}"] += 1
        winner_preview = preview_racers.get(str(winner)) or preview_racers.get(winner) or {}
        winning_course = as_int(winner_preview.get("course_number"), winner)
        if winning_course is not None and 1 <= winning_course <= 6:
            wind_wins[f"{venue}-{bucket}-{winning_course}"] += 1
    return race_count


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.end < args.start:
        raise SystemExit("end before start")

    days = []
    cursor = args.start
    while cursor <= args.end:
        days.append(cursor)
        cursor += timedelta(days=1)

    payloads: dict[date, dict[str, Any]] = {}
    failures: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(fetch_day, day) for day in days]
        for future in as_completed(futures):
            day, data, error = future.result()
            if data is None:
                failures[day.isoformat()] = error or "unknown"
            else:
                payloads[day] = data

    if failures:
        raise SystemExit("historical JSON missing days: " + json.dumps(failures, ensure_ascii=False))

    starts: Counter[str] = Counter()
    wins: Counter[str] = Counter()
    wind_starts: Counter[str] = Counter()
    wind_wins: Counter[str] = Counter()
    venue_counts: Counter[str] = Counter()
    race_count = 0
    for day in days:
        race_count += aggregate_day(payloads[day], starts, wins, wind_starts, wind_wins, venue_counts)

    if race_count <= 1000:
        raise SystemExit(f"historical contribution too small: {race_count}")
    if len(starts) < 120 or len(wins) < 120:
        raise SystemExit("venue/lane map too sparse")
    if len(wind_starts) < 200 or len(wind_wins) < 200:
        raise SystemExit("wind/course map too sparse")

    payload = {
        "schemaVersion": 1,
        "source": "BOAT AI historical race JSON mirror of BOAT RACE data",
        "trainedFrom": args.start.isoformat(),
        "trainedThrough": args.end.isoformat(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "historicalRaceCount": race_count,
        "downloadedDays": len(days),
        "missingOrNoRaceDays": 0,
        "starts": dict(sorted(starts.items())),
        "wins": dict(sorted(wins.items())),
        "windCourseStarts": dict(sorted(wind_starts.items())),
        "windCourseWins": dict(sorted(wind_wins.items())),
        "venueRaceCounts": dict(sorted(venue_counts.items(), key=lambda x: int(x[0]))),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "from": payload["trainedFrom"],
        "through": payload["trainedThrough"],
        "days": len(days),
        "races": race_count,
        "starts": sum(starts.values()),
        "windCourseStarts": sum(wind_starts.values()),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
