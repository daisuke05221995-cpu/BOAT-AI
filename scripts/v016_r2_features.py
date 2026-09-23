#!/usr/bin/env python3
"""Pre-race whitelist sidecar. Reuses outcomes/odds; never requests results or Q4."""
import argparse
import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import numpy as np
from v016_core_research import dump, digest

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / 'data/v016_r2_protocol.json'
PROGRAM_FIELDS = ['racer_national_top_1_percent', 'racer_local_top_1_percent',
 'racer_national_top_2_percent', 'racer_local_top_2_percent',
 'racer_national_top_3_percent', 'racer_local_top_3_percent',
 'racer_assigned_motor_top_2_percent', 'racer_assigned_motor_top_3_percent',
 'racer_assigned_boat_top_2_percent', 'racer_assigned_boat_top_3_percent',
 'racer_average_start_timing', 'racer_flying_count', 'racer_late_count',
 'racer_age', 'racer_weight']
PREVIEW_FIELDS = ['racer_exhibition_time', 'racer_start_timing',
 'racer_course_number', 'racer_tilt_adjustment', 'racer_weight_adjustment']
FEATURES = PROGRAM_FIELDS + PREVIEW_FIELDS + ['class_1','class_2','class_3','class_4','course_changed']
WEATHER = ['wind_speed','wave_height','air_temperature','water_temperature']
GLOBALS = WEATHER + ['wind_direction_'+str(i) for i in range(1,17)] + ['venue','race_number']

def allowed(day):
    if not (date(2023,5,1) <= day <= date(2023,9,30) or day.year == 2024):
        raise ValueError('r2 date fence: only 2023 May-Sep and full 2024; all 2025 sealed')

def number(value):
    try:
        v = float(value)
        return v if np.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan

def extract(program, preview, day, venue, race):
    allowed(day)
    b = np.full((6,len(FEATURES)), np.nan, np.float32)
    g = np.full(len(GLOBALS), np.nan, np.float32)
    if not program or not preview: return b,g,False
    for src in (program,preview):
        if (str(src.get('date')),src.get('stadium_number'),src.get('number')) != (day.isoformat(),venue,race):
            raise ValueError('Pre-race archive race key mismatch')
    pb = {x['racer_boat_number']:x for x in program.get('boats',[])}
    eb = {x['racer_boat_number']:x for x in preview.get('boats',[])}
    if set(pb) != set(range(1,7)) or set(eb) != set(range(1,7)): return b,g,False
    for lane in range(1,7):
        p,e = pb[lane],eb[lane]
        cls = p.get('racer_class_number')
        b[lane-1] = ([number(p.get(k)) for k in PROGRAM_FIELDS] +
                     [number(e.get(k)) for k in PREVIEW_FIELDS] +
                     [float(cls==i) if cls is not None else np.nan for i in range(1,5)] +
                     [float(e['racer_course_number'] != lane) if e.get('racer_course_number') is not None else np.nan])
    wd = preview.get('wind_direction_number')
    g[:] = ([number(preview.get(k)) for k in WEATHER] +
            [float(wd==i) if wd is not None else np.nan for i in range(1,17)] + [venue,race])
    # Missing optional program metrics retain NaN plus explicit missing flags.
    # Missing exhibition time/ST/course on any boat causes a pre-race SKIP.
    usable = bool(np.isfinite(b[:,15:18]).all() and np.isfinite(b[:,0]).all())
    return b,g,usable

def fetch_day(day, commits):
    allowed(day)  # BEFORE URL construction/network, including every retry.
    result = {}; hashes = {}
    for kind in ('programs','previews'):
        url = f'https://raw.githubusercontent.com/BoatraceOpenAPI/{kind}/{commits[kind]}/docs/v3/{day.year}/{day:%Y%m%d}.json'
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BOAT-AI-v016-r2'}),timeout=40) as r:
                    raw = r.read()
                payload = json.loads(raw)
                records = payload[kind]
                keyed = {(int(x['stadium_number']),int(x['number'])):x for x in records}
                if len(keyed) != len(records): raise ValueError('Duplicate source race')
                result[kind] = keyed
                hashes[kind] = hashlib.sha256(raw).hexdigest()
                break
            except Exception:
                if attempt == 2: raise
                time.sleep(attempt+1)
    return result,hashes

def load(path, year, features=True):
    if year not in (2023,2024): raise ValueError('All 2025 access sealed in r2')
    with np.load(path,allow_pickle=False) as z:
        days=z['day_ordinal']; months=z['month']
        if int(z['year'][0]) != year: raise ValueError('Year mismatch')
        for d,m in zip(days,months):
            dt=date.fromordinal(int(d))
            if dt.year != year or dt.month != int(m): raise ValueError('Date axis mismatch')
            # Original 2023 cache also has February-April. Inspect dates before outcomes.
            if features or year==2024: allowed(dt)
            elif not date(2023,2,1)<=dt<=date(2023,9,30): raise ValueError('Source dates outside fence')
        keys=['year','combos','month','day_ordinal','venue','race_number','actual_index','amount','market_p','odds']
        if features: keys += ['boat','global_features','usable']
        c={k:z[k] for k in keys}
    if year==2023 and not features:
        take=c['month']>=5
        c={k:v if k in ('year','combos') else v[take] for k,v in c.items()}
    n=len(c['month'])
    keys=np.stack([c['day_ordinal'],c['venue'],c['race_number']],axis=1)
    if len(np.unique(keys,axis=0))!=n: raise ValueError('Duplicate cached race')
    for k in ('market_p','odds'):
        if c[k].shape!=(n,120) or not np.isfinite(c[k]).all(): raise ValueError('Invalid '+k)
    return c

def build(args):
    c=load(args.cache,args.year,features=False)
    protocol=json.loads(PROTOCOL.read_text())
    n=len(c['month']); c['boat']=np.full((n,6,len(FEATURES)),np.nan,np.float32)
    c['global_features']=np.full((n,len(GLOBALS)),np.nan,np.float32); c['usable']=np.zeros(n,bool)
    hashes={}; days=np.unique(c['day_ordinal'])
    with ThreadPoolExecutor(max_workers=12) as pool:
        futures={pool.submit(fetch_day,date.fromordinal(int(d)),protocol['sourceCommits']):int(d) for d in days}
        for step,f in enumerate(as_completed(futures),1):
            d=futures[f]; sources,h=f.result(); hashes[date.fromordinal(d).isoformat()]=h
            for i in np.flatnonzero(c['day_ordinal']==d):
                key=(int(c['venue'][i]),int(c['race_number'][i]))
                b,g,ok=extract(sources['programs'].get(key),sources['previews'].get(key),date.fromordinal(d),*key)
                c['boat'][i]=b; c['global_features'][i]=g; c['usable'][i]=ok
            if step%30==0: print(f'{args.year}: {step}/{len(days)} days',flush=True)
    coverage={str(m):{'races':int((c['month']==m).sum()),'usable':int(c['usable'][c['month']==m].sum()),
                     'coverage':float(c['usable'][c['month']==m].mean())} for m in np.unique(c['month'])}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.output,**c)
    dump(args.output.with_suffix('.json'),{'year':args.year,'races':n,'coverage':coverage,'sourceHashes':hashes,
         'sourceCommits':protocol['sourceCommits'],'reusedCacheSha256':digest(args.cache),
         'features':FEATURES,'globals':GLOBALS,'holdoutOpened':False,'captureTimeVerified':False})
    if any(v['coverage']<protocol['featureCoveragePerMonthMin'] for v in coverage.values()):
        raise ValueError('Monthly pre-race feature coverage below fixed 95% gate')

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--year',type=int,required=True)
    p.add_argument('--cache',type=Path,required=True); p.add_argument('--output',type=Path,required=True)
    build(p.parse_args())
