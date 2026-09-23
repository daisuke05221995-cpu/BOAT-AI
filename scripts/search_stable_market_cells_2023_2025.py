#!/usr/bin/env python3
"""Mine simple market/model structural cells that repeat across 2023 and 2024.

Development protocol:
- Fixed, interpretable cells use only first-lane group, AI-vs-market rank relation,
  AI/market probability ratio band and archived odds band.
- Cells are retained only when they have sufficient volume, hit count, month
  stability and non-jackpot-dependent returns in BOTH 2023 and 2024 May-Sep.
- The resulting cell set is frozen before 2025 May-Sep is evaluated.
- One combo per race is bought for 1,200 yen, selected only by the frozen cell
  score and pre-race AI/market ratio.
- 2025 Oct-Dec is never loaded and remains the pristine final holdout.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_multiyear_strategy_v14 as v14
import search_preview_hierarchical_2024_2025 as base

MONTHS = (5, 6, 7, 8, 9)
BUDGET = 1200

RATIO_EDGES = np.asarray([0.0, 0.75, 1.0, 1.25, 1.75, np.inf], dtype=np.float64)
ODDS_EDGES = np.asarray([1.0, 10.0, 20.0, 40.0, 80.0, np.inf], dtype=np.float64)

MIN_CELL_BETS_PER_YEAR = 250
MIN_CELL_HITS_PER_YEAR = 10
MIN_CELL_YEAR_ROI = 95.0
MIN_CELL_COMBINED_ROI = 105.0
MIN_CELL_POSITIVE_MONTHS = 3
MAX_CELL_LARGEST_HIT_SHARE = 25.0

TARGET_MIN_TOTAL_BUYS = 100
TARGET_MIN_MONTH_BUYS = 10
TARGET_MIN_ROI = 105.0
TARGET_MIN_POSITIVE_MONTHS = 4
TARGET_MIN_WORST_ROI = 90.0
TARGET_MAX_LARGEST_HIT_SHARE = 25.0


def rank_matrix(prob: np.ndarray) -> np.ndarray:
    order = np.argsort(-prob, axis=1)
    ranks = np.empty_like(order, dtype=np.int16)
    values = np.broadcast_to(np.arange(1, prob.shape[1] + 1, dtype=np.int16), order.shape)
    np.put_along_axis(ranks, order, values, axis=1)
    return ranks


def first_lane_groups(combos: np.ndarray) -> np.ndarray:
    first = np.asarray([int(str(combo).split('-')[0]) for combo in combos], dtype=np.int8)
    return np.where(first == 1, 0, np.where(first <= 3, 1, 2)).astype(np.int8)


def relation_matrix(model_rank: np.ndarray, market_rank: np.ndarray) -> np.ndarray:
    # 0: both top-10; 1: AI materially ranks higher; 2: market materially ranks higher; 3: other
    both = (model_rank <= 10) & (market_rank <= 10)
    ai_adv = (model_rank <= 20) & ((market_rank - model_rank) >= 5) & ~both
    market_adv = (market_rank <= 20) & ((model_rank - market_rank) >= 5) & ~both
    return np.where(both, 0, np.where(ai_adv, 1, np.where(market_adv, 2, 3))).astype(np.int8)


def feature_cells(cache: v14.Cache) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model = cache.model_p.astype(np.float64)
    market = cache.market_p.astype(np.float64)
    odds = cache.odds.astype(np.float64)
    valid = (model > 0.0) & (market > 0.0) & (odds > 1.0) & (odds <= 80.0)

    model_rank = rank_matrix(model)
    market_rank = rank_matrix(market)
    relation = relation_matrix(model_rank, market_rank)

    ratio = np.zeros_like(model)
    ratio[valid] = model[valid] / market[valid]
    ratio_bin = np.digitize(ratio, RATIO_EDGES[1:-1], right=False).astype(np.int8)
    odds_bin = np.digitize(odds, ODDS_EDGES[1:-1], right=False).astype(np.int8)
    lane_group = first_lane_groups(cache.combos)[None, :]

    # 3 lane groups x 4 rank relations x 5 ratio bins x 5 odds bins = 300 cells.
    cell = (((lane_group * 4 + relation) * 5 + ratio_bin) * 5 + odds_bin).astype(np.int16)
    cell[~valid] = -1
    return cell, ratio, valid


def month_cell_stats(cache: v14.Cache, cells: np.ndarray, month: int) -> dict[int, dict[str, Any]]:
    race_mask = cache.month == month
    c = cells[race_mask]
    actual = cache.actual[race_mask]
    amount = cache.amount[race_mask].astype(np.int64)
    rows = np.arange(len(actual))

    hit = np.zeros_like(c, dtype=bool)
    hit[rows, actual] = True
    out: dict[int, dict[str, Any]] = {}
    for cell_id in np.unique(c[c >= 0]):
        mask = c == int(cell_id)
        count = int(mask.sum())
        hit_rows, hit_cols = np.where(mask & hit)
        payouts = amount[hit_rows] if len(hit_rows) else np.asarray([], dtype=np.int64)
        payout = int(payouts.sum()) if len(payouts) else 0
        largest = int(payouts.max(initial=0)) if len(payouts) else 0
        out[int(cell_id)] = {
            'bets': count,
            'hits': int(len(hit_rows)),
            'payout': payout,
            'roi': round(payout / count, 1) if count else 0.0,
            'largestHitPayout': largest,
        }
    return out


def combine_months(monthly: dict[int, dict[int, dict[str, Any]]], cell_id: int) -> dict[str, Any]:
    rows = [monthly.get(month, {}).get(cell_id, {'bets':0,'hits':0,'payout':0,'roi':0.0,'largestHitPayout':0}) for month in MONTHS]
    bets = sum(int(r['bets']) for r in rows)
    hits = sum(int(r['hits']) for r in rows)
    payout = sum(int(r['payout']) for r in rows)
    largest = max((int(r['largestHitPayout']) for r in rows), default=0)
    positive_months = sum(int(r['bets']) > 0 and float(r['roi']) > 100.0 for r in rows)
    return {
        'bets': bets,
        'hits': hits,
        'payout': payout,
        'roi': round(payout / bets, 1) if bets else 0.0,
        'positiveMonths': positive_months,
        'largestHitPayout': largest,
        'largestHitShare': round(largest * 100.0 / payout, 1) if payout else 0.0,
        'months': {f'{month:02d}': rows[i] for i, month in enumerate(MONTHS)},
    }


def decode_cell(cell_id: int) -> dict[str, Any]:
    value = int(cell_id)
    odds_bin = value % 5; value //= 5
    ratio_bin = value % 5; value //= 5
    relation = value % 4; value //= 4
    lane_group = value
    return {
        'laneGroup': ('1', '2-3', '4-6')[lane_group],
        'rankRelation': ('bothTop10', 'aiAdvantage', 'marketAdvantage', 'other')[relation],
        'ratioLow': None if ratio_bin == 0 else float(RATIO_EDGES[ratio_bin]),
        'ratioHigh': None if ratio_bin == 4 else float(RATIO_EDGES[ratio_bin + 1]),
        'oddsLow': float(ODDS_EDGES[odds_bin]),
        'oddsHigh': None if odds_bin == 4 else float(ODDS_EDGES[odds_bin + 1]),
    }


def strategy_eval(cache: v14.Cache, cells: np.ndarray, ratio: np.ndarray, selected: dict[int, float]) -> tuple[dict[str, Any], dict[str, Any]]:
    monthly: dict[str, Any] = {}
    all_race_payouts: list[int] = []
    total_buys = total_hits = total_payout = 0

    for month in MONTHS:
        race_mask = cache.month == month
        c = cells[race_mask]
        r = ratio[race_mask]
        actual = cache.actual[race_mask]
        amount = cache.amount[race_mask].astype(np.int64)
        rows = np.arange(len(actual))

        score = np.full(c.shape, -np.inf, dtype=np.float64)
        for cell_id, quality in selected.items():
            mask = c == int(cell_id)
            # Cell quality is frozen from 2023/2024; ratio is only a pre-race tie breaker.
            score[mask] = float(quality) + np.log(np.maximum(r[mask], 1e-9)) * 0.01
        best_col = np.argmax(score, axis=1)
        best_score = score[rows, best_col]
        buy = np.isfinite(best_score)
        buys = int(buy.sum())
        hit = buy & (best_col == actual)
        hits = int(hit.sum())
        race_payout = np.where(hit, amount * 12, 0).astype(np.int64)
        payout = int(race_payout.sum())
        largest = int(race_payout.max(initial=0))
        monthly[f'{cache.year}-{month:02d}'] = {
            'purchaseRaces': buys,
            'hits': hits,
            'stake': buys * BUDGET,
            'payout': payout,
            'profit': payout - buys * BUDGET,
            'roi': round(payout * 100.0 / (buys * BUDGET), 1) if buys else 0.0,
            'hitRate': round(hits * 100.0 / buys, 1) if buys else 0.0,
            'largestHitPayout': largest,
        }
        total_buys += buys
        total_hits += hits
        total_payout += payout
        if buys:
            all_race_payouts.extend(race_payout[buy].tolist())

    stake = total_buys * BUDGET
    largest = max(all_race_payouts, default=0)
    total = {
        'purchaseRaces': total_buys,
        'hits': total_hits,
        'stake': stake,
        'payout': total_payout,
        'profit': total_payout - stake,
        'roi': round(total_payout * 100.0 / stake, 1) if stake else 0.0,
        'hitRate': round(total_hits * 100.0 / total_buys, 1) if total_buys else 0.0,
        'largestHitPayout': largest,
        'largestHitShare': round(largest * 100.0 / total_payout, 1) if total_payout else 0.0,
    }
    return monthly, total


def target_metrics(monthly: dict[str, Any], total: dict[str, Any]) -> dict[str, Any]:
    rows = list(monthly.values())
    positive = sum(int(r['purchaseRaces']) > 0 and int(r['profit']) > 0 for r in rows)
    worst = min((float(r['roi']) for r in rows), default=0.0)
    volume_ok = all(int(r['purchaseRaces']) >= TARGET_MIN_MONTH_BUYS for r in rows)
    target = bool(
        int(total['purchaseRaces']) >= TARGET_MIN_TOTAL_BUYS
        and float(total['roi']) >= TARGET_MIN_ROI
        and positive >= TARGET_MIN_POSITIVE_MONTHS
        and worst >= TARGET_MIN_WORST_ROI
        and float(total['largestHitShare']) <= TARGET_MAX_LARGEST_HIT_SHARE
        and volume_ok
    )
    return {'positiveMonths': positive, 'worstMonthRoi': worst, 'volumeOk': volume_ok, 'targetMet': target}


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--cache-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()

    caches={year:base.load_cache(args.cache_dir,year) for year in (2023,2024,2025)}
    feat={year:feature_cells(cache) for year,cache in caches.items()}
    month_stats={}
    year_stats={}
    for year in (2023,2024):
        cells=feat[year][0]
        monthly={m:month_cell_stats(caches[year],cells,m) for m in MONTHS}
        month_stats[year]=monthly
        ids=set()
        for m in MONTHS: ids.update(monthly[m])
        year_stats[year]={cell_id:combine_months(monthly,cell_id) for cell_id in ids}

    common=set(year_stats[2023]) & set(year_stats[2024])
    robust=[]
    selected: dict[int,float]={}
    for cell_id in sorted(common):
        a=year_stats[2023][cell_id]; b=year_stats[2024][cell_id]
        combined_bets=int(a['bets'])+int(b['bets'])
        combined_payout=int(a['payout'])+int(b['payout'])
        combined_roi=round(combined_payout/combined_bets,1) if combined_bets else 0.0
        ok=(
            int(a['bets'])>=MIN_CELL_BETS_PER_YEAR and int(b['bets'])>=MIN_CELL_BETS_PER_YEAR
            and int(a['hits'])>=MIN_CELL_HITS_PER_YEAR and int(b['hits'])>=MIN_CELL_HITS_PER_YEAR
            and float(a['roi'])>=MIN_CELL_YEAR_ROI and float(b['roi'])>=MIN_CELL_YEAR_ROI
            and combined_roi>=MIN_CELL_COMBINED_ROI
            and int(a['positiveMonths'])>=MIN_CELL_POSITIVE_MONTHS and int(b['positiveMonths'])>=MIN_CELL_POSITIVE_MONTHS
            and float(a['largestHitShare'])<=MAX_CELL_LARGEST_HIT_SHARE
            and float(b['largestHitShare'])<=MAX_CELL_LARGEST_HIT_SHARE
        )
        if not ok: continue
        quality=min(float(a['roi']),float(b['roi'])) + 0.25*(combined_roi-100.0)
        selected[int(cell_id)]=quality
        robust.append({
            'cellId':int(cell_id),'cell':decode_cell(cell_id),'quality':round(quality,3),
            '2023':a,'2024':b,'combinedRoi':combined_roi,'combinedBets':combined_bets,
        })

    robust.sort(key=lambda r:(r['quality'],r['combinedBets']),reverse=True)
    m23,t23=strategy_eval(caches[2023],feat[2023][0],feat[2023][1],selected)
    m24,t24=strategy_eval(caches[2024],feat[2024][0],feat[2024][1],selected)
    # Only after the cell set is fully frozen do we evaluate 2025 May-Sep.
    m25,t25=strategy_eval(caches[2025],feat[2025][0],feat[2025][1],selected)
    metrics25=target_metrics(m25,t25)

    result={
        'schemaVersion':20,
        'generatedAt':datetime.now(timezone.utc).isoformat(),
        'researchOnly':True,'releaseQualified':False,
        'method':'fixed structural market/model cells required to repeat in both 2023 and 2024, then frozen one-point evaluation in 2025',
        'cellDefinition':{
            'laneGroups':['1','2-3','4-6'],
            'rankRelations':['bothTop10','aiAdvantage','marketAdvantage','other'],
            'ratioEdges':[0.0,0.75,1.0,1.25,1.75,None],
            'oddsEdges':[1.0,10.0,20.0,40.0,80.0,None],
        },
        'selectionGuards':{
            'minBetsPerYear':MIN_CELL_BETS_PER_YEAR,'minHitsPerYear':MIN_CELL_HITS_PER_YEAR,
            'minYearRoi':MIN_CELL_YEAR_ROI,'minCombinedRoi':MIN_CELL_COMBINED_ROI,
            'minPositiveMonthsPerYear':MIN_CELL_POSITIVE_MONTHS,
            'maxLargestHitShare':MAX_CELL_LARGEST_HIT_SHARE,
        },
        'selectedCellCount':len(robust),'selectedCells':robust,
        'development2023':{'months':m23,'total':t23},
        'development2024':{'months':m24,'total':t24},
        'frozenEvaluation2025':{'months':m25,'total':t25,**metrics25},
        'readyForFinalHoldout':bool(len(robust)>0 and metrics25['targetMet']),
        'holdoutPolicy':{'reserved':'2025-10-01..2025-12-31','opened':False},
        'notes':[
            '2023/2024 are explicit development years used to select cells.',
            '2025 May-Sep is frozen evaluation for this exact cell strategy, but has been inspected by prior strategy families.',
            '2025 Oct-Dec is not loaded and remains the only pristine final holdout.',
        ],
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({
        'selectedCellCount':len(robust),'selectedCells':robust[:10],
        'development2023':t23,'development2024':t24,
        'frozenEvaluation2025':{**t25,**metrics25},
        'readyForFinalHoldout':result['readyForFinalHoldout'],'holdoutOpened':False,
    },ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
