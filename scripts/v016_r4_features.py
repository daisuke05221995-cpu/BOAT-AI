#!/usr/bin/env python3
"""Pinned pre-race sources and reuse of 2024 outcomes. Q4 denied before I/O."""
import argparse
import calendar
import hashlib
import itertools
import json
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
import numpy as np
from v016_core_research import canonical, digest, dump
from v016_r2_features import PROGRAM_FIELDS, PREVIEW_FIELDS, FEATURES as CURRENT_NAMES, GLOBALS, WEATHER, number

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'data/v016_r4_protocol.json'
COMBOS=np.asarray(list(itertools.permutations(range(6),3)))
COMBO_TEXT=np.asarray(['-'.join(str(i+1) for i in row) for row in COMBOS])
STATIC={'year','combos','boat_names','history_names','reaction_names'}

def guard_day(day, september=False):
    if day.year==2024: return
    if day.year==2025 and day<=date(2025,8,31): return
    if september and date(2025,9,1)<=day<=date(2025,9,30): return
    raise ValueError('r4 date fence: September needs a frozen candidate; Q4 is always sealed')

def frozen_lock(path):
    x=json.loads(Path(path).read_text())
    payload=x.get('candidate')
    if not payload or x.get('freezeSha256')!=canonical(payload): raise ValueError('Invalid/no frozen r4 candidate')
    if payload['protocolSha256']!=digest(PROTOCOL): raise ValueError('Protocol changed after freeze')
    for name,sha in payload['codeSha256'].items():
        if digest(ROOT/name)!=sha: raise ValueError('Code changed after freeze: '+name)
    return x

def source_url(kind,day,source,september=False):
    guard_day(day,september)  # Deliberately before URL construction.
    return f"https://raw.githubusercontent.com/{source['repo']}/{source['commit']}/docs/v3/{day.year}/{day:%Y%m%d}.json"

def read_cache(path,september=False):
    with np.load(path,allow_pickle=False) as z:
        days=z['day_ordinal']; months=z['month']
        for d,m in zip(days,months):
            dt=date.fromordinal(int(d)); guard_day(dt,september)
            if dt.month!=int(m): raise ValueError('Date/month mismatch')
        c={k:z[k] for k in z.files}
    if not len(days): raise ValueError('Empty cache')
    if 'combos' in c and not np.array_equal(c['combos'],COMBO_TEXT): raise ValueError('Combination order mismatch')
    keys=np.stack([days,c['venue'],c['race_number']],axis=1)
    if len(np.unique(keys,axis=0))!=len(days): raise ValueError('Duplicate race')
    return c

def subset(c,mask):
    return {k:v if k in STATIC else v[mask] for k,v in c.items()}

def extract_pre(program,preview,day,venue,race):
    # Day access is separately authorized by the source/cache reader, never inferred here.
    b=np.full((6,len(CURRENT_NAMES)),np.nan,np.float32); g=np.full(len(GLOBALS),np.nan,np.float32)
    ids=np.zeros(6,np.int32); classes=np.zeros(6,np.int8)
    if not program or not preview: return b,g,ids,classes,False
    for src in [program,preview]:
        if (src.get('date'),src.get('stadium_number'),src.get('number'))!=(day.isoformat(),venue,race):
            raise ValueError('Source race key mismatch')
    pb={x['racer_boat_number']:x for x in program.get('boats',[])}
    eb={x['racer_boat_number']:x for x in preview.get('boats',[])}
    if len(program['boats'])!=6 or len(preview['boats'])!=6 or set(pb)!=set(range(1,7)) or set(eb)!=set(pb):
        return b,g,ids,classes,False
    for lane in range(1,7):
        p,e=pb[lane],eb[lane]; cls=p.get('racer_class_number')
        ids[lane-1]=int(p.get('racer_number') or 0); classes[lane-1]=int(cls or 0)
        b[lane-1]=([number(p.get(k)) for k in PROGRAM_FIELDS]+[number(e.get(k)) for k in PREVIEW_FIELDS]+
                   [float(cls==i) if cls is not None else np.nan for i in range(1,5)]+
                   [float(e['racer_course_number']!=lane) if e.get('racer_course_number') is not None else np.nan])
    wd=preview.get('wind_direction_number')
    g[:]=[number(preview.get(k)) for k in WEATHER]+[float(wd==i) if wd is not None else np.nan for i in range(1,17)]+[venue,race]
    ok=(np.isfinite(b[:,15:18]).all() and np.isfinite(b[:,0]).all() and (ids>0).all() and len(set(ids))==6
        and set(b[:,17].astype(int))==set(range(1,7)))
    return b,g,ids,classes,bool(ok)

def result_label(result,program):
    """Read finish order and payout only; actual ST/course/weather are ignored."""
    if not result: return None
    pb={x['racer_boat_number']:x for x in program.get('boats',[])}
    rb={x['racer_boat_number']:x for x in result.get('boats',[])}
    if len(rb)!=6 or set(rb)!=set(range(1,7)) or set(pb)!=set(rb): return None
    if any(rb[i].get('racer_number')!=pb[i].get('racer_number') for i in rb): raise ValueError('Result/program racer-ID mismatch')
    places=[rb[i].get('racer_place_number') for i in range(1,7)]
    if set(places)!=set(range(1,7)): return None
    payouts=result.get('payouts',{}).get('trifecta',[])
    if len(payouts)!=1: return None
    text=payouts[0].get('combination'); amount=payouts[0].get('amount')
    matches=np.flatnonzero(COMBO_TEXT==text)
    if len(matches)!=1 or not amount or amount<=0: return None
    idx=int(matches[0]); order=COMBOS[idx]
    if [places[i] for i in order]!=[1,2,3]: raise ValueError('Finish/payout combination mismatch')
    return idx,int(amount)

def fetch_day(day,seed,september=False):
    proto=json.loads(PROTOCOL.read_text()); sources={}; hashes={}
    for kind in (['programs','previews'] if seed else ['programs','previews','results','odds']):
        url=source_url(kind,day,proto['sources'][kind],september)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BOAT-AI-r4-research'}),timeout=45) as response:
                    raw=response.read()
                records=json.loads(raw)[kind]; keys={}
                for row in records:
                    if row.get('date')!=day.isoformat(): raise ValueError('Source day mismatch')
                    key=(int(row['stadium_number']),int(row['number']))
                    if key in keys: raise ValueError('Duplicate source race')
                    keys[key]=row
                sources[kind]=keys; hashes[kind]=hashlib.sha256(raw).hexdigest(); break
            except Exception:
                if attempt==2: raise
                time.sleep(attempt+1)
    return sources,hashes

def build_raw(args):
    september=bool(args.lock)
    if september: frozen_lock(args.lock)
    begin=date(args.year,args.start_month,1); end=date(args.year,args.end_month,calendar.monthrange(args.year,args.end_month)[1])
    if begin>end: raise ValueError('Reversed date range')
    days=[begin+timedelta(days=i) for i in range((end-begin).days+1)]
    for d in days: guard_day(d,september)
    if args.year not in (2024,2025): raise ValueError('Unknown year')
    seed={}
    if args.year==2024:
        if not args.seed_cache: raise ValueError('2024 must reuse annual cache')
        c=read_cache(args.seed_cache)
        if set(date.fromordinal(int(d)).year for d in c['day_ordinal'])!={2024}: raise ValueError('Wrong seed year')
        for i,d in enumerate(c['day_ordinal']):
            seed.setdefault(int(d),{})[(int(c['venue'][i]),int(c['race_number'][i]))]=(int(c['actual_index'][i]),int(c['amount'][i]))
    records=[]; hashes={}; ledger={}
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(fetch_day,d,args.year==2024,september):d for d in days}
        for step,future in enumerate(as_completed(futures),1):
            day=futures[future]; src,h=future.result(); hashes[day.isoformat()]=h; counts=Counter()
            keys=seed.get(day.toordinal(),{}) if args.year==2024 else src['programs']
            for venue,race in sorted(keys):
                counts['sourceRaces']+=1; key=(venue,race); program=src['programs'].get(key)
                if not program: counts['missingProgram']+=1; continue
                label=seed[day.toordinal()][key] if args.year==2024 else result_label(src['results'].get(key),program)
                if label is None: counts['notEligibleSettledSixBoat']+=1; continue
                counts['eligibleSettled']+=1
                b,g,ids,classes,usable=extract_pre(program,src['previews'].get(key),day,venue,race)
                counts['preRaceUsable']+=int(usable)
                odds=np.zeros(120,np.float32)
                if args.year==2025:
                    tree=src['odds'].get(key,{}).get('trifecta_odds',{})
                    odds[:]=[number(tree.get(str(a+1),{}).get(str(bb+1),{}).get(str(cc+1))) for a,bb,cc in COMBOS]
                    odds_ok=bool(np.isfinite(odds).all() and (odds>0).all())
                else: odds_ok=True
                counts['oddsUsable']+=int(odds_ok); counts['jointUsable']+=int(usable and odds_ok)
                records.append((day.toordinal(),day.month,venue,race,label[0],label[1],b,g,ids,classes,usable,odds_ok,odds))
            ledger[day.isoformat()]=dict(counts)
            if step%30==0: print(f'raw {args.year}: {step}/{len(days)} days',flush=True)
    records.sort(key=lambda r:r[:1]+r[2:4])
    names=['day_ordinal','month','venue','race_number','actual_index','amount','current','global_features','racer_id','racer_class','usable','odds_usable','odds']
    c={k:np.asarray([r[i] for r in records]) for i,k in enumerate(names)}
    c['year']=np.array([args.year]); c['combos']=COMBO_TEXT
    args.output.parent.mkdir(parents=True,exist_ok=True); np.savez_compressed(args.output,**c)
    months={}
    for day,counts in ledger.items():
        month=day[:7]; target=months.setdefault(month,Counter()); target.update(counts)
    meta={'year':args.year,'start':begin.isoformat(),'end':end.isoformat(),'races':len(records),'months':months,
          'sourceHashes':hashes,'sourceCommits':json.loads(PROTOCOL.read_text())['sources'],'seedCacheSha256':digest(args.seed_cache) if args.seed_cache else None,
          'holdoutOpened':False,'oddsCaptureTimeVerified':False,'protocolSha256':digest(PROTOCOL)}
    dump(args.output.with_suffix('.json'),meta)
    for month,counts in months.items():
        if counts['eligibleSettled']<500 or counts['jointUsable']/counts['eligibleSettled']<.95:
            raise ValueError('Monthly coverage below registered gate: '+month+' '+str(counts))
    print(json.dumps({'year':args.year,'races':len(records),'months':months}))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--year',type=int,required=True); p.add_argument('--start-month',type=int,default=1)
    p.add_argument('--end-month',type=int,required=True); p.add_argument('--seed-cache',type=Path)
    p.add_argument('--lock',type=Path); p.add_argument('--output',type=Path,required=True); build_raw(p.parse_args())
