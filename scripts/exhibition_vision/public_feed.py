"""Ingest publicly downloadable *numeric* pre-race CSV snapshots, not footage.

BoatraceCSV documents an HTTPS CSV interface and an MIT-licensed repository.
This adapter fetches at most four day files per invocation, with no crawling,
video capture, or discovery of private streaming endpoints.  Published times
are independent references; they are never fabricated video-AI measurements.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, time, timedelta
from io import StringIO
import json
import math
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
BASE = "https://boatracecsv.github.io/data/previews"
SOURCES = ("original_exhibition", "tkz", "stt", "sui")
SOURCE_CREDIT = "BoatraceCSV (https://github.com/BoatraceCSV/boatracecsv.github.io, MIT)"
MAX_CSV_BYTES = 2 * 1024 * 1024
MAX_CSV_RACES = 400
METRICS = {
    "一周": "lap_time_s",
    "半周ラップ": "half_lap_time_s",
    "まわり足": "turn_time_s",
    "回り足": "turn_time_s",
    "直線": "straight_time_s",
}


class FeedError(ValueError):
    """A public feed contains content that is unsafe to interpret."""


class _RejectRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        raise FeedError("unexpected redirect from documented public CSV endpoint")


def feed_url(source: str, day: date) -> str:
    if source not in SOURCES:
        raise FeedError("unsupported CSV source")
    if not isinstance(day, date) or isinstance(day, datetime):
        raise FeedError("day must be a date")
    return f"{BASE}/{source}/{day:%Y/%m/%d}.csv"


def fetch_source(source: str, day: date) -> str:
    """Single well-bounded public HTTPS GET, no redirects or site crawling."""
    url = feed_url(source, day)
    req = Request(url, headers={"User-Agent": "BOAT-AI-research/1.0 (public-CSV adapter)", "Accept": "text/csv"})
    try:
        with build_opener(_RejectRedirect()).open(req, timeout=15) as response:
            payload = response.read(MAX_CSV_BYTES + 1)
    except HTTPError as exc:
        if exc.code == 404:
            return ""  # Day file has not been published yet.
        raise
    if len(payload) > MAX_CSV_BYTES:
        raise FeedError(f"{source}: response larger than 2 MiB")
    try:
        return payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FeedError(f"{source}: invalid UTF-8") from exc


def _numeric(value: str | None, *, positive: bool = False) -> float | None:
    if value is None or value.strip() == "":
        return None
    try:
        number = float(value)
    except (ValueError, TypeError) as exc:
        raise FeedError(f"invalid numeric value: {value!r}") from exc
    if not math.isfinite(number) or (positive and number <= 0):
        raise FeedError(f"out-of-range numeric value: {value!r}")
    return number


def _timestamp(value: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise FeedError("invalid source timestamp") from exc
    if result.tzinfo is None or result.utcoffset() is None:
        raise FeedError("source timestamp must have timezone")
    return result.astimezone(JST)


def parse_source(source: str, day: date, raw: str) -> dict[str, dict]:
    """Validate records, retain only day-matching unique race codes."""
    if source not in SOURCES:
        raise FeedError("unsupported source")
    if not raw:
        return {}
    reader = csv.DictReader(StringIO(raw.lstrip("\ufeff")))
    mandatory = {"レースコード", "レース日", "レース場", "レース回", "締切時刻", "取得日時"}
    if reader.fieldnames is None or not mandatory.issubset(set(reader.fieldnames)):
        raise FeedError(f"{source}: missing required CSV headers")
    output = {}
    for row in reader:
        if len(output) >= MAX_CSV_RACES or None in row:
            raise FeedError(f"{source}: malformed or oversized CSV")
        key = row["レースコード"]
        if not re.fullmatch(r"\d{12}", key or ""):
            raise FeedError(f"{source}: invalid race code")
        if (not key.startswith(day.strftime("%Y%m%d")) or row["レース日"] != day.isoformat()
                or not re.fullmatch(r"\d{2}", row["レース場"] or "")
                or not 1 <= int(row["レース場"]) <= 24
                or not re.fullmatch(r"\d{2}R", row["レース回"] or "")
                or not 1 <= int(row["レース回"][:2]) <= 12
                or key != f"{day:%Y%m%d}{row['レース場']}{row['レース回'][:2]}"):
            raise FeedError(f"{source}: inconsistent race identity")
        try:
            clock = time.fromisoformat(row["締切時刻"])
        except (TypeError, ValueError) as exc:
            raise FeedError(f"{source}: invalid deadline") from exc
        row["_deadline"] = datetime.combine(day, clock, JST)
        row["_captured"] = _timestamp(row["取得日時"])
        if key in output:
            raise FeedError(f"{source}: repeated race code")
        output[key] = row
    return output


def _original(row: dict | None, lane: int) -> dict:
    if not row:
        return {}
    result = {}
    count_str = row.get("計測数")
    try:
        count = int(count_str)
    except (ValueError, TypeError) as exc:
        raise FeedError("invalid original measurement count") from exc
    if not 0 <= count <= 3:
        raise FeedError("invalid original measurement count")
    for i in range(1, count + 1):
        label = row.get(f"計測項目{i}", "")
        if label not in METRICS:
            raise FeedError(f"unknown original measurement: {label}")
        key = METRICS[label]
        if key in result:
            raise FeedError("duplicate original measurement")
        result[key] = _numeric(row.get(f"艇{lane}_値{i}"), positive=True)
    return result


def _published_ranks(boats: list[dict], field: str) -> list[int] | None:
    values = [b["original"].get(field) for b in boats]
    if any(value is None for value in values):
        return None
    # Published values carry hundredth-second differences; do not apply the
    # vision prototype's 0.1-index tie tolerance to measured seconds.
    order = sorted(range(6), key=lambda lane: (values[lane], lane))
    ranks = [0] * 6
    for place, index in enumerate(order, 1):
        ranks[index] = ranks[order[place - 2]] if place > 1 and abs(values[index] - values[order[place - 2]]) < 1e-8 else place
    return ranks


def process_day(raw_by_source: dict[str, str], day: date, retrieved_at: datetime) -> list[dict]:
    """Join available pre-race snapshots; fail closed on late or missing data.

    'PRE_CLOSE_OBSERVED' proves this *worker* retrieved the row before close;
    a source timestamp alone cannot make a past fetch prospective evidence.
    """
    if retrieved_at.tzinfo is None or retrieved_at.utcoffset() is None:
        raise FeedError("retrieval timestamp requires timezone")
    retrieved_at = retrieved_at.astimezone(JST)
    parsed = {source: parse_source(source, day, raw_by_source.get(source, "")) for source in SOURCES}
    keys = sorted(set().union(*(set(rows) for rows in parsed.values())))
    records = []
    for key in keys:
        present = {source: parsed[source][key] for source in SOURCES if key in parsed[source]}
        primary = next(iter(present.values()))
        deadline = primary["_deadline"]
        if any(row["_deadline"] != deadline for row in present.values()):
            raise FeedError(f"{key}: inconsistent deadline between sources")
        preclose_sources = {
            source: row for source, row in present.items()
            if row["_captured"] < deadline and row["_captured"] <= retrieved_at + timedelta(minutes=1)
        }
        originals = preclose_sources.get("original_exhibition")
        tkz = preclose_sources.get("tkz")
        stt = preclose_sources.get("stt")
        sui = preclose_sources.get("sui")
        boats = []
        for lane in range(1, 7):
            orig = _original(originals, lane)
            boats.append({
                "lane": lane,
                "name": originals.get(f"艇{lane}_選手名") if originals else None,
                "original": orig,
                "exhibition_time_s": _numeric(tkz.get(f"艇{lane}_展示タイム"), positive=True) if tkz else None,
                "tilt": _numeric(tkz.get(f"艇{lane}_チルト")) if tkz else None,
                "course": int(stt[f"艇{lane}_コース"]) if stt and (stt.get(f"艇{lane}_コース") or "").isdigit() and 1 <= int(stt[f"艇{lane}_コース"]) <= 6 else None,
                "exhibition_st": _numeric(stt.get(f"艇{lane}_スタート展示")) if stt else None,
                "traits": {"deashi": None, "yukiashi": None, "nobiashi": None,
                           "mawariashi": None, "turn_performance": None},
            })
        ranks = {field: _published_ranks(boats, field)
                 for field in ("lap_time_s", "half_lap_time_s", "straight_time_s", "turn_time_s")}
        # A rank is an observed *time rank*, not a video-derived score for an
        # unmeasured motor trait such as 出足, 行き足 or ターン性能.
        for lane, boat in enumerate(boats):
            boat["original_ranks"] = {field: values[lane] if values else None for field, values in ranks.items()}
        status = "PRE_CLOSE_OBSERVED" if retrieved_at < deadline else "ARCHIVE_ONLY"
        records.append({
            "schema_version": 1,
            "source": "boatracecsv_public_preview",
            "source_credit": SOURCE_CREDIT,
            "data_kind": "published_numeric_exhibition_not_video_ai",
            "status": status,
            "race": {"date": day.isoformat(), "venue": int(key[8:10]),
                     "number": int(key[10:12]), "deadline": deadline.isoformat(), "code": key},
            "retrieved_at": retrieved_at.isoformat(),
            "source_captured_at": {source: row["_captured"].isoformat() for source, row in preclose_sources.items()},
            "sources_present": sorted(preclose_sources),
            "sources_missing_or_late": sorted(set(SOURCES) - set(preclose_sources)),
            "weather": ({"wind_speed_mps": _numeric(sui.get("風速(m)")),
                         "wave_height_cm": _numeric(sui.get("波の高さ(cm)"))} if sui else None),
            "forecast_input_allowed": False,
            "purchase_decision_allowed": False,
            "boats": boats,
        })
    return records


def write_records(records: list[dict], output_dir: Path, *, live_only: bool = False) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {"total_races": len(records), "saved": 0, "pre_close_observed": 0, "archive_only": 0,
               "original_measurement_available": 0}
    for record in records:
        if record["status"] == "PRE_CLOSE_OBSERVED":
            summary["pre_close_observed"] += 1
        else:
            summary["archive_only"] += 1
        if "original_exhibition" in record["sources_present"]:
            summary["original_measurement_available"] += 1
        if live_only and record["status"] != "PRE_CLOSE_OBSERVED":
            continue
        race = record["race"]
        path = output_dir / f"{race['date']}_{race['venue']:02d}_{race['number']:02d}.json"
        path.write_text(json.dumps(record, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        summary["saved"] += 1
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--date", help="JST day YYYY-MM-DD (default: today in Japan)")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--live-only", action="store_true", help="write only races observed before cutoff")
    args = parser.parse_args()
    now = datetime.now(JST)
    try:
        day = date.fromisoformat(args.date) if args.date else now.date()
    except ValueError as exc:
        parser.error(str(exc))
    raw = {source: fetch_source(source, day) for source in SOURCES}
    records = process_day(raw, day, now)
    print(json.dumps(write_records(records, args.output_dir, live_only=args.live_only)))


if __name__ == "__main__":
    main()
