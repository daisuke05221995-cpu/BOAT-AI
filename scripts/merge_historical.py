#!/usr/bin/env python3
"""Merge BOAT AI historical-learning partial JSON files into one baseline."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--start", type=parse_date, required=True)
    parser.add_argument("--end", type=parse_date, required=True)
    args = parser.parse_args()

    files = sorted(args.input_dir.glob("historical_learning_*.json"))
    if not files:
        raise SystemExit(f"no partial JSON files found in {args.input_dir}")

    parts = [read_json(path) for path in files]
    parts.sort(key=lambda part: part["trainedFrom"])

    cursor = args.start
    for part in parts:
        if part.get("schemaVersion") != 1:
            raise SystemExit(f"unsupported schemaVersion in {part.get('trainedFrom')}")
        part_start = date.fromisoformat(part["trainedFrom"])
        part_end = date.fromisoformat(part["trainedThrough"])
        if part_start != cursor:
            raise SystemExit(
                f"historical range gap/overlap: expected {cursor}, got {part_start}"
            )
        if part_end < part_start:
            raise SystemExit(f"invalid partial range: {part_start}..{part_end}")
        cursor = part_end + timedelta(days=1)

    if cursor - timedelta(days=1) != args.end:
        raise SystemExit(
            f"historical range ends at {cursor - timedelta(days=1)}, expected {args.end}"
        )

    starts: Counter[str] = Counter()
    wins: Counter[str] = Counter()
    wind_course_starts: Counter[str] = Counter()
    wind_course_wins: Counter[str] = Counter()
    venue_race_counts: Counter[str] = Counter()

    historical_race_count = 0
    downloaded_days = 0
    missing_or_no_race_days = 0

    for part in parts:
        historical_race_count += int(part.get("historicalRaceCount", 0))
        downloaded_days += int(part.get("downloadedDays", 0))
        missing_or_no_race_days += int(part.get("missingOrNoRaceDays", 0))
        starts.update({k: int(v) for k, v in part.get("starts", {}).items()})
        wins.update({k: int(v) for k, v in part.get("wins", {}).items()})
        wind_course_starts.update(
            {k: int(v) for k, v in part.get("windCourseStarts", {}).items()}
        )
        wind_course_wins.update(
            {k: int(v) for k, v in part.get("windCourseWins", {}).items()}
        )
        venue_race_counts.update(
            {k: int(v) for k, v in part.get("venueRaceCounts", {}).items()}
        )

    if historical_race_count < 150_000:
        raise SystemExit(
            f"historical coverage too small: {historical_race_count:,} races "
            "(expected >= 150,000)"
        )
    if len(starts) < 120 or len(wins) < 120:
        raise SystemExit("venue/lane learning map is unexpectedly sparse")
    if len(wind_course_starts) < 200 or len(wind_course_wins) < 200:
        raise SystemExit("wind/course learning map is unexpectedly sparse")

    payload = {
        "schemaVersion": 1,
        "source": "BOAT RACE official performance K files",
        "trainedFrom": args.start.isoformat(),
        "trainedThrough": args.end.isoformat(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "historicalRaceCount": historical_race_count,
        "downloadedDays": downloaded_days,
        "missingOrNoRaceDays": missing_or_no_race_days,
        "starts": dict(sorted(starts.items())),
        "wins": dict(sorted(wins.items())),
        "windCourseStarts": dict(sorted(wind_course_starts.items())),
        "windCourseWins": dict(sorted(wind_course_wins.items())),
        "venueRaceCounts": dict(
            sorted(venue_race_counts.items(), key=lambda item: int(item[0]))
        ),
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "parts": len(parts),
                "historicalRaceCount": historical_race_count,
                "downloadedDays": downloaded_days,
                "missingOrNoRaceDays": missing_or_no_race_days,
                "venueBuckets": len(starts),
                "windCourseBuckets": len(wind_course_starts),
            },
            ensure_ascii=False,
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
