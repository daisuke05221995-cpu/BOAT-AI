"""Audit temporary GitHub Actions preview artifacts without using race outcomes.

Download `public-exhibition-preview-*.zip` artifacts from GitHub Actions into a
directory and pass it as --artifact-dir. This tool neither accesses GitHub nor
claims that scheduled polling works. The same race may appear in multiple runs:
the latest *valid, sufficiently early* snapshot wins, independent of its values.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import json
from pathlib import Path
from statistics import median
from zipfile import BadZipFile, ZipFile

from exhibition_vision.features import UnusablePreview, build_features


MIN_LEAD_SECONDS = 120  # Frozen in data/EXHIBITION_PUBLIC_MODEL_B_PROTOCOL_20261030.json
MAX_MEMBER_BYTES = 1024 * 1024
MAX_ARCHIVE_MEMBERS = 500
TIME_FIELDS = ("lap_time_s", "half_lap_time_s", "turn_time_s", "straight_time_s")


class RollupError(ValueError):
    pass


def _date_time(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw)
    except (ValueError, TypeError) as exc:
        raise RollupError("invalid datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RollupError("datetime must include timezone")
    return parsed


def _record(raw: bytes) -> tuple[dict, dict, float]:
    try:
        record = json.loads(raw.decode("utf-8"))
        features = build_features(record)
    except (UnicodeError, ValueError, TypeError, KeyError, UnusablePreview) as exc:
        raise RollupError("invalid or ineligible pre-close preview") from exc
    race = record["race"]
    if (type(race.get("venue")) is not int or not 1 <= race["venue"] <= 24
            or type(race.get("number")) is not int or not 1 <= race["number"] <= 12
            or not isinstance(race.get("date"), str)
            or not isinstance(race.get("code"), str) or len(race["code"]) != 12
            or not race["code"].isdigit()
            or race["code"] != f"{race.get('date', '').replace('-', '')}{race.get('venue', 0):02d}{race.get('number', 0):02d}"):
        raise RollupError("invalid race identity")
    lead_s = (_date_time(race["deadline"]) - _date_time(record["retrieved_at"])).total_seconds()
    return record, features, lead_s


def _members(folder: Path):
    for path in sorted(folder.iterdir()):
        if path.is_file() and path.suffix == ".json":
            if path.stat().st_size > MAX_MEMBER_BYTES:
                raise RollupError(f"oversized JSON: {path.name}")
            yield path.name, path.read_bytes()
        elif path.is_file() and path.suffix == ".zip":
            try:
                with ZipFile(path) as archive:
                    infos = [info for info in archive.infolist() if not info.is_dir()]
                    if len(infos) > MAX_ARCHIVE_MEMBERS:
                        raise RollupError(f"too many files in {path.name}")
                    for info in infos:
                        # Never extract zip paths to disk. Reject unusual entries.
                        if (info.filename != Path(info.filename).name
                                or not info.filename.endswith(".json")
                                or info.file_size > MAX_MEMBER_BYTES):
                            raise RollupError(f"unsafe artifact entry: {path.name}")
                        yield f"{path.name}/{info.filename}", archive.read(info)
            except BadZipFile as exc:
                raise RollupError(f"corrupt artifact: {path.name}") from exc


def rollup(artifact_dir: Path, output_dir: Path, *, min_lead_seconds: int = MIN_LEAD_SECONDS) -> dict:
    if not artifact_dir.is_dir() or min_lead_seconds != MIN_LEAD_SECONDS:
        raise RollupError("input folder missing or protocol lead time changed")

    # A selected race is determined solely by observation time and identity.
    # Never select snapshots based on model score, prediction, result or payout.
    selected: dict[str, tuple[datetime, dict, dict, float]] = {}
    stats = Counter()
    for name, raw in _members(artifact_dir):
        stats["file_entries"] += 1
        try:
            record, features, lead_s = _record(raw)
        except RollupError:
            stats["invalid_or_ineligible"] += 1
            continue
        stats["valid_preclose_entries"] += 1
        if lead_s < min_lead_seconds:
            stats["too_close_to_deadline"] += 1
            continue
        key = record["race"]["code"]
        observed = _date_time(record["retrieved_at"])
        incumbent = selected.get(key)
        if incumbent is None or observed > incumbent[0]:
            selected[key] = (observed, record, features, lead_s)
        elif observed == incumbent[0] and record != incumbent[1]:
            # Identical timestamps carrying different content are unsafe to merge.
            raise RollupError(f"conflicting same-time snapshots for {key} in {name}")

    output_dir.mkdir(parents=True, exist_ok=True)
    dates = Counter()
    venues = Counter()
    full_original = 0
    originals = 0
    lead_values = []
    for key, (_, record, features, lead_s) in sorted(selected.items()):
        dates[record["race"]["date"]] += 1
        venues[f"{record['race']['venue']:02d}"] += 1
        lead_values.append(lead_s)
        present = features["boats"][0]["present"]
        count = sum(bool(present[field]) for field in TIME_FIELDS)
        originals += int(count > 0)
        full_original += int(count >= 2)
        path = output_dir / f"{key}.json"
        path.write_text(json.dumps(features, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    summary = {
        "protocol": "public_exhibition_model_b_prereg_v1",
        "min_lead_seconds": MIN_LEAD_SECONDS,
        "total_file_entries": stats["file_entries"],
        "valid_preclose_entries": stats["valid_preclose_entries"],
        "invalid_or_ineligible": stats["invalid_or_ineligible"],
        "too_close_to_deadline": stats["too_close_to_deadline"],
        "duplicate_observations": max(0, stats["valid_preclose_entries"] - stats["too_close_to_deadline"] - len(selected)),
        "distinct_races": len(selected),
        "distinct_days": len(dates),
        "days": dict(sorted(dates.items())),
        "venues": dict(sorted(venues.items())),
        "races_with_original": originals,
        "races_with_two_or_more_original_items": full_original,
        "median_retrieval_lead_seconds": round(median(lead_values), 1) if lead_values else None,
        "phase_1_readiness": len(selected) >= 360 and len(dates) >= 5,
        "phase_2_sample_count_only": len(selected) >= 1000 and len(dates) >= 14,
        "forecast_input_allowed": False,
        "purchase_decision_allowed": False,
    }
    (output_dir / "rollup-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(rollup(args.artifact_dir, args.output_dir)))


if __name__ == "__main__":
    main()
