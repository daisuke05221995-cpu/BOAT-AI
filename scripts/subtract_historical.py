#!/usr/bin/env python3
"""Derive a historical learning snapshot by subtracting a later partial aggregate.

Used to create a 2025-12-31 learning snapshot from the five-year baseline while
keeping the exact BOAT RACE K-file aggregation semantics used by the app.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

MAP_KEYS = ("starts", "wins", "windCourseStarts", "windCourseWins", "venueRaceCounts")


def subtract_map(full: dict[str, int], partial: dict[str, int]) -> dict[str, int]:
    result: dict[str, int] = {}
    for key in set(full) | set(partial):
        value = int(full.get(key, 0)) - int(partial.get(key, 0))
        if value < 0:
            raise SystemExit(f"negative derived count for {key}: {value}")
        if value:
            result[key] = value
    return dict(sorted(result.items()))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", type=Path, required=True)
    parser.add_argument("--subtract", type=Path, required=True)
    parser.add_argument("--through", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    full = json.loads(args.full.read_text(encoding="utf-8"))
    partial = json.loads(args.subtract.read_text(encoding="utf-8"))

    payload = {
        "schemaVersion": 1,
        "source": "BOAT RACE official performance K files; derived by exact aggregate subtraction",
        "trainedFrom": full.get("trainedFrom"),
        "trainedThrough": args.through,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "historicalRaceCount": int(full.get("historicalRaceCount", 0)) - int(partial.get("historicalRaceCount", 0)),
        "downloadedDays": max(0, int(full.get("downloadedDays", 0)) - int(partial.get("downloadedDays", 0))),
        "missingOrNoRaceDays": 0,
    }
    for key in MAP_KEYS:
        payload[key] = subtract_map(full.get(key, {}), partial.get(key, {}))

    if payload["historicalRaceCount"] <= 0:
        raise SystemExit("derived historical learning is empty")
    if len(payload["starts"]) < 120 or len(payload["wins"]) < 120:
        raise SystemExit("derived venue/lane map is unexpectedly sparse")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(
        f"wrote {args.output}: races={payload['historicalRaceCount']:,}, "
        f"through={payload['trainedThrough']}"
    )


if __name__ == "__main__":
    main()
