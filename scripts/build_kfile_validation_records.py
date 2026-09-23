#!/usr/bin/env python3
"""Build leakage-safe model records for older-year validation from BOAT RACE B/K files.

The public JSON mirror used for 2026 does not contain 2023-2025 history. This module
reconstructs the model inputs from official BOAT RACE archives instead:

* B (schedule/program) files provide pre-race national/local win rates and motor/boat
  top-2 rates.
* K (performance/result) files provide exhibition time and the settled trifecta.
* average_start is reconstructed only from races settled BEFORE the target day,
  seeded from the pre-year K-file snapshot.

Leakage guard:
* current-race actual start timing and actual entrance position from K files are NOT
  used as prediction features;
* current-race result-time wind/wave are NOT used as prediction features;
* those settled values may update historical learning / racer start history only
  AFTER all records for that day have been created.

This intentionally leaves preview_start missing and uses lane as the pre-race course
proxy for older years. If the strategy survives this more conservative feature set,
that is stronger robustness evidence than reusing post-race fields.
"""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from boatrace_lzh import LzhDownloader, PerformanceParser, ScheduleParser
from boatrace_lzh.constants import VENUE_CODES

import search_2026_strategy as v6
from build_2026_backtest import LearningProfile, normalize_combo

_ENTRY_HEAD_RE = re.compile(r"^\s*([1-6])\s+(\d{4})(.*)$")
_CLASS_RE = re.compile(r"([AB][12])")
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")
_RACE_RE = re.compile(r"^\s*(\d{1,2})R(?:\s|$)")


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _venue_from_line(line: str) -> int | None:
    """Return venue code when a BOAT RACE venue header is present.

    Official B archives may contain multiple venue blocks in one text file. The
    upstream ScheduleParser assigns one header venue to a whole file, so validation
    must track venue headers line-by-line instead of assuming one file == one venue.
    """
    compact = re.sub(r"\s+", "", line)
    if "ボートレース" not in compact:
        return None
    for venue_name, venue_code in sorted(VENUE_CODES.items(), key=lambda item: len(item[0]), reverse=True):
        if f"ボートレース{venue_name}" in compact:
            try:
                value = int(venue_code)
            except (TypeError, ValueError):
                continue
            if 1 <= value <= 24:
                return value
    return None


def _metric_from_line(line: str) -> dict[str, Any] | None:
    """Parse one B-file entry line without relying on historical column spacing."""
    match = _ENTRY_HEAD_RE.match(line)
    if not match:
        return None
    lane = int(match.group(1))
    registration = int(match.group(2))
    remainder = match.group(3)
    class_match = _CLASS_RE.search(remainder)
    if class_match is None:
        return None
    rank = class_match.group(1)
    values = _NUMBER_RE.findall(remainder[class_match.end() :])
    if len(values) < 8:
        return None
    try:
        return {
            "lane": lane,
            "registration": registration,
            "rank": rank,
            "national_win": float(values[0]),
            "national_top2": float(values[1]),
            "local_win": float(values[2]),
            "local_top2": float(values[3]),
            "motor_number": int(float(values[4])),
            "motor_top2": float(values[5]),
            "boat_number": int(float(values[6])),
            "boat_top2": float(values[7]),
        }
    except (TypeError, ValueError):
        return None


def parse_program_metrics(files: dict[str, str], parser: ScheduleParser | None = None) -> dict[tuple[int, int, int], dict[str, Any]]:
    """Extract pre-race numerical features from official B files.

    `parser` is retained for call-site compatibility, but venue assignment is done
    directly from raw headers because a historical B file can contain multiple venues.
    """
    del parser
    output: dict[tuple[int, int, int], dict[str, Any]] = {}
    for _filename, content in files.items():
        if not content or len(content) < 50:
            continue
        current_venue: int | None = None
        current_race: int | None = None
        for raw_line in content.splitlines():
            line = unicodedata.normalize("NFKC", raw_line)
            venue = _venue_from_line(line)
            if venue is not None:
                current_venue = venue
                current_race = None
                continue
            race_match = _RACE_RE.match(line)
            if race_match:
                current_race = int(race_match.group(1))
                continue
            if current_venue is None or current_race is None:
                continue
            metric = _metric_from_line(line)
            if metric is None:
                continue
            lane = int(metric.pop("lane"))
            output[(current_venue, current_race, lane)] = metric
    return output


def _learning_race(
    venue: int,
    combo: str,
    amount: int,
    entries_by_lane: dict[int, Any],
    race_info: Any,
    metrics: dict[tuple[int, int, int], dict[str, Any]],
    race_number: int,
) -> dict[str, Any]:
    wind = int(round(float(race_info.wind_speed))) if race_info is not None and race_info.wind_speed is not None else None
    racers: dict[str, dict[str, Any]] = {}
    preview_racers: dict[str, dict[str, Any]] = {}
    for lane in range(1, 7):
        item = metrics.get((venue, race_number, lane)) or {}
        racers[str(lane)] = {"national_win_rate": item.get("national_win", 0.0)}
        entry = entries_by_lane.get(lane)
        actual_course = int(entry.entrance_position) if entry is not None and entry.entrance_position is not None else lane
        preview_racers[str(lane)] = {"course_number": actual_course}
    return {
        "stadium_number": venue,
        "race_number": race_number,
        "racers": racers,
        "preview": {"wind_speed": wind, "racers": preview_racers},
        "result": {"payouts": {"trifecta": [{"combination": combo, "amount": amount}]}},
    }


def build_records_from_kfiles(
    *,
    year: int,
    learning_json: dict[str, Any],
    workers: int = 12,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Build Jan-Sep model records with no same-race or same-day result leakage."""
    start = date(year, 1, 1)
    end = date(year, 9, 30)
    cache_dir = Path(f".validation-k-cache-{year}")
    downloader = LzhDownloader(
        cache_dir=cache_dir,
        max_workers=max(1, min(workers, 16)),
        request_delay=0.15,
        timeout=45,
    )
    schedule_parser = ScheduleParser()
    performance_parser = PerformanceParser()
    learning = LearningProfile(learning_json)

    start_sum = {str(k): float(v) for k, v in learning_json.get("racerStartTimingSum", {}).items()}
    start_count = {str(k): int(v) for k, v in learning_json.get("racerStartTimingCount", {}).items()}

    records: list[dict[str, Any]] = []
    stats: dict[str, Any] = {
        "requestedDays": (end - start).days + 1,
        "daysWithPerformance": 0,
        "daysWithSchedule": 0,
        "settledRaces": 0,
        "records": 0,
        "programMetricParsedRacers": 0,
        "programMetricMatchedRacers": 0,
        "recordRacers": 0,
        "averageStartAvailable": 0,
        "exhibitionAvailable": 0,
        "scheduleMissingOnPerformanceDay": [],
        "performanceParseErrors": {},
        "scheduleMetricPolicy": "official pre-race B-file national/local/motor/boat rates",
        "previewPolicy": "exhibition time retained; current-race actual course/ST/wind/wave excluded from features",
        "averageStartPolicy": "prior-race K-file ST mean, seeded only through previous Dec 31 and updated after each whole day",
    }

    current = start
    chunk_days = 31
    try:
        while current <= end:
            chunk_end = min(end, current + timedelta(days=chunk_days - 1))
            days: list[date] = []
            cursor = current
            while cursor <= chunk_end:
                days.append(cursor)
                cursor += timedelta(days=1)

            schedule_results = downloader.download_many(days, "schedule", max_workers=max(1, min(workers, 16)))
            performance_results = downloader.download_many(days, "performance", max_workers=max(1, min(workers, 16)))

            for target_day in days:
                schedule_files = schedule_results.get(target_day) or {}
                performance_files = performance_results.get(target_day) or {}
                if not performance_files:
                    continue
                stats["daysWithPerformance"] += 1
                if schedule_files:
                    stats["daysWithSchedule"] += 1
                else:
                    stats["scheduleMissingOnPerformanceDay"].append(target_day.isoformat())

                try:
                    parsed = performance_parser.parse(performance_files)
                except Exception as exc:
                    stats["performanceParseErrors"][target_day.isoformat()] = f"{type(exc).__name__}: {exc}"
                    continue

                program_metrics = parse_program_metrics(schedule_files, schedule_parser)
                stats["programMetricParsedRacers"] += len(program_metrics)

                race_by_key = {
                    (str(race.venue_code), int(race.race_number)): race
                    for race in parsed.races
                    if race.venue_code and race.race_number
                }
                entries_by_key: dict[tuple[str, int], list[Any]] = defaultdict(list)
                for entry in parsed.entries:
                    if entry.venue_code and entry.race_number:
                        entries_by_key[(str(entry.venue_code), int(entry.race_number))].append(entry)
                trifecta_by_key = {
                    (str(payout.venue_code), int(payout.race_number)): payout
                    for payout in parsed.payouts
                    if payout.ticket_type == "sanrensho" and payout.winning_combination and int(payout.payout or 0) > 0
                }

                learning_updates: list[dict[str, Any]] = []
                start_updates: list[tuple[str, float]] = []
                for key, entries in sorted(entries_by_key.items(), key=lambda item: (int(item[0][0]), item[0][1])):
                    payout = trifecta_by_key.get(key)
                    if payout is None:
                        continue
                    combo = normalize_combo(payout.winning_combination)
                    if not combo:
                        continue
                    amount = int(payout.payout or 0)
                    if amount <= 0:
                        continue
                    try:
                        result_lanes = [int(value) for value in combo.split("-")]
                    except ValueError:
                        continue
                    if len(result_lanes) != 3 or any(lane < 1 or lane > 6 for lane in result_lanes):
                        continue
                    try:
                        venue = int(key[0])
                    except ValueError:
                        continue
                    race_number = int(key[1])
                    if not (1 <= venue <= 24 and 1 <= race_number <= 12):
                        continue

                    entries_by_lane = {
                        int(entry.boat_number): entry
                        for entry in entries
                        if entry.boat_number is not None and 1 <= int(entry.boat_number) <= 6
                    }
                    if len(entries_by_lane) != 6:
                        continue

                    features: list[list[float]] = []
                    for lane in range(1, 7):
                        entry = entries_by_lane[lane]
                        metric = program_metrics.get((venue, race_number, lane)) or {}
                        reg = int(entry.racer_number or metric.get("registration") or 0)
                        reg_key = str(reg) if reg > 0 else ""
                        count = int(start_count.get(reg_key, 0)) if reg_key else 0
                        avg_start = (
                            float(start_sum.get(reg_key, 0.0)) / count
                            if reg_key and count >= 3
                            else None
                        )
                        exhibition = _as_float(entry.exhibition_time)
                        racer = {
                            "lane": lane,
                            "average_start": avg_start,
                            "national_win": _as_float(metric.get("national_win")),
                            "local_win": _as_float(metric.get("local_win")),
                            "motor_top2": _as_float(metric.get("motor_top2")),
                            "boat_top2": _as_float(metric.get("boat_top2")),
                            "course": lane,
                            "preview_start": None,
                            "exhibition": exhibition,
                        }
                        features.append(v6.feature_row(racer, venue, 0, 0, learning))
                        stats["recordRacers"] += 1
                        if metric:
                            stats["programMetricMatchedRacers"] += 1
                        if avg_start is not None:
                            stats["averageStartAvailable"] += 1
                        if exhibition is not None:
                            stats["exhibitionAvailable"] += 1

                    records.append({
                        "day": target_day,
                        "venue": venue,
                        "raceNumber": race_number,
                        "features": features,
                        "targets": [lane - 1 for lane in result_lanes],
                        "combo": combo,
                        "amount": amount,
                    })
                    stats["settledRaces"] += 1

                    race_info = race_by_key.get(key)
                    learning_updates.append(
                        _learning_race(venue, combo, amount, entries_by_lane, race_info, program_metrics, race_number)
                    )

                for update in learning_updates:
                    learning.observe_race(update)
                for entry in parsed.entries:
                    reg = int(entry.racer_number or 0)
                    timing = _as_float(entry.st_timing)
                    if reg <= 0 or timing is None or not (-1.0 <= timing <= 1.0):
                        continue
                    start_updates.append((str(reg), timing))
                for reg_key, timing in start_updates:
                    start_sum[reg_key] = float(start_sum.get(reg_key, 0.0)) + timing
                    start_count[reg_key] = int(start_count.get(reg_key, 0)) + 1

            print(
                f"{year}: processed {current.isoformat()}..{chunk_end.isoformat()} records={len(records):,}",
                flush=True,
            )
            current = chunk_end + timedelta(days=1)
    finally:
        shutil.rmtree(cache_dir, ignore_errors=True)

    stats["records"] = len(records)
    racer_rows = max(1, int(stats["recordRacers"]))
    stats["averageStartCoverage"] = round(int(stats["averageStartAvailable"]) * 100.0 / racer_rows, 2)
    stats["exhibitionCoverage"] = round(int(stats["exhibitionAvailable"]) * 100.0 / racer_rows, 2)
    stats["programMetricCoverage"] = round(int(stats["programMetricMatchedRacers"]) * 100.0 / racer_rows, 2)
    stats["programMetricParsedToRecordRatio"] = round(int(stats["programMetricParsedRacers"]) * 100.0 / racer_rows, 2)
    stats["racersWithStartHistoryAfterPeriod"] = len(start_count)

    if len(records) < 15_000:
        raise RuntimeError(f"K-file validation records too sparse for {year}: {len(records)}")
    if float(stats["programMetricCoverage"]) < 90.0:
        raise RuntimeError(f"B-file matched program metric coverage too low: {stats['programMetricCoverage']}%")
    if float(stats["exhibitionCoverage"]) < 90.0:
        raise RuntimeError(f"exhibition coverage too low: {stats['exhibitionCoverage']}%")
    if float(stats["averageStartCoverage"]) < 70.0:
        raise RuntimeError(f"average-start history coverage too low: {stats['averageStartCoverage']}%")
    if stats["performanceParseErrors"]:
        raise RuntimeError(f"K-file parse errors: {json.dumps(stats['performanceParseErrors'], ensure_ascii=False)}")

    return records, stats
