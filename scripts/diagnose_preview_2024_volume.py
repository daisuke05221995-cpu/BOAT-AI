#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import diagnose_v15_hierarchical_edge as hierarchy
import search_preview_hierarchical_2024_2025 as search


def main() -> None:
    p=argparse.ArgumentParser()
    p.add_argument('--cache-dir',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()

    cache=search.load_cache(args.cache_dir,2024)
    fitted=hierarchy.fit(cache)
    prepared={m:search.prepare_month(cache,m,fitted) for m in search.OPERATION_MONTHS}

    rows=[]
    for cfg in search.config_grid():
        monthly,total=search.evaluate_year(prepared,cfg)
        month_buys=[int(monthly[m]['purchaseRaces']) for m in search.OPERATION_MONTHS]
        rows.append({
            'config':cfg,
            'monthBuys':month_buys,
            'minMonthBuys':min(month_buys),
            'positiveMonths':sum(search.positive(monthly[m]) for m in search.OPERATION_MONTHS),
            'worstMonthRoi':min(float(monthly[m]['roi']) for m in search.OPERATION_MONTHS),
            'total':total,
            'months':{f'2024-{m:02d}':monthly[m] for m in search.OPERATION_MONTHS},
        })

    by_volume=sorted(rows,key=lambda r:(r['minMonthBuys'],r['total']['purchaseRaces'],r['positiveMonths'],r['worstMonthRoi'],r['total']['roi']),reverse=True)
    by_robust=sorted(rows,key=lambda r:(r['positiveMonths'],r['worstMonthRoi'],-r['total']['largestHitShare'],r['total']['roi'],r['total']['purchaseRaces']),reverse=True)

    candidate_volume={}
    for month in search.OPERATION_MONTHS:
        pmat,ev,odds=hierarchy.calibrated_month(cache,month,fitted)
        candidate_volume[f'2024-{month:02d}']={}
        for thr in (0.95,1.00,1.02,1.05,1.08,1.10):
            mask=(ev>=thr)&(pmat>=0.003)&(odds>0.0)&(odds<=80.0)
            candidate_volume[f'2024-{month:02d}'][f'ev{thr:.2f}']={
                'racesWithCandidate':int(mask.any(axis=1).sum()),
                'candidateCombos':int(mask.sum()),
            }

    result={
        'schemaVersion':1,
        'generatedAt':datetime.now(timezone.utc).isoformat(),
        'diagnosticOnly':True,
        'period':'2024-05-01..2024-09-30',
        'calibration':'2024-02-01..2024-04-30',
        'reservedHoldoutOpened':False,
        'candidateVolume':candidate_volume,
        'bestByVolume':by_volume[:15],
        'bestByRobustness':by_robust[:15],
        'basicGuardFeasible':any(
            r['total']['purchaseRaces']>=search.DESIGN_MIN_TOTAL_BUYS and r['minMonthBuys']>=search.DESIGN_MIN_MONTH_BUYS
            for r in rows
        ),
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({
        'basicGuardFeasible':result['basicGuardFeasible'],
        'candidateVolume':candidate_volume,
        'bestByVolume':by_volume[:5],
        'bestByRobustness':by_robust[:5],
    },ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
