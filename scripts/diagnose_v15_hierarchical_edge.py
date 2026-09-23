#!/usr/bin/env python3
"""Diagnose whether hierarchical model-vs-market calibration yields actionable edges.

Leakage policy:
- ONLY 2023 Feb-Apr outcomes fit calibration.
- 2023 May-Sep outcomes are not read by the feasibility calculation; only pre-race
  model probabilities, market probabilities and odds are used to count candidate volume.
- 2024/2025 and reserved 2025-Q4 are never loaded.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_multiyear_strategy_v14 as v14

CAL_MONTHS = (2, 3, 4)
TEST_MONTHS = (5, 6, 7, 8, 9)
LOG_RATIO_EDGES = np.asarray([-np.inf, -1.25, -0.50, 0.0, 0.50, 1.25, np.inf], dtype=np.float64)
ODDS_EDGES = np.asarray([0.0, 10.0, 20.0, 40.0, 80.0, np.inf], dtype=np.float64)
PARENT_PRIOR_EXPECTED = 50.0
CELL_PRIOR_EXPECTED = 20.0
LIFT_MIN = 0.50
LIFT_MAX = 2.00
EV_THRESHOLDS = (0.95, 1.00, 1.02, 1.05, 1.10, 1.20)
MAX_ODDS_LEVELS = (20.0, 40.0, 80.0, 150.0)
MIN_PROBABILITY = 0.005


def lane_group(first_lane: int) -> int:
    if first_lane == 1:
        return 0
    if first_lane in (2, 3):
        return 1
    return 2


def combo_lane_groups(combos: np.ndarray) -> np.ndarray:
    groups=[]
    for raw in combos.tolist():
        first=int(str(raw).split('-')[0])
        groups.append(lane_group(first))
    return np.asarray(groups, dtype=np.int8)


def bucket_arrays(cache: v14.Cache, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    model=cache.model_p[mask]
    market=cache.market_p[mask]
    odds=cache.odds[mask]
    valid=(model>0.0)&(market>0.0)&(odds>0.0)
    log_ratio=np.zeros_like(model, dtype=np.float64)
    log_ratio[valid]=np.log(model[valid]/market[valid])
    ratio_bin=np.digitize(log_ratio, LOG_RATIO_EDGES[1:-1], right=False).astype(np.int8)
    odds_bin=np.digitize(odds, ODDS_EDGES[1:-1], right=False).astype(np.int8)
    return ratio_bin, odds_bin, valid


def fit(cache: v14.Cache) -> dict[str, Any]:
    mask=np.isin(cache.month, CAL_MONTHS)
    model=cache.model_p[mask]
    market=cache.market_p[mask]
    odds=cache.odds[mask]
    actual=cache.actual[mask]
    ratio_bin, odds_bin, valid=bucket_arrays(cache, mask)
    lane_groups=combo_lane_groups(cache.combos)
    rows=np.arange(len(actual))

    parent: dict[tuple[int,int], dict[str,float]]={}
    for g in range(3):
        lane_mask=(lane_groups[None,:]==g)
        for rb in range(len(LOG_RATIO_EDGES)-1):
            cell=valid & lane_mask & (ratio_bin==rb)
            expected=float(market[cell].sum())
            hit_mask=(lane_groups[actual]==g) & (ratio_bin[rows,actual]==rb) & valid[rows,actual]
            observed=float(hit_mask.sum())
            lift=(observed+PARENT_PRIOR_EXPECTED)/(expected+PARENT_PRIOR_EXPECTED)
            lift=max(LIFT_MIN,min(LIFT_MAX,lift))
            parent[(g,rb)]={"observed":observed,"expected":expected,"lift":lift,"candidates":int(cell.sum())}

    cells: dict[tuple[int,int,int], dict[str,float]]={}
    for g in range(3):
        lane_mask=(lane_groups[None,:]==g)
        for rb in range(len(LOG_RATIO_EDGES)-1):
            parent_lift=parent[(g,rb)]["lift"]
            for ob in range(len(ODDS_EDGES)-1):
                cell=valid & lane_mask & (ratio_bin==rb) & (odds_bin==ob)
                expected=float(market[cell].sum())
                hit_mask=(
                    (lane_groups[actual]==g)
                    & (ratio_bin[rows,actual]==rb)
                    & (odds_bin[rows,actual]==ob)
                    & valid[rows,actual]
                )
                observed=float(hit_mask.sum())
                lift=(observed + CELL_PRIOR_EXPECTED*parent_lift)/(expected+CELL_PRIOR_EXPECTED)
                lift=max(LIFT_MIN,min(LIFT_MAX,lift))
                cells[(g,rb,ob)]={"observed":observed,"expected":expected,"lift":lift,"candidates":int(cell.sum())}
    return {"parent":parent,"cells":cells,"sampleRaces":int(mask.sum())}


def calibrated_month(cache:v14.Cache, month:int, fitted:dict[str,Any]) -> tuple[np.ndarray,np.ndarray,np.ndarray]:
    mask=cache.month==month
    model=cache.model_p[mask]
    market=cache.market_p[mask]
    odds=cache.odds[mask]
    ratio_bin, odds_bin, valid=bucket_arrays(cache, mask)
    lane_groups=combo_lane_groups(cache.combos)
    lift=np.ones_like(market,dtype=np.float64)
    for g in range(3):
        lane_mask=lane_groups[None,:]==g
        for rb in range(len(LOG_RATIO_EDGES)-1):
            for ob in range(len(ODDS_EDGES)-1):
                select=lane_mask & (ratio_bin==rb) & (odds_bin==ob)
                lift=np.where(select,float(fitted["cells"][(g,rb,ob)]["lift"]),lift)
    weights=np.where(valid,market*lift,0.0)
    totals=weights.sum(axis=1,keepdims=True)
    calibrated=np.divide(weights,totals,out=np.zeros_like(weights),where=totals>0.0)
    ev=calibrated*odds
    return calibrated,ev,odds


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    cache=v14.Cache(args.cache_dir/'signal_cache_2023.npz')
    if cache.year!=2023:
        raise SystemExit('2023 cache required')
    fitted=fit(cache)

    monthly:dict[str,Any]={}
    aggregate={f"ev{thr:.2f}":0 for thr in EV_THRESHOLDS}
    max_seen=0.0
    for month in TEST_MONTHS:
        p,ev,odds=calibrated_month(cache,month,fitted)
        max_seen=max(max_seen,float(ev.max(initial=0.0)))
        row:dict[str,Any]={"races":int(len(ev)),"maxEv":round(float(ev.max(initial=0.0)),4)}
        for thr in EV_THRESHOLDS:
            key=f"ev{thr:.2f}"
            candidate=(ev>=thr)&(p>=MIN_PROBABILITY)&(odds>0.0)
            race_count=int(candidate.any(axis=1).sum())
            combo_count=int(candidate.sum())
            row[key]={"racesWithCandidate":race_count,"candidateCombos":combo_count}
            aggregate[key]+=race_count
        row["byMaxOdds"]={}
        for cap in MAX_ODDS_LEVELS:
            candidate=(ev>=1.02)&(p>=MIN_PROBABILITY)&(odds>0.0)&(odds<=cap)
            row["byMaxOdds"][str(int(cap))]={
                "racesWithCandidate":int(candidate.any(axis=1).sum()),
                "candidateCombos":int(candidate.sum()),
            }
        monthly[f"2023-{month:02d}"]=row

    cell_rows=[]
    for (g,rb,ob),values in fitted['cells'].items():
        cell_rows.append({
            "laneGroup":('1' if g==0 else '2-3' if g==1 else '4-6'),
            "logRatioLow":None if math.isinf(LOG_RATIO_EDGES[rb]) else float(LOG_RATIO_EDGES[rb]),
            "logRatioHigh":None if math.isinf(LOG_RATIO_EDGES[rb+1]) else float(LOG_RATIO_EDGES[rb+1]),
            "oddsLow":float(ODDS_EDGES[ob]),
            "oddsHigh":None if math.isinf(ODDS_EDGES[ob+1]) else float(ODDS_EDGES[ob+1]),
            "observed":round(float(values['observed']),3),
            "marketExpected":round(float(values['expected']),3),
            "candidates":int(values['candidates']),
            "lift":round(float(values['lift']),6),
        })
    cell_rows.sort(key=lambda x:(x['lift'],x['marketExpected']),reverse=True)

    result={
        "schemaVersion":1,
        "generatedAt":datetime.now(timezone.utc).isoformat(),
        "diagnosticOnly":True,
        "calibrationPeriod":"2023-02-01..2023-04-30",
        "candidatePeriod":"2023-05-01..2023-09-30",
        "candidateOutcomesRead":False,
        "evaluationYearsOpened":[],
        "reservedHoldoutOpened":False,
        "sampleRaces":fitted['sampleRaces'],
        "hierarchy":{"parentPriorExpected":PARENT_PRIOR_EXPECTED,"cellPriorExpected":CELL_PRIOR_EXPECTED,"liftCap":[LIFT_MIN,LIFT_MAX]},
        "maxCalibratedEv":round(max_seen,4),
        "monthlyCandidateVolume":monthly,
        "aggregateRaceCounts":aggregate,
        "topCalibrationCells":cell_rows[:30],
        "note":"May-Sep outcomes are not used; this measures only pre-race candidate availability after hierarchical calibration.",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({"maxCalibratedEv":result['maxCalibratedEv'],"aggregateRaceCounts":aggregate,"monthlyCandidateVolume":monthly,"topCells":cell_rows[:10]},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
