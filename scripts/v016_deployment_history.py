#!/usr/bin/env python3
"""Advance frozen Model A player history after final holdout; no model retraining or odds."""
from __future__ import annotations
import argparse, json, time, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
import numpy as np
from v016_core_research import dump
from v016_r4_features import COMBOS, COMBO_TEXT, extract_pre
from v016_r4_player_history import PlayerHistory, enrich

# Current 2026 sources are pinned at the exact gh-pages revisions observed before
# this release. The upstream historical format moved from docs/v3 to docs/v2 in
# April; normalize v2 keys into the frozen r4 inference schema below.
SOURCE={
    'programs':('boatraceopenapi/programs','e4032602493edd52d1a1d00ae9e58bd080ab7a98'),
    'previews':('boatraceopenapi/previews','1dd0b5868f3638b6d917d013a2a91366406292f9'),
    'results':('boatraceopenapi/results','ddac62a656494dbad1a69e172d50725c145e69e7')
}
START=date(2026,1,1)


def source_url(day,kind,through):
    if not START<=day<=through: raise ValueError('Deployment history date fence')
    if kind not in SOURCE: raise ValueError('Only programs/previews/results are allowed')
    repo,sha=SOURCE[kind]
    return f'https://raw.githubusercontent.com/{repo}/{sha}/docs/v2/2026/{day:%Y%m%d}.json'


def normalize(kind,row):
    common={
        'date':row.get('race_date'),
        'stadium_number':row.get('race_stadium_number'),
        'number':row.get('race_number')
    }
    if kind=='programs':
        out=dict(row); out.update(common); return out
    if kind=='previews':
        boats=row.get('boats',{})
        if isinstance(boats,dict): boats=list(boats.values())
        out=dict(row); out.update(common); out.update({
            'boats':boats,
            'wind_speed':row.get('race_wind'),
            'wind_direction_number':row.get('race_wind_direction_number'),
            'wave_height':row.get('race_wave'),
            'air_temperature':row.get('race_temperature'),
            'water_temperature':row.get('race_water_temperature')
        }); return out
    if kind=='results':
        out=dict(row); out.update(common); return out
    raise ValueError('Unknown source kind')


def read_day(day,through):
    out={}
    for kind in SOURCE:
        url=source_url(day,kind,through)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BOAT-AI-v016-deployment-history'}),timeout=45) as r: raw=r.read()
                records=json.loads(raw)[kind]; keyed={}
                for original in records:
                    row=normalize(kind,original)
                    if row.get('date')!=day.isoformat(): raise ValueError('Source date mismatch')
                    key=(int(row['stadium_number']),int(row['number']))
                    if key in keyed: raise ValueError('Duplicate race')
                    if kind=='results': keyed[key]={'date':row['date'],'stadium_number':row['stadium_number'],'number':row['number'],'boats':[{k:b.get(k) for k in ('racer_boat_number','racer_number','racer_place_number')} for b in row.get('boats',[])]}
                    else: keyed[key]=row
                out[kind]=keyed; break
            except ValueError: raise
            except Exception:
                if attempt==2: raise
                time.sleep(attempt+1)
    return out


def finish_index(program,result):
    if not result:return None
    pb={b['racer_boat_number']:b for b in program.get('boats',[])}; rb={b['racer_boat_number']:b for b in result.get('boats',[])}
    if len(pb)!=6 or len(rb)!=6 or set(pb)!=set(range(1,7)) or set(rb)!=set(pb):return None
    places=[rb[i].get('racer_place_number') for i in range(1,7)]
    if set(places)!=set(range(1,7)):return None
    if any(rb[i].get('racer_number')!=pb[i].get('racer_number') for i in range(1,7)):raise ValueError('Racer ID mismatch')
    order=tuple(places.index(i) for i in (1,2,3)); ix=np.flatnonzero(np.all(COMBOS==order,axis=1))
    return int(ix[0]) if len(ix)==1 else None


def build_chunk(days,through):
    rows=[]; counts=Counter()
    with ThreadPoolExecutor(max_workers=12) as pool:
        tasks={pool.submit(read_day,d,through):d for d in days}
        for task in as_completed(tasks):
            day=tasks[task]; src=task.result(); counts['sourceRaces']+=len(src['programs'])
            for venue,race in sorted(src['programs']):
                program=src['programs'][venue,race]; label=finish_index(program,src['results'].get((venue,race)))
                if label is None: counts['skippedUnsettledOrNonUnique']+=1; continue
                counts['eligibleSettled']+=1
                try:
                    preview=src['previews'].get((venue,race))
                    if preview is not None and not isinstance(preview.get('boats',[]),list): raise TypeError('preview boats is not a list')
                    b,g,ids,classes,usable=extract_pre(program,preview,day,venue,race)
                except (TypeError,KeyError,IndexError,ValueError):
                    counts['malformedPreRaceInput']+=1; continue
                if not usable: counts['missingRequiredInput']+=1
                rows.append((day.toordinal(),day.month,venue,race,label,b,g,ids,classes,usable))
    rows.sort(key=lambda r:(r[0],r[2],r[3])); names=('day_ordinal','month','venue','race_number','actual_index','current','global_features','racer_id','racer_class','usable')
    c={name:np.asarray([r[i] for r in rows]) for i,name in enumerate(names)}; c['year']=np.asarray([2026]); c['combos']=COMBO_TEXT
    return c,dict(counts)


def run(args):
    through=date.fromisoformat(args.through)
    if not START<=through<=date(2026,9,23): raise ValueError('Deployment through-date not preregistered for this release')
    state=json.loads(args.state.read_text()); history=PlayerHistory(state)
    if history.state['lastDay']!=date(2025,12,31).toordinal(): raise ValueError('Deployment seed must be final holdout state through 2025-12-31')
    total=Counter(); day=START
    while day<=through:
        month_end=(date(day.year+1,1,1)-timedelta(days=1)) if day.month==12 else (date(day.year,day.month+1,1)-timedelta(days=1))
        end=min(month_end,through); days=[day+timedelta(days=i) for i in range((end-day).days+1)]
        c,counts=build_chunk(days,through)
        if len(c['month'])==0: raise ValueError(f'No eligible races in {day:%Y-%m}')
        enrich(c,history)
        for k,v in counts.items(): total[k]+=v
        print(f'deployment history through {end}: players={len(history.state["recent"])} races={history.state["updateRaces"]}',flush=True)
        day=end+timedelta(days=1)
    if history.state['lastDay']!=through.toordinal(): raise ValueError('History did not advance through target date')
    args.output.parent.mkdir(parents=True,exist_ok=True); dump(args.output,history.state)
    summary={'through':through.isoformat(),'lastDay':history.state['lastDay'],'updateRaces':history.state['updateRaces'],'registeredPlayers':len(history.state['recent']),
             'population':dict(total),'sourceCommits':{k:v[1] for k,v in SOURCE.items()},'sourceSchema':'docs/v2 normalized to frozen r4 schema',
             'oddsRead':False,'payoutRead':False,'modelRetrained':False}
    dump(args.output.with_suffix('.summary.json'),summary); print(json.dumps(summary,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--state',type=Path,required=True); p.add_argument('--through',required=True); p.add_argument('--output',type=Path,required=True); run(p.parse_args())
