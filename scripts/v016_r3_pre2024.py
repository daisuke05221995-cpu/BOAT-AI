#!/usr/bin/env python3
"""Build the missing 2023-Q4 pre-race feature sidecar for CORE r3 Q1.

Only 2023-10-01..2023-12-31 is read. Outcomes come from official BOAT RACE K
archives solely to label historical races; prediction inputs are fetched from the
fixed pre-race programs/previews commits registered in r2. 2025 is unreachable.
"""
import argparse
import hashlib
import json
import shutil
import time
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
import numpy as np
from boatrace_lzh import LzhDownloader, PerformanceParser

from build_2026_backtest import normalize_combo
from build_market_signal_cache import all_combinations
import search_2026_strategy_v9 as v9
from v016_core_research import dump, digest
from v016_r2_features import PROGRAM_FIELDS, PREVIEW_FIELDS, FEATURES, WEATHER, GLOBALS, number

ROOT=Path(__file__).resolve().parents[1]
R2_PROTOCOL=ROOT/'data/v016_r2_protocol.json'
START=date(2023,10,1); END=date(2023,12,31)


def days_between(start,end):
    out=[]; d=start
    while d<=end: out.append(d); d+=timedelta(days=1)
    return out


def result_labels(workers):
    cache=Path('.v016-r3-k-q4-2023')
    dl=LzhDownloader(cache_dir=cache,max_workers=max(1,min(workers,16)),request_delay=.15,timeout=45)
    parser=PerformanceParser(); rows=[]; parse_errors={}; days=days_between(START,END)
    try:
        for offset in range(0,len(days),31):
            chunk=days[offset:offset+31]
            downloaded=dl.download_many(chunk,'performance',max_workers=max(1,min(workers,16)))
            for day in chunk:
                files=downloaded.get(day) or {}
                if not files: continue
                try: parsed=parser.parse(files)
                except Exception as exc:
                    parse_errors[day.isoformat()]=f'{type(exc).__name__}: {exc}'; continue
                for payout in parsed.payouts:
                    if payout.ticket_type!='sanrensho' or not payout.winning_combination or int(payout.payout or 0)<=0: continue
                    combo=normalize_combo(payout.winning_combination)
                    try: venue=int(payout.venue_code); race=int(payout.race_number)
                    except (TypeError,ValueError): continue
                    if combo and 1<=venue<=24 and 1<=race<=12:
                        rows.append((day,venue,race,combo,int(payout.payout)))
            print(f'K labels: {chunk[0]}..{chunk[-1]} rows={len(rows)}',flush=True)
    finally:
        shutil.rmtree(cache,ignore_errors=True)
    if parse_errors: raise ValueError(f'K parse errors: {parse_errors}')
    if len(rows)<10000: raise ValueError(f'Q4 labels too sparse: {len(rows)}')
    if len({(d,v,r) for d,v,r,_,_ in rows})!=len(rows): raise ValueError('duplicate Q4 result keys')
    return rows


def fetch_source_day(day, commits):
    if not START<=day<=END: raise ValueError('pre2024 date fence')
    result={}; hashes={}
    for kind in ('programs','previews'):
        url=f'https://raw.githubusercontent.com/BoatraceOpenAPI/{kind}/{commits[kind]}/docs/v3/2023/{day:%Y%m%d}.json'
        last=None
        for attempt in range(3):
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'BOAT-AI-v016-r3-pre2024'})
                with urllib.request.urlopen(req,timeout=40) as resp: raw=resp.read()
                payload=json.loads(raw); records=payload[kind]
                keyed={(int(x['stadium_number']),int(x['number'])):x for x in records}
                if len(keyed)!=len(records): raise ValueError('duplicate pre-race source race')
                result[kind]=keyed; hashes[kind]=hashlib.sha256(raw).hexdigest(); break
            except Exception as exc:
                last=exc
                if attempt==2: raise
                time.sleep(attempt+1)
    return result,hashes


def extract(program, preview, day, venue, race):
    if not START<=day<=END: raise ValueError('pre2024 extraction fence')
    b=np.full((6,len(FEATURES)),np.nan,np.float32); g=np.full(len(GLOBALS),np.nan,np.float32)
    if not program or not preview: return b,g,False
    for src in (program,preview):
        if (str(src.get('date')),src.get('stadium_number'),src.get('number'))!=(day.isoformat(),venue,race):
            raise ValueError('pre-race source key mismatch')
    pb={x['racer_boat_number']:x for x in program.get('boats',[])}
    eb={x['racer_boat_number']:x for x in preview.get('boats',[])}
    if set(pb)!=set(range(1,7)) or set(eb)!=set(range(1,7)): return b,g,False
    for lane in range(1,7):
        p,e=pb[lane],eb[lane]; cls=p.get('racer_class_number')
        b[lane-1]=([number(p.get(k)) for k in PROGRAM_FIELDS]+[number(e.get(k)) for k in PREVIEW_FIELDS]+
                   [float(cls==i) if cls is not None else np.nan for i in range(1,5)]+[
                    float(e['racer_course_number']!=lane) if e.get('racer_course_number') is not None else np.nan])
    wd=preview.get('wind_direction_number')
    g[:]=([number(preview.get(k)) for k in WEATHER]+[float(wd==i) if wd is not None else np.nan for i in range(1,17)]+[venue,race])
    usable=bool(np.isfinite(b[:,15:18]).all() and np.isfinite(b[:,0]).all())
    return b,g,usable


def build(args):
    protocol=json.loads(R2_PROTOCOL.read_text()); commits=protocol['sourceCommits']
    labels=result_labels(args.workers)
    v9.ODDS_URL='https://raw.githubusercontent.com/lamrongol/BoatraceOdds/gh-pages/docs/v3/2023/{day}.json'
    odds_by_day,odds_errors=v9.fetch_odds_range(START,END,args.workers)
    if odds_errors: raise ValueError(f'odds fetch errors: {odds_errors}')
    combos=all_combinations(); combo_index={c:i for i,c in enumerate(combos)}
    base=[]; missing_odds=0
    for day,venue,race,combo,amount in labels:
        ro=odds_by_day.get(day,{}).get((venue,race))
        actual=combo_index.get(combo)
        if not ro or actual is None: missing_odds+=1; continue
        odds=np.zeros(120,np.float32); market=np.zeros(120,np.float32)
        denom=sum(1/o for o in ro.values() if o>0)
        if denom<=0: missing_odds+=1; continue
        for c,o in ro.items():
            ix=combo_index.get(c)
            if ix is not None and o>0: odds[ix]=o; market[ix]=(1/o)/denom
        valid=(odds>0)&(market>0)
        if int(valid.sum())<100 or not valid[actual]: missing_odds+=1; continue
        base.append((day,venue,race,actual,amount,market,odds))
    if len(base)<10000: raise ValueError(f'Q4 odds-matched rows too sparse: {len(base)} missing={missing_odds}')
    base.sort(key=lambda x:(x[0],x[1],x[2]))
    n=len(base); boats=np.full((n,6,len(FEATURES)),np.nan,np.float32); globals_=np.full((n,len(GLOBALS)),np.nan,np.float32); usable=np.zeros(n,bool)
    hashes={}; unique_days=sorted({x[0] for x in base}); by_day=defaultdict(list)
    for i,row in enumerate(base): by_day[row[0]].append(i)
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(fetch_source_day,d,commits):d for d in unique_days}
        for step,f in enumerate(as_completed(futures),1):
            d=futures[f]; sources,h=f.result(); hashes[d.isoformat()]=h
            for i in by_day[d]:
                _,venue,race,*_=base[i]
                b,g,ok=extract(sources['programs'].get((venue,race)),sources['previews'].get((venue,race)),d,venue,race)
                boats[i]=b; globals_[i]=g; usable[i]=ok
            if step%20==0: print(f'pre-race source: {step}/{len(unique_days)} days',flush=True)
    months=np.asarray([x[0].month for x in base],np.int8)
    coverage={str(m):{'races':int((months==m).sum()),'usable':int(usable[months==m].sum()),'coverage':float(usable[months==m].mean())} for m in (10,11,12)}
    if any(x['coverage']<.95 for x in coverage.values()): raise ValueError(f'Q4 feature coverage below 95%: {coverage}')
    out={
      'year':np.asarray([2023],np.int16),'combos':np.asarray(combos,dtype='U5'),'month':months,
      'day_ordinal':np.asarray([x[0].toordinal() for x in base],np.int32),'venue':np.asarray([x[1] for x in base],np.int16),
      'race_number':np.asarray([x[2] for x in base],np.int8),'actual_index':np.asarray([x[3] for x in base],np.int16),
      'amount':np.asarray([x[4] for x in base],np.int32),'market_p':np.stack([x[5] for x in base]),'odds':np.stack([x[6] for x in base]),
      'boat':boats,'global_features':globals_,'usable':usable,
    }
    args.output.parent.mkdir(parents=True,exist_ok=True); np.savez_compressed(args.output,**out)
    dump(args.output.with_suffix('.json'),{'year':2023,'period':'2023-10-01..2023-12-31','races':n,'coverage':coverage,
      'resultSource':'official BOAT RACE K archives','oddsSource':'lamrongol/BoatraceOdds 2023 archive','oddsMissing':missing_odds,
      'sourceCommits':commits,'sourceHashes':hashes,'features':FEATURES,'globals':GLOBALS,'r2ProtocolSha256':digest(R2_PROTOCOL),
      'holdoutOpened':False,'final2025Q4Read':False,'researchOnly':True})
    print(json.dumps({'rows':n,'coverage':coverage,'missingOdds':missing_odds},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,required=True); p.add_argument('--workers',type=int,default=16); build(p.parse_args())
