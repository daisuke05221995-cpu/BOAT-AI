#!/usr/bin/env python3
"""Build reusable BOAT AI model/market signal caches for archived years.

The expensive part of historical research is reconstructing official B/K pre-race
features and re-fitting the monthly conditional model. This script performs that once
per year and stores compact NumPy arrays so later strategy experiments can run without
re-downloading/re-parsing the official archives.

Cache contents per race:
- month
- actual trifecta index and official payout amount
- 120-way BOAT AI model probability
- 120-way normalized market probability from archived odds
- 120-way archived trifecta odds

No future information is introduced: each month model is trained only through the
preceding month, matching the existing historical validator.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_2026_strategy_v9 as v9
from build_kfile_validation_records import build_records_from_kfiles

MONTHS = tuple(range(2, 10))


def month_end(year: int, month: int) -> date:
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - timedelta(days=1)


def all_combinations() -> list[str]:
    return [
        f"{first}-{second}-{third}"
        for first in range(1, 7)
        for second in range(1, 7)
        if second != first
        for third in range(1, 7)
        if third not in (first, second)
    ]


def fetch_archived_odds(year: int, workers: int):
    original = v9.ODDS_URL
    v9.ODDS_URL = (
        f"https://raw.githubusercontent.com/lamrongol/BoatraceOdds/gh-pages/docs/v3/{year}/{{day}}.json"
    )
    try:
        return v9.fetch_odds_range(date(year, 2, 1), date(year, 9, 30), workers)
    finally:
        v9.ODDS_URL = original


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--learning", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=16)
    args = parser.parse_args()

    year = int(args.year)
    if year not in (2023, 2024, 2025):
        raise SystemExit("signal cache currently supports 2023-2025")

    learning_json = json.loads(args.learning.read_text(encoding="utf-8"))
    expected_through = f"{year - 1}-12-31"
    if learning_json.get("trainedThrough") != expected_through:
        raise SystemExit(
            f"learning leakage guard: expected trainedThrough={expected_through}, "
            f"got {learning_json.get('trainedThrough')}"
        )
    if learning_json.get("snapshotComplete") is not True:
        raise SystemExit("learning snapshot is not marked complete")

    records, record_source = build_records_from_kfiles(
        year=year,
        learning_json=learning_json,
        workers=args.workers,
    )
    if float(record_source.get("programMetricCoverage", 0.0)) < 90.0:
        raise SystemExit(f"program metric coverage too low: {record_source}")

    odds_by_day, odds_errors = fetch_archived_odds(year, args.workers)
    if odds_errors:
        raise SystemExit(f"odds download failures: {odds_errors}")

    combos = all_combinations()
    combo_index = {combo: idx for idx, combo in enumerate(combos)}
    months: list[int] = []
    actual_indices: list[int] = []
    amounts: list[int] = []
    model_rows: list[np.ndarray] = []
    market_rows: list[np.ndarray] = []
    odds_rows: list[np.ndarray] = []
    month_signal_counts: dict[str, int] = {}
    month_missing: dict[str, int] = {}

    for month in MONTHS:
        model = v9.v6.fit_conditional_model(
            records,
            date(year, 1, 1),
            month_end(year, month - 1),
        )
        signals, missing = v9.make_signals(
            model,
            records,
            date(year, month, 1),
            month_end(year, month),
            odds_by_day,
        )
        key = f"{year}-{month:02d}"
        accepted = 0
        for signal in signals:
            actual = combo_index.get(str(signal["combo"]))
            if actual is None:
                continue
            model_p = np.zeros(120, dtype=np.float32)
            market_p = np.zeros(120, dtype=np.float32)
            odds = np.zeros(120, dtype=np.float32)
            for combo, mp, mkp, odd in signal["items"]:
                idx = combo_index.get(str(combo))
                if idx is None:
                    continue
                model_p[idx] = float(mp)
                market_p[idx] = float(mkp)
                odds[idx] = float(odd)
            valid = (odds > 0.0) & (market_p > 0.0) & (model_p > 0.0)
            if int(valid.sum()) < 100 or not valid[actual]:
                continue
            months.append(month)
            actual_indices.append(actual)
            amounts.append(int(signal["amount"]))
            model_rows.append(model_p)
            market_rows.append(market_p)
            odds_rows.append(odds)
            accepted += 1
        month_signal_counts[key] = accepted
        month_missing[key] = int(missing)
        print(f"{key}: cached={accepted} missing={missing}", flush=True)

    if not model_rows:
        raise SystemExit("no signals were cached")
    if any(month_signal_counts.get(f"{year}-{month:02d}", 0) < 500 for month in MONTHS):
        raise SystemExit(f"insufficient cached signals: {month_signal_counts}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output,
        year=np.asarray([year], dtype=np.int16),
        combos=np.asarray(combos, dtype="U5"),
        month=np.asarray(months, dtype=np.int8),
        actual_index=np.asarray(actual_indices, dtype=np.int16),
        amount=np.asarray(amounts, dtype=np.int32),
        model_p=np.stack(model_rows).astype(np.float32),
        market_p=np.stack(market_rows).astype(np.float32),
        odds=np.stack(odds_rows).astype(np.float32),
    )

    metadata: dict[str, Any] = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "learningTrainedThrough": learning_json.get("trainedThrough"),
        "recordSource": record_source,
        "signalCounts": month_signal_counts,
        "missingRaces": month_missing,
        "cachedRaces": len(months),
        "comboCount": len(combos),
        "policy": (
            "Each monthly model is trained only through the previous month. Cache stores "
            "pre-race model probabilities, archived market probabilities/odds, and settled outcome."
        ),
    }
    args.metadata.parent.mkdir(parents=True, exist_ok=True)
    args.metadata.write_text(
        json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(json.dumps({
        "year": year,
        "cachedRaces": len(months),
        "signalCounts": month_signal_counts,
        "recordSource": record_source,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
