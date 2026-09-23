#!/usr/bin/env python3
"""2024 calendar-year extension of frozen r1 grid; no 2025 files permitted.

February-September signals are copied exactly from verified existing artifacts.
January conditional model uses May-September 2023 cached features only. October-
December models use current-year records strictly before each evaluation month.
This is development, not a new pristine holdout. Closing-odds limitations remain.
"""
from __future__ import annotations
import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path
import numpy as np
import v016_core_research as core

YEAR=2024
EXTRA_MONTHS=(1,10,11,12)


def build(args):
    import search_2026_strategy_v9 as v9
    from v016_kfile_records import build_records_from_kfiles
    from build_market_signal_cache import all_combinations, month_end
    from historical_preview_overlay import fetch_preview_range, apply_preview_overlay
    old=core.load_cache(args.cache,YEAR)
    prior=core.load_cache(args.prior,2023)
    learning=json.loads(args.learning.read_text())
    if learning.get('trainedThrough')!='2023-12-31' or not learning.get('snapshotComplete'):
        raise ValueError('Pre-2024 learning snapshot required')
    records,record_source=build_records_from_kfiles(year=YEAR,learning_json=learning,
                     workers=16,end_date=date(YEAR,12,31))
    previews,errors=fetch_preview_range(date(YEAR,1,1),date(YEAR,12,31),16)
    if errors: raise ValueError(f'Preview fetch errors {errors}')
    preview_source=apply_preview_overlay(records,previews)
    if preview_source['raceCoverage']<95: raise ValueError('Preview coverage below 95%')
    del previews
    v9.ODDS_URL=f'https://raw.githubusercontent.com/lamrongol/BoatraceOdds/gh-pages/docs/v3/{YEAR}/{{day}}.json'
    combos=all_combinations(); combo_index={s:i for i,s in enumerate(combos)}
    if old['combos'].tolist()!=combos or prior['combos'].tolist()!=combos: raise ValueError('Combo order mismatch')
    fields=('month','day_ordinal','venue','race_number','actual_index','amount','model_p','market_p','odds')
    parts={k:[old[k]] for k in fields}
    counts={str(m):int((old['month']==m).sum()) for m in range(2,10)}
    eligible={str(m):sum(r['day'].month==m for r in records) for m in range(1,13)}
    # Prior-year cached records only, not current-year outcomes, seed January.
    prior_records=[]
    for i in np.flatnonzero(np.isin(prior['month'],[5,6,7,8,9])):
        combo=str(prior['combos'][prior['actual_index'][i]])
        prior_records.append({'day':date.fromordinal(int(prior['day_ordinal'][i])),
            'features':prior['racer_features'][i].tolist(), 'targets':[int(x)-1 for x in combo.split('-')]})
    missing={}; training={}
    for month in EXTRA_MONTHS:
        if month==1:
            model=v9.v6.fit_conditional_model(prior_records,date(2023,5,1),date(2023,9,30))
            training[str(month)]='2023-05-01..2023-09-30 cached settled races'
        else:
            end=month_end(YEAR,month-1)
            model=v9.v6.fit_conditional_model(records,date(YEAR,1,1),end)
            training[str(month)]=f'2024-01-01..{end}'
        odds_days,errors=v9.fetch_odds_range(date(YEAR,month,1),month_end(YEAR,month),16)
        if errors: raise ValueError(f'Odds fetch errors {errors}')
        rows={k:[] for k in fields}; absent=0
        for rec in records:
            if rec['day'].month!=month:continue
            ro=odds_days.get(rec['day'],{}).get((int(rec['venue']),int(rec['raceNumber'])))
            if not ro: absent+=1;continue
            distribution=v9.full_distribution(model,rec)
            market_sum=sum(1/o for o in ro.values() if o>0)
            actual=combo_index.get(str(rec['combo']))
            if not distribution or market_sum<=0 or actual is None:absent+=1;continue
            mp=np.zeros(120,dtype=np.float32); mkp=mp.copy(); od=mp.copy()
            for combo,prob in distribution:
                idx=combo_index.get(combo); odd=ro.get(combo)
                if idx is not None and odd is not None and odd>0:
                    mp[idx]=prob;mkp[idx]=(1/odd)/market_sum;od[idx]=odd
            valid=(mp>0)&(mkp>0)&(od>0)
            if int(valid.sum())<100 or not valid[actual]:absent+=1;continue
            for key,value in dict(month=month,day_ordinal=rec['day'].toordinal(),venue=int(rec['venue']),
                 race_number=int(rec['raceNumber']),actual_index=actual,amount=int(rec['amount']),
                 model_p=mp,market_p=mkp,odds=od).items():rows[key].append(value)
        counts[str(month)]=len(rows['month']);missing[str(month)]=absent
        if counts[str(month)]<500:raise ValueError(f'Insufficient month {month}')
        for key in fields:parts[key].append(np.asarray(rows[key],dtype=old[key].dtype))
        print(json.dumps({'month':month,'accepted':counts[str(month)],'missing':absent}),flush=True)
    c={key:np.concatenate(parts[key],axis=0) for key in fields}
    order=np.lexsort((c['race_number'],c['venue'],c['day_ordinal']))
    c={key:value[order] for key,value in c.items()}
    c['year']=np.asarray([YEAR],dtype=np.int16);c['combos']=np.asarray(combos,dtype='U5')
    keys=np.stack([c['day_ordinal'],c['venue'],c['race_number']],axis=1)
    if len(np.unique(keys,axis=0))!=len(keys):raise ValueError('Duplicate keys')
    if set(c['month'].tolist())!=set(range(1,13)):raise ValueError('Not 12 months')
    if any(date.fromordinal(int(d)).year!=YEAR for d in c['day_ordinal']):raise ValueError('Year fence')
    coverage={m:100*counts[m]/max(1,eligible[m]) for m in eligible}
    if min(coverage.values())<90:raise ValueError(f'Calendar month coverage below 90% {coverage}')
    model=json.loads(args.model.read_text())
    for family in core.FAMILIES:
        for i,param in enumerate(core.PARAMETERS[family]):
            c[f'p_{family}_{i}']=core.probabilities(c,family,param,model).astype(np.float32)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.output,**c)
    core.dump(args.output.with_suffix('.json'),{'year':YEAR,'createdAt':datetime.now(timezone.utc).isoformat(),
         'originalCacheSha256':core.digest(args.cache),'priorCacheSha256':core.digest(args.prior),
         'calibrationSha256':core.digest(args.model),'signalCounts':counts,'eligibleSettledRaces':eligible,
         'coveragePercent':coverage,'addedMissingRaces':missing,'training':training,
         'recordSource':record_source,'previewSource':preview_source,'holdoutOpened':False,
         'researchOnly':True,'releaseQualified':False,
         'limitations':['2024 development, not pristine holdout','Archived odds lack verified pre-close timestamp',
                       'Denominator is eligible settled six-boat records; cancelled/refunded races require separate audit',
                       'January model seeds from available 2023 May-September only; no current-year training'],
         'reusedPeriod':'2024-02-01..2024-09-30 values copied exactly'})


def load(path):
    with np.load(path,allow_pickle=False) as z:
        # Explicitly refuses every year other than 2024 before reading outcomes.
        if int(z['year'][0])!=2024:raise ValueError('Only 2024 annual cache allowed')
        if set(z['month'].tolist())!=set(range(1,13)):raise ValueError('Twelve months required')
        if any(date.fromordinal(int(d)).year!=2024 for d in z['day_ordinal']):raise ValueError('Date fence')
        return {k:z[k] for k in z.files}


def evaluate(c,cfg):
    p=c[f"p_{cfg['family']}_{cfg['parameterIndex']}"] .astype(np.float64)
    selected,units,counts=core.tickets(p,c['odds'],cfg)
    winning=(units*(selected==c['actual_index'][:,None])).sum(axis=1)
    stake=np.where(counts>0,1200,0);pay=winning*c['amount']
    total=core.summarize(stake,pay,counts)
    months={str(m):core.summarize(stake[c['month']==m],pay[c['month']==m],counts[c['month']==m]) for m in range(1,13)}
    passed=(total['roi']>=105 and total['purchaseRaces']>=360
            and total['largestHitShare']<=25 and total['roiWithoutLargestHit']>=100)
    return {'config':cfg,'annual2024':total,'months':months,'historicalNumericGatePassed':passed,
            'releaseQualified':False}


def screen(args):
    c=load(args.cache)
    configs=core.configurations(args.family,args.cap)
    rows=[evaluate(c,cfg) for cfg in configs]
    # Verify copied old-period decisions/accounting exactly match successful r1.
    old=json.loads(Path('data/v016_core_audit.json').read_text())
    expected={core.canonical(r['config']):r['years']['2024'] for r in old['allCandidates']}
    mask=np.isin(c['month'],core.MONTHS)
    subset={k:(v[mask] if k not in ('year','combos') else v) for k,v in c.items()}
    for cfg in configs:
        check=evaluate(subset,cfg)['annual2024']
        if check!=expected[core.canonical(cfg)]:raise ValueError('Existing May-September result changed')
    core.dump(args.output,{'year':2024,'family':args.family,'cap':args.cap,
                          'cacheSha256':core.digest(args.cache),'rows':rows,'holdoutOpened':False})


def aggregate(args):
    reports=[json.loads(p.read_text()) for p in sorted(args.input.glob('annual-2024-*.json'))]
    ids=[(r['family'],r['cap']) for r in reports]
    if set(ids)!={(f,o) for f in core.FAMILIES for o in (20,40)} or len(ids)!=6:raise ValueError('Incomplete matrix')
    rows=[row for r in reports for row in r['rows']]
    if len(rows)!=144 or len({core.canonical(r['config']) for r in rows})!=144:raise ValueError('Invalid grid')
    adequate=[r for r in rows if r['annual2024']['purchaseRaces']>=360]
    adequate.sort(key=lambda r:r['annual2024']['roi'],reverse=True)
    passed=[r for r in adequate if r['historicalNumericGatePassed']]
    out={'year':2024,'period':'2024-01-01..2024-12-31','researchOnly':True,'releaseQualified':False,
         'sourceRun':args.run,'candidateCount':144,'adequateVolumeCount':len(adequate),'passCount':len(passed),
         'bestAdequateVolume':adequate[:10],'allCandidates':rows,
         'holdoutPolicy':{'reserved':core.HOLDOUT,'opened':False},
         'status':'CANDIDATE_NEEDS_MULTIPLE_YEARS_AND_TIMING_AUDIT' if passed else 'NO_ANNUAL_2024_CANDIDATE',
         'metadata':json.loads(args.metadata.read_text()),
         'longshotStatus':'NOT_STARTED_CORE_NOT_QUALIFIED'}
    core.dump(args.output,out)
    print(json.dumps({'candidates':144,'adequateVolume':len(adequate),'passed':len(passed),
                     'best':adequate[:1]},ensure_ascii=False))


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['build','screen','aggregate'])
    for name in ('cache','prior','learning','model','input','output','metadata'):p.add_argument('--'+name,type=Path)
    p.add_argument('--family',choices=core.FAMILIES);p.add_argument('--cap',type=int,choices=[20,40]);p.add_argument('--run')
    a=p.parse_args();globals()[a.command](a)
if __name__=='__main__':main()
