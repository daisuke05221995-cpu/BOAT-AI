#!/usr/bin/env python3
"""Build historical BOAT AI signal cache with archived pre-race preview features.

This is the production-parity successor to build_market_signal_cache.py. It starts from
leakage-safe official B/K records, overlays archived pre-race exhibition course/ST/time
and wind/wave, then refits each monthly conditional model only through the previous month.
The resulting NPZ keeps the same shape as the existing market-signal cache so research
scripts can compare conservative vs preview-enhanced model probabilities directly.
"""
from __future__ import annotations

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_2026_strategy_v9 as v9
from build_kfile_validation_records import build_records_from_kfiles
from build_market_signal_cache import MONTHS, all_combinations, fetch_archived_odds, month_end
from historical_preview_overlay import PREVIEW_AVAILABLE_FROM, apply_preview_overlay, fetch_preview_range


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
        raise SystemExit("preview-enhanced cache currently supports 2023-2025")

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

    preview_by_day, preview_errors = fetch_preview_range(
        date(year, 1, 1),
        date(year, 9, 30),
        args.workers,
    )
    if preview_errors:
        raise SystemExit(f"preview download failures: {preview_errors}")
    preview_source = apply_preview_overlay(records, preview_by_day)
    if year >= 2024 and float(preview_source.get("raceCoverage", 0.0)) < 95.0:
        raise SystemExit(f"preview race coverage too low: {preview_source}")
    if year == 2023 and float(preview_source.get("raceCoverage", 0.0)) < 95.0:
        raise SystemExit(f"2023 May-Sep preview race coverage too low: {preview_source}")

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
        print(f"{key}: preview-enhanced cached={accepted} missing={missing}", flush=True)

    if not model_rows:
        raise SystemExit("no preview-enhanced signals were cached")
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
        "schemaVersion": 2,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "year": year,
        "learningTrainedThrough": learning_json.get("trainedThrough"),
        "recordSource": record_source,
        "previewSource": preview_source,
        "previewArchive": {
            "repository": "BoatraceOpenAPI/previews",
            "availableFrom": PREVIEW_AVAILABLE_FROM.isoformat(),
            "policy": "pre-race v3 snapshot only; result-time K course/ST/wind/wave are not used",
        },
        "signalCounts": month_signal_counts,
        "missingRaces": month_missing,
        "cachedRaces": len(months),
        "comboCount": len(combos),
        "featurePolicy": (
            "B-file program metrics + prior-race average ST + archived pre-race exhibition "
            "course/ST/time and wind/wave; historical-learning bonus input forced to zero."
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
        "previewSource": preview_source,
        "signalCounts": month_signal_counts,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
