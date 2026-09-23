#!/usr/bin/env python3
"""Test whether preview-era empirical calibration transfers year-to-year.

Protocol:
- Fit fixed hierarchical market calibration on 2023 Jul-Sep only. By July the
  walk-forward model has already seen May-Jun preview-enhanced training records.
- Select ticket thresholds on 2024 May-Sep development outcomes.
- Freeze both calibration and ticket config and evaluate 2025 May-Sep.
- Never load 2025 Oct-Dec; it remains the final holdout.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import diagnose_v15_hierarchical_edge as hierarchy
import search_multiyear_strategy_v14 as v14
import search_preview_hierarchical_2024_2025 as ticket

CAL_MONTHS = (7, 8, 9)
OPERATION_MONTHS = ticket.OPERATION_MONTHS


def fit_2023(cache: v14.Cache) -> dict[str, Any]:
    mask = np.isin(cache.month, CAL_MONTHS)
    model = cache.model_p[mask]
    market = cache.market_p[mask]
    odds = cache.odds[mask]
    actual = cache.actual[mask]
    valid = (model > 0.0) & (market > 0.0) & (odds > 0.0)
    log_ratio = np.zeros_like(model, dtype=np.float64)
    log_ratio[valid] = np.log(model[valid] / market[valid])
    ratio_bin = np.digitize(log_ratio, hierarchy.LOG_RATIO_EDGES[1:-1], right=False).astype(np.int8)
    odds_bin = np.digitize(odds, hierarchy.ODDS_EDGES[1:-1], right=False).astype(np.int8)
    lane_groups = hierarchy.combo_lane_groups(cache.combos)
    rows = np.arange(len(actual))

    parent = {}
    for g in range(3):
        lane_mask = lane_groups[None, :] == g
        for rb in range(len(hierarchy.LOG_RATIO_EDGES) - 1):
            cell = valid & lane_mask & (ratio_bin == rb)
            expected = float(market[cell].sum())
            hit = (lane_groups[actual] == g) & (ratio_bin[rows, actual] == rb) & valid[rows, actual]
            observed = float(hit.sum())
            lift = (observed + hierarchy.PARENT_PRIOR_EXPECTED) / (expected + hierarchy.PARENT_PRIOR_EXPECTED)
            lift = max(hierarchy.LIFT_MIN, min(hierarchy.LIFT_MAX, lift))
            parent[(g, rb)] = {"observed": observed, "expected": expected, "lift": lift, "candidates": int(cell.sum())}

    cells = {}
    for g in range(3):
        lane_mask = lane_groups[None, :] == g
        for rb in range(len(hierarchy.LOG_RATIO_EDGES) - 1):
            parent_lift = float(parent[(g, rb)]["lift"])
            for ob in range(len(hierarchy.ODDS_EDGES) - 1):
                cell = valid & lane_mask & (ratio_bin == rb) & (odds_bin == ob)
                expected = float(market[cell].sum())
                hit = (
                    (lane_groups[actual] == g)
                    & (ratio_bin[rows, actual] == rb)
                    & (odds_bin[rows, actual] == ob)
                    & valid[rows, actual]
                )
                observed = float(hit.sum())
                lift = (observed + hierarchy.CELL_PRIOR_EXPECTED * parent_lift) / (expected + hierarchy.CELL_PRIOR_EXPECTED)
                lift = max(hierarchy.LIFT_MIN, min(hierarchy.LIFT_MAX, lift))
                cells[(g, rb, ob)] = {"observed": observed, "expected": expected, "lift": lift, "candidates": int(cell.sum())}
    return {"parent": parent, "cells": cells, "sampleRaces": int(mask.sum())}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--cache-dir', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()

    c23 = ticket.load_cache(args.cache_dir, 2023)
    c24 = ticket.load_cache(args.cache_dir, 2024)
    c25 = ticket.load_cache(args.cache_dir, 2025)
    fitted = fit_2023(c23)
    prep24 = {m: ticket.prepare_month(c24, m, fitted) for m in OPERATION_MONTHS}
    prep25 = {m: ticket.prepare_month(c25, m, fitted) for m in OPERATION_MONTHS}

    rows = []
    qualified = []
    for cfg in ticket.config_grid():
        monthly, total = ticket.evaluate_year(prep24, cfg)
        min_month = min(int(r['purchaseRaces']) for r in monthly.values())
        row = {
            'config': cfg,
            'minMonthBuys': min_month,
            'positiveMonths': sum(ticket.positive(r) for r in monthly.values()),
            'worstMonthRoi': min(float(r['roi']) for r in monthly.values()),
            'total': total,
            'months': monthly,
        }
        rows.append(row)
        if int(total['purchaseRaces']) >= ticket.DESIGN_MIN_TOTAL_BUYS and min_month >= ticket.DESIGN_MIN_MONTH_BUYS:
            qualified.append((ticket.design_score(monthly, total), cfg, monthly, total))

    rows.sort(key=lambda r: (r['minMonthBuys'], r['total']['purchaseRaces'], r['positiveMonths'], r['worstMonthRoi'], r['total']['roi']), reverse=True)
    result: dict[str, Any] = {
        'schemaVersion': 19,
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'researchOnly': True,
        'releaseQualified': False,
        'method': '2023 Jul-Sep preview calibration transferred unchanged to 2024 design and 2025 frozen evaluation',
        'calibration': {
            'period': '2023-07-01..2023-09-30',
            'sampleRaces': fitted['sampleRaces'],
            'binsChanged': False,
            'parentPriorExpected': hierarchy.PARENT_PRIOR_EXPECTED,
            'cellPriorExpected': hierarchy.CELL_PRIOR_EXPECTED,
            'liftCap': [hierarchy.LIFT_MIN, hierarchy.LIFT_MAX],
        },
        'basicVolumeFeasible': bool(qualified),
        'bestByVolume': rows[:10],
        'holdoutPolicy': {'reserved': '2025-10-01..2025-12-31', 'opened': False},
    }

    if qualified:
        qualified.sort(key=lambda x: x[0], reverse=True)
        score, cfg, m24, t24 = qualified[0]
        metrics24 = ticket.robustness(m24, t24)
        m25, t25 = ticket.evaluate_year(prep25, cfg)
        metrics25 = ticket.robustness(m25, t25)
        result.update({
            'selectedTicketConfig': cfg,
            'design2024': {
                'period': '2024-05-01..2024-09-30',
                'score': list(score),
                'months': {f'2024-{m:02d}': m24[m] for m in OPERATION_MONTHS},
                'total': t24,
                **metrics24,
            },
            'frozenEvaluation2025': {
                'period': '2025-05-01..2025-09-30',
                'months': {f'2025-{m:02d}': m25[m] for m in OPERATION_MONTHS},
                'total': t25,
                **metrics25,
            },
            'readyForFinalHoldout': bool(metrics24['targetMet'] and metrics25['targetMet']),
        })
    else:
        result['readyForFinalHoldout'] = False

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    print(json.dumps({
        'calibrationSampleRaces': fitted['sampleRaces'],
        'basicVolumeFeasible': result['basicVolumeFeasible'],
        'bestByVolume': result['bestByVolume'][:3],
        'selected': result.get('selectedTicketConfig'),
        'design2024': result.get('design2024'),
        'frozen2025': result.get('frozenEvaluation2025'),
        'readyForFinalHoldout': result['readyForFinalHoldout'],
        'holdoutOpened': False,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
