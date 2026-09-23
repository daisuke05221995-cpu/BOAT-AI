#!/usr/bin/env python3
"""Diagnose where BOAT AI adds value relative to archived trifecta market odds.

Uses only cached May-Sep races from 2023-2025. 2025 Oct-Dec is intentionally not
present in the cache and remains reserved as the final holdout.

This script does not search a strategy or unlock release. It reports simple, fixed
subsets so the next strategy is designed from evidence rather than another blind grid.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

BUDGET = 1200
UNITS = 12
MONTHS = (5, 6, 7, 8, 9)
ODDS_BUCKETS = (
    ("lt5", 0.0, 5.0),
    ("5to10", 5.0, 10.0),
    ("10to20", 10.0, 20.0),
    ("20to40", 20.0, 40.0),
    ("40plus", 40.0, float("inf")),
)
RATIO_BUCKETS = (
    ("lt-1", float("-inf"), -1.0),
    ("-1to-0.5", -1.0, -0.5),
    ("-0.5to0", -0.5, 0.0),
    ("0to0.5", 0.0, 0.5),
    ("0.5to1", 0.5, 1.0),
    ("1plus", 1.0, float("inf")),
)


class Cache:
    def __init__(self, path: Path):
        arr = np.load(path)
        self.year = int(arr["year"][0])
        self.month = arr["month"].astype(np.int16)
        self.actual = arr["actual_index"].astype(np.int16)
        self.amount = arr["amount"].astype(np.int64)
        self.model_p = arr["model_p"].astype(np.float64)
        self.market_p = arr["market_p"].astype(np.float64)
        self.odds = arr["odds"].astype(np.float64)

    def operation_mask(self) -> np.ndarray:
        return np.isin(self.month, MONTHS)


def finalize(mask: np.ndarray, picked_index: np.ndarray, cache: Cache) -> dict[str, Any]:
    valid = mask & (picked_index >= 0)
    buys = int(valid.sum())
    if buys == 0:
        return {"buys": 0, "hits": 0, "stake": 0, "payout": 0, "profit": 0, "roi": 0.0, "hitRate": 0.0}
    row = np.arange(len(cache.actual))
    hit = valid & (picked_index == cache.actual)
    hits = int(hit.sum())
    payout = int(np.sum(cache.amount[hit]) * UNITS)
    stake = buys * BUDGET
    return {
        "buys": buys,
        "hits": hits,
        "stake": stake,
        "payout": payout,
        "profit": payout - stake,
        "roi": round(payout * 100.0 / stake, 1),
        "hitRate": round(hits * 100.0 / buys, 2),
    }


def subset_stats(cache: Cache) -> dict[str, Any]:
    operation = cache.operation_mask()
    rows = np.arange(len(cache.actual))

    market_top = np.argmax(cache.market_p, axis=1)
    model_top = np.argmax(cache.model_p, axis=1)
    market_top_odds = cache.odds[rows, market_top]
    market_top_model_p = cache.model_p[rows, market_top]
    market_top_market_p = cache.market_p[rows, market_top]
    model_top_odds = cache.odds[rows, model_top]

    market_valid = operation & (market_top_odds > 0.0)
    model_valid = operation & (model_top_odds > 0.0)
    agreement = market_valid & model_valid & (market_top == model_top)

    market_order = np.argsort(-cache.market_p, axis=1)
    model_order = np.argsort(-cache.model_p, axis=1)
    market_top3 = market_order[:, :3]
    model_top3 = model_order[:, :3]
    model_top_in_market_top3 = model_valid & operation & np.any(market_top3 == model_top[:, None], axis=1)
    market_top_in_model_top3 = market_valid & operation & np.any(model_top3 == market_top[:, None], axis=1)

    top_ratio = np.log(
        np.maximum(market_top_model_p, 1e-12) / np.maximum(market_top_market_p, 1e-12)
    )

    result: dict[str, Any] = {
        "raceCount": int(operation.sum()),
        "marketTop1": finalize(market_valid, market_top, cache),
        "modelTop1": finalize(model_valid, model_top, cache),
        "top1Agreement": finalize(agreement, market_top, cache),
        "modelTopInMarketTop3": finalize(model_top_in_market_top3, model_top, cache),
        "marketTopInModelTop3": finalize(market_top_in_model_top3, market_top, cache),
        "agreementRate": round(int(agreement.sum()) * 100.0 / max(1, int(operation.sum())), 2),
        "marketTopOddsBuckets": {},
        "agreementOddsBuckets": {},
        "marketTopModelMarketLogRatioBuckets": {},
        "monthly": {},
    }

    for name, low, high in ODDS_BUCKETS:
        bucket = market_valid & (market_top_odds >= low) & (market_top_odds < high)
        result["marketTopOddsBuckets"][name] = finalize(bucket, market_top, cache)
        result["agreementOddsBuckets"][name] = finalize(bucket & agreement, market_top, cache)

    for name, low, high in RATIO_BUCKETS:
        bucket = market_valid & (top_ratio >= low) & (top_ratio < high)
        result["marketTopModelMarketLogRatioBuckets"][name] = finalize(bucket, market_top, cache)

    for month in MONTHS:
        month_mask = operation & (cache.month == month)
        result["monthly"][f"{cache.year}-{month:02d}"] = {
            "marketTop1": finalize(month_mask & market_valid, market_top, cache),
            "modelTop1": finalize(month_mask & model_valid, model_top, cache),
            "top1Agreement": finalize(month_mask & agreement, market_top, cache),
        }
    return result


def merge_caches(caches: list[Cache]) -> Cache:
    class Combined:
        pass
    combined = Combined()
    combined.year = 0
    combined.month = np.concatenate([c.month for c in caches])
    combined.actual = np.concatenate([c.actual for c in caches])
    combined.amount = np.concatenate([c.amount for c in caches])
    combined.model_p = np.concatenate([c.model_p for c in caches], axis=0)
    combined.market_p = np.concatenate([c.market_p for c in caches], axis=0)
    combined.odds = np.concatenate([c.odds for c in caches], axis=0)
    combined.operation_mask = lambda: np.isin(combined.month, MONTHS)
    return combined  # type: ignore[return-value]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    caches = [Cache(args.cache_dir / f"signal_cache_{year}.npz") for year in (2023, 2024, 2025)]
    yearly = {str(cache.year): subset_stats(cache) for cache in caches}
    combined_cache = merge_caches(caches)
    combined = subset_stats(combined_cache)

    result = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "period": "May-Sep only for 2023-2025",
        "holdoutExcluded": "2025-10-01..2025-12-31",
        "researchOnly": True,
        "flatStakePerRace": BUDGET,
        "yearly": yearly,
        "combined": combined,
        "notes": [
            "Market top1 is the highest normalized inverse-odds probability (lowest effective trifecta odds).",
            "Agreement means BOAT AI top1 trifecta equals market top1 trifecta.",
            "Each diagnostic bet is one combination at 1200 yen; payout uses official archived trifecta payout.",
            "This diagnostic does not search thresholds and cannot unlock release.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(json.dumps({
        "yearly": {
            year: {
                "marketTop1": stats["marketTop1"],
                "modelTop1": stats["modelTop1"],
                "top1Agreement": stats["top1Agreement"],
                "agreementRate": stats["agreementRate"],
            }
            for year, stats in yearly.items()
        },
        "combined": {
            "marketTop1": combined["marketTop1"],
            "modelTop1": combined["modelTop1"],
            "top1Agreement": combined["top1Agreement"],
            "agreementRate": combined["agreementRate"],
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
