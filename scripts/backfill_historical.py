#!/usr/bin/env python3
"""Build the BOAT AI historical learning baseline from official BOAT RACE K files.

The resulting JSON intentionally stores aggregated learning statistics rather than
hundreds of thousands of raw races. This keeps the Android APK small while giving
PredictionEngine a five-year prior before on-device learning begins.
"""

from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from boatrace_lzh import LzhDownloader, PerformanceParser


def parse_date(value: str) -> date:
    return date.fromisoformat(value)


def wind_bucket(wind_speed: float) -> str:
    if wind_speed <= 2:
        return "0-2"
    if wind_speed <= 4:
        return "3-4"
    return "5+"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=parse_date, required=True)
    parser.add_argument("--end", type=parse_date, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--request-delay", type=float, default=0.25)
    args = parser.parse_args()

    if args.end < args.start:
        raise SystemExit("--end must be on or after --start")

    cache_dir = Path(".historical-lzh-cache")
    downloader = LzhDownloader(
        cache_dir=cache_dir,
        max_workers=max(1, args.workers),
        request_delay=max(0.0, args.request_delay),
        timeout=90,
    )
    performance_parser = PerformanceParser()

    starts: Counter[str] = Counter()
    wins: Counter[str] = Counter()
    wind_course_starts: Counter[str] = Counter()
    wind_course_wins: Counter[str] = Counter()
    venue_race_counts: Counter[str] = Counter()

    historical_race_count = 0
    downloaded_days = 0
    failed_days: list[str] = []
    current = args.start
    chunk_size = 31

    while current <= args.end:
        chunk_end = min(args.end, current + timedelta(days=chunk_size - 1))
        dates = []
        cursor = current
        while cursor <= chunk_end:
            dates.append(cursor)
            cursor += timedelta(days=1)

        results = downloader.download_many(dates, "performance", max_workers=args.workers)
        for target_date in dates:
            files = results.get(target_date) or {}
            if not files:
                # A no-race day can legitimately have no data. Keep it as failed-day
                # metadata only; coverage validation uses race counts, not day count.
                failed_days.append(target_date.isoformat())
                continue

            parsed = performance_parser.parse(files)
            downloaded_days += 1

            race_by_key = {
                (race.venue_code, race.race_number): race
                for race in parsed.races
                if race.venue_code and race.race_number
            }
            entries_by_key: dict[tuple[str, int], list] = {}
            for entry in parsed.entries:
                key = (entry.venue_code, entry.race_number)
                entries_by_key.setdefault(key, []).append(entry)

            for key, entries in entries_by_key.items():
                venue_code, _race_number = key
                try:
                    stadium = int(venue_code)
                except (TypeError, ValueError):
                    continue
                if not 1 <= stadium <= 24:
                    continue

                winner = next((entry for entry in entries if entry.result_position == 1), None)
                if winner is None or not 1 <= winner.boat_number <= 6:
                    continue

                valid_entries = [entry for entry in entries if 1 <= entry.boat_number <= 6]
                if len(valid_entries) < 3:
                    continue

                historical_race_count += 1
                venue_race_counts[str(stadium)] += 1

                for entry in valid_entries:
                    starts[f"{stadium}-{entry.boat_number}"] += 1
                wins[f"{stadium}-{winner.boat_number}"] += 1

                race = race_by_key.get(key)
                wind_speed = race.wind_speed if race is not None else None
                if wind_speed is None:
                    continue

                bucket = wind_bucket(float(wind_speed))
                for entry in valid_entries:
                    course = entry.entrance_position
                    if course is not None and 1 <= course <= 6:
                        wind_course_starts[f"{stadium}-{bucket}-{course}"] += 1

                winning_course = winner.entrance_position
                if winning_course is not None and 1 <= winning_course <= 6:
                    wind_course_wins[f"{stadium}-{bucket}-{winning_course}"] += 1

        print(
            f"processed {current.isoformat()}..{chunk_end.isoformat()} "
            f"races={historical_race_count:,} downloaded_days={downloaded_days}"
        )
        current = chunk_end + timedelta(days=1)

    payload = {
        "schemaVersion": 1,
        "source": "BOAT RACE official performance K files",
        "trainedFrom": args.start.isoformat(),
        "trainedThrough": args.end.isoformat(),
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "historicalRaceCount": historical_race_count,
        "downloadedDays": downloaded_days,
        "missingOrNoRaceDays": len(failed_days),
        "starts": dict(sorted(starts.items())),
        "wins": dict(sorted(wins.items())),
        "windCourseStarts": dict(sorted(wind_course_starts.items())),
        "windCourseWins": dict(sorted(wind_course_wins.items())),
        "venueRaceCounts": dict(sorted(venue_race_counts.items(), key=lambda item: int(item[0]))),
    }

    # Guard against accidentally publishing a partial five-year baseline.
    if historical_race_count < 150_000:
        raise SystemExit(
            f"historical coverage too small: {historical_race_count:,} races (expected >= 150,000)"
        )
    if len(starts) < 120 or len(wins) < 120:
        raise SystemExit("venue/lane learning map is unexpectedly sparse")
    if len(wind_course_starts) < 200 or len(wind_course_wins) < 200:
        raise SystemExit("wind/course learning map is unexpectedly sparse")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=False),
        encoding="utf-8",
    )
    print(
        f"wrote {args.output} with {historical_race_count:,} races; "
        f"starts={sum(starts.values()):,}, wind-course starts={sum(wind_course_starts.values()):,}"
    )

    # The workflow runner is ephemeral, so remove the cache before later steps.
    shutil.rmtree(cache_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
