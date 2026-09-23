#!/usr/bin/env python3
"""Overlay archived pre-race preview data onto historical BOAT AI feature rows.

BoatraceOpenAPI/previews v3 contains historical pre-race snapshots from 2023-05-01.
Those fields are observable before the race and therefore may be used without result
leakage: exhibition course, exhibition ST, exhibition time, wind and wave.

The historical B/K record builder intentionally produced conservative rows with lane as
course, no preview ST, and zero wind/wave. This module upgrades those rows in-place.
Feature index 7 (historical-learning bonus) is explicitly set to zero for ALL records so
the preview-enhanced research has a feature definition that can be reproduced exactly in
production without relying on a differently reconstructed historical learning state.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Any

PREVIEW_AVAILABLE_FROM = date(2023, 5, 1)
PREVIEW_URL = (
    "https://raw.githubusercontent.com/BoatraceOpenAPI/previews/"
    "gh-pages/docs/v3/{year}/{day}.json"
)
USER_AGENT = "BOAT-AI-Historical-Preview/1.0"

# search_2026_strategy.feature_row positions.
IDX_EXHIBITION = 5
IDX_PREVIEW_START = 6
IDX_LEARNING_BONUS = 7
IDX_COURSE_ONEHOT = 14
IDX_COURSE_CHANGED = 20
IDX_WIND_LANE1 = 21
IDX_WIND_OUTER = 22
IDX_WAVE_LANE1 = 23
IDX_WAVE_OUTER = 24
IDX_MISSING_EXHIBITION = 30
IDX_MISSING_PREVIEW_START = 31
FEATURE_COUNT = 32


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def fetch_preview_day(day: date, attempts: int = 3) -> tuple[date, dict[tuple[int, int], dict[str, Any]], str | None]:
    if day < PREVIEW_AVAILABLE_FROM:
        return day, {}, "before-archive"
    url = PREVIEW_URL.format(year=day.year, day=day.strftime("%Y%m%d"))
    last_error: str | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            races: dict[tuple[int, int], dict[str, Any]] = {}
            for preview in payload.get("previews", []):
                try:
                    venue = int(preview.get("stadium_number"))
                    race_number = int(preview.get("number"))
                except (TypeError, ValueError):
                    continue
                if 1 <= venue <= 24 and 1 <= race_number <= 12:
                    races[(venue, race_number)] = preview
            return day, races, None
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return day, {}, "404"
            last_error = f"HTTP {exc.code}"
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
        time.sleep(0.7 * (attempt + 1))
    return day, {}, last_error or "unknown"


def fetch_preview_range(start: date, end: date, workers: int = 16) -> tuple[dict[date, dict[tuple[int, int], dict[str, Any]]], dict[str, str]]:
    first = max(start, PREVIEW_AVAILABLE_FROM)
    if end < first:
        return {}, {}
    days: list[date] = []
    cursor = first
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    output: dict[date, dict[tuple[int, int], dict[str, Any]]] = {}
    errors: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 16))) as pool:
        futures = {pool.submit(fetch_preview_day, day): day for day in days}
        for future in as_completed(futures):
            day, races, error = future.result()
            if races:
                output[day] = races
            elif error and error not in ("404", "before-archive"):
                errors[day.isoformat()] = error
    return output, errors


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def apply_preview_overlay(
    records: list[dict[str, Any]],
    preview_by_day: dict[date, dict[tuple[int, int], dict[str, Any]]],
) -> dict[str, Any]:
    """Mutate feature rows in place and return coverage diagnostics."""
    matched_races = 0
    eligible_races = 0
    matched_racers = 0
    eligible_racers = 0
    missing_by_month: dict[str, int] = {}

    # Remove the dynamic learning-bonus feature globally for exact historical/live parity.
    for record in records:
        for row in record.get("features", []):
            if len(row) != FEATURE_COUNT:
                raise RuntimeError(f"unexpected feature count: {len(row)}")
            row[IDX_LEARNING_BONUS] = 0.0

    for record in records:
        day = record.get("day")
        if not isinstance(day, date) or day < PREVIEW_AVAILABLE_FROM:
            continue
        eligible_races += 1
        eligible_racers += 6
        venue = int(record["venue"])
        race_number = int(record["raceNumber"])
        preview = preview_by_day.get(day, {}).get((venue, race_number))
        if preview is None:
            key = f"{day.year}-{day.month:02d}"
            missing_by_month[key] = missing_by_month.get(key, 0) + 1
            continue

        boats: dict[int, dict[str, Any]] = {}
        for boat in preview.get("boats", []):
            try:
                lane = int(boat.get("racer_boat_number"))
            except (TypeError, ValueError):
                continue
            if 1 <= lane <= 6:
                boats[lane] = boat
        if len(boats) != 6:
            key = f"{day.year}-{day.month:02d}"
            missing_by_month[key] = missing_by_month.get(key, 0) + 1
            continue

        try:
            wind = float(preview.get("wind_speed") or 0.0)
            wave = float(preview.get("wave_height") or 0.0)
        except (TypeError, ValueError):
            wind = 0.0
            wave = 0.0

        rows = record["features"]
        for lane in range(1, 7):
            row = rows[lane - 1]
            boat = boats[lane]
            try:
                course = int(boat.get("racer_course_number") or lane)
            except (TypeError, ValueError):
                course = lane
            if course not in range(1, 7):
                course = lane
            preview_start = _as_float(boat.get("racer_start_timing"))
            exhibition = _as_float(boat.get("racer_exhibition_time"))

            if exhibition is not None:
                row[IDX_EXHIBITION] = _clamp(exhibition, 6.0, 8.0)
                row[IDX_MISSING_EXHIBITION] = 0.0
            if preview_start is not None:
                row[IDX_PREVIEW_START] = _clamp(preview_start, -0.20, 0.60)
                row[IDX_MISSING_PREVIEW_START] = 0.0

            for idx in range(6):
                row[IDX_COURSE_ONEHOT + idx] = 1.0 if course == idx + 1 else 0.0
            row[IDX_COURSE_CHANGED] = 1.0 if course != lane else 0.0
            row[IDX_WIND_LANE1] = wind if lane == 1 else 0.0
            row[IDX_WIND_OUTER] = wind if lane >= 4 else 0.0
            row[IDX_WAVE_LANE1] = wave if lane == 1 else 0.0
            row[IDX_WAVE_OUTER] = wave if lane >= 4 else 0.0
            matched_racers += 1

        matched_races += 1

    return {
        "archiveAvailableFrom": PREVIEW_AVAILABLE_FROM.isoformat(),
        "eligibleRaces": eligible_races,
        "matchedRaces": matched_races,
        "raceCoverage": round(matched_races * 100.0 / eligible_races, 2) if eligible_races else 0.0,
        "eligibleRacers": eligible_racers,
        "matchedRacers": matched_racers,
        "racerCoverage": round(matched_racers * 100.0 / eligible_racers, 2) if eligible_racers else 0.0,
        "missingRacesByMonth": missing_by_month,
        "featurePolicy": (
            "Archived pre-race exhibition course/ST/time and wind/wave overlay; "
            "historical-learning bonus feature forced to zero for reproducible production parity."
        ),
    }
