#!/usr/bin/env python3
"""Build preview-enhanced signal caches including raw per-racer feature vectors.

This extends the existing preview cache for model-body research. It preserves the
leakage-safe monthly walk-forward conditional probabilities and archived market odds,
but also stores the exact 6x32 pre-race racer feature matrix used for each accepted
race. No result-time feature is added.
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
    ap=argparse.ArgumentParser()
    ap.add_argument('--year',type=int,required=True)
    ap.add_argument('--learning',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--metadata',type=Path,required=True)
    ap.add_argument('--workers',type=int,default=16)
    args=ap.parse_args()
    year=int(args.year)
    if year not in (2023,2024,2025): raise SystemExit('supports 2023-2025')
    learning_json=json.loads(args.learning.read_text(encoding='utf-8'))
    expected=f'{year-1}-12-31'
    if learning_json.get('trainedThrough')!=expected: raise SystemExit(f'learning leakage guard expected={expected} got={learning_json.get("trainedThrough")}')
    if learning_json.get('snapshotComplete') is not True: raise SystemExit('learning snapshot incomplete')

    records,record_source=build_records_from_kfiles(year=year,learning_json=learning_json,workers=args.workers)
    if float(record_source.get('programMetricCoverage',0.0))<90.0: raise SystemExit(f'program coverage too low: {record_source}')
    preview_by_day,preview_errors=fetch_preview_range(date(year,1,1),date(year,9,30),args.workers)
    if preview_errors: raise SystemExit(f'preview failures: {preview_errors}')
    preview_source=apply_preview_overlay(records,preview_by_day)
    if float(preview_source.get('raceCoverage',0.0))<95.0: raise SystemExit(f'preview coverage too low: {preview_source}')
    odds_by_day,odds_errors=fetch_archived_odds(year,args.workers)
    if odds_errors: raise SystemExit(f'odds failures: {odds_errors}')

    combos=all_combinations(); combo_index={c:i for i,c in enumerate(combos)}
    months=[]; actuals=[]; amounts=[]; model_rows=[]; market_rows=[]; odds_rows=[]; racer_rows=[]
    venues=[]; race_numbers=[]; day_ordinals=[]
    counts={}; missing={}

    for month in MONTHS:
        model=v9.v6.fit_conditional_model(records,date(year,1,1),month_end(year,month-1))
        accepted=0; absent=0
        for rec in records:
            if not (date(year,month,1)<=rec['day']<=month_end(year,month)): continue
            race_odds=odds_by_day.get(rec['day'],{}).get((int(rec['venue']),int(rec['raceNumber'])))
            if not race_odds:
                absent+=1; continue
            distribution=v9.full_distribution(model,rec)
            market_sum=sum(1.0/o for o in race_odds.values() if o>0)
            if not distribution or market_sum<=0:
                absent+=1; continue
            actual=combo_index.get(str(rec['combo']))
            if actual is None:
                absent+=1; continue
            mp=np.zeros(120,dtype=np.float32); mkp=np.zeros(120,dtype=np.float32); od=np.zeros(120,dtype=np.float32)
            for combo,p in distribution:
                idx=combo_index.get(combo); odd=race_odds.get(combo)
                if idx is None or odd is None or odd<=0: continue
                mp[idx]=float(p); mkp[idx]=float((1.0/odd)/market_sum); od[idx]=float(odd)
            valid=(mp>0)&(mkp>0)&(od>0)
            features=np.asarray(rec['features'],dtype=np.float32)
            if int(valid.sum())<100 or not valid[actual] or features.shape!=(6,32):
                absent+=1; continue
            months.append(month); actuals.append(actual); amounts.append(int(rec['amount']))
            model_rows.append(mp); market_rows.append(mkp); odds_rows.append(od); racer_rows.append(features)
            venues.append(int(rec['venue'])); race_numbers.append(int(rec['raceNumber'])); day_ordinals.append(int(rec['day'].toordinal()))
            accepted+=1
        key=f'{year}-{month:02d}'; counts[key]=accepted; missing[key]=absent
        print(f'{key}: rich cached={accepted} missing={absent}',flush=True)

    if not model_rows: raise SystemExit('no rich signals')
    if any(counts.get(f'{year}-{m:02d}',0)<500 for m in MONTHS): raise SystemExit(f'insufficient signals: {counts}')
    args.output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.output,
        year=np.asarray([year],dtype=np.int16),combos=np.asarray(combos,dtype='U5'),month=np.asarray(months,dtype=np.int8),
        actual_index=np.asarray(actuals,dtype=np.int16),amount=np.asarray(amounts,dtype=np.int32),
        model_p=np.stack(model_rows).astype(np.float32),market_p=np.stack(market_rows).astype(np.float32),odds=np.stack(odds_rows).astype(np.float32),
        racer_features=np.stack(racer_rows).astype(np.float32),venue=np.asarray(venues,dtype=np.int8),race_number=np.asarray(race_numbers,dtype=np.int8),day_ordinal=np.asarray(day_ordinals,dtype=np.int32))
    meta:dict[str,Any]={
        'schemaVersion':3,'generatedAt':datetime.now(timezone.utc).isoformat(),'year':year,'learningTrainedThrough':learning_json.get('trainedThrough'),
        'recordSource':record_source,'previewSource':preview_source,'previewArchive':{'repository':'BoatraceOpenAPI/previews','availableFrom':PREVIEW_AVAILABLE_FROM.isoformat(),'policy':'pre-race only'},
        'signalCounts':counts,'missingRaces':missing,'cachedRaces':len(months),'comboCount':120,'racerFeatureShape':[6,32],
        'featurePolicy':'exact preview-enhanced 6x32 pre-race feature matrix; historical learning bonus forced zero by overlay',
    }
    args.metadata.parent.mkdir(parents=True,exist_ok=True); args.metadata.write_text(json.dumps(meta,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({'year':year,'cachedRaces':len(months),'previewSource':preview_source,'signalCounts':counts,'racerFeatureShape':[6,32]},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
