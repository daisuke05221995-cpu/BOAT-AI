#!/usr/bin/env python3
"""Merge official K-file learning parts into a leakage-safe pre-year snapshot.

Unlike merge_historical.py, this supports shorter prefixes used by independent
validation (for example 2021-09-22 through 2022-12-31). It still requires exact
contiguous date coverage and validates that the aggregate is large enough to be a
meaningful baseline.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--start", type=parse_date, required=True)
    parser.add_argument("--end", type=parse_date, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    all_files = sorted(args.input_dir.glob("historical_learning_*.json"))
    if not all_files:
        raise SystemExit(f"no learning parts found in {args.input_dir}")

    parts = []
    for path in all_files:
        part = json.loads(path.read_text(encoding="utf-8"))
        part_start = date.fromisoformat(part["trainedFrom"])
        part_end = date.fromisoformat(part["trainedThrough"])
        if part_end <= args.end:
            parts.append(part)
    parts.sort(key=lambda item: item["trainedFrom"])
    if not parts:
        raise SystemExit("no learning parts are eligible for requested snapshot end")

    cursor = args.start
    for part in parts:
        if int(part.get("schemaVersion", 0)) != 1:
            raise SystemExit("unsupported learning part schema")
        part_start = date.fromisoformat(part["trainedFrom"])
        part_end = date.fromisoformat(part["trainedThrough"])
        if part_start != cursor:
            raise SystemExit(f"learning range gap/overlap: expected {cursor}, got {part_start}")
        if part_end < part_start:
            raise SystemExit(f"invalid learning part {part_start}..{part_end}")
        cursor = part_end + timedelta(days=1)
    actual_end = cursor - timedelta(days=1)
    if actual_end != args.end:
        raise SystemExit(f"learning range ends at {actual_end}, expected {args.end}")

    starts: Counter[str] = Counter()
    wins: Counter[str] = Counter()
    wind_starts: Counter[str] = Counter()
    wind_wins: Counter[str] = Counter()
    venue_counts: Counter[str] = Counter()
    race_count = 0
    downloaded_days = 0
    missing_or_no_race_days = 0

    for part in parts:
        race_count += int(part.get("historicalRaceCount", 0))
        downloaded_days += int(part.get("downloadedDays", 0))
        missing_or_no_race_days += int(part.get("missingOrNoRaceDays", 0))
        starts.update({k: int(v) for k, v in part.get("starts", {}).items()})
        wins.update({k: int(v) for k, v in part.get("wins", {}).items()})
        wind_starts.update({k: int(v) for k, v in part.get("windCourseStarts", {}).items()})
        wind_wins.update({k: int(v) for k, v in part.get("windCourseWins", {}).items()})
        venue_counts.update({k: int(v) for k, v in part.get("venueRaceCounts", {}).items()})

    requested_days = (args.end - args.start).days + 1
    # Roughly 100+ races/day are typical. The lower bound is deliberately loose
    # enough for the short pre-2023 prefix but strict enough to catch broken downloads.
    minimum_races = max(20_000, requested_days * 45)
    if race_count < minimum_races:
        raise SystemExit(f"validation learning coverage too small: {race_count} < {minimum_races}")
    if len(starts) < 120 or len(wins) < 120:
        raise SystemExit("venue/lane learning map is unexpectedly sparse")
    if len(wind_starts) < 180 or len(wind_wins) < 180:
        raise SystemExit("wind/course learning map is unexpectedly sparse")

    payload = {
        "schemaVersion": 1,
        "source": "BOAT RACE official performance K files (validation prefix)",
        "trainedFrom": args.start.isoformat(),
        "trainedThrough": args.end.isoformat(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "historicalRaceCount": race_count,
        "downloadedDays": downloaded_days,
        "missingOrNoRaceDays": missing_or_no_race_days,
        "snapshotComplete": True,
        "knownSourceGap": "Official K-file history may omit venue 23 buckets; neutral priors are used when absent.",
        "starts": dict(sorted(starts.items())),
        "wins": dict(sorted(wins.items())),
        "windCourseStarts": dict(sorted(wind_starts.items())),
        "windCourseWins": dict(sorted(wind_wins.items())),
        "venueRaceCounts": dict(sorted(venue_counts.items(), key=lambda item: int(item[0]))),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "trainedFrom": payload["trainedFrom"],
        "trainedThrough": payload["trainedThrough"],
        "parts": len(parts),
        "historicalRaceCount": race_count,
        "downloadedDays": downloaded_days,
        "missingOrNoRaceDays": missing_or_no_race_days,
        "venueBuckets": len(starts),
        "windCourseBuckets": len(wind_starts),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
