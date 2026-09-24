#!/usr/bin/env python3
"""Final preregistered 2025 Q4 forecast-only holdout for frozen Model A."""
from __future__ import annotations

import argparse, hashlib, json, subprocess, time, urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path
import numpy as np

from v016_core_research import canonical, digest, dump
from v016_r4_features import COMBOS, COMBO_TEXT, extract_pre
from v016_r4_player_history import PlayerHistory, enrich
from v016_r4_model import code_hashes, inputs, calibrated
from v016_r2_model import predict
from v016_sept_forecast_holdout import baseline_prob, score

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'data/v016_q4_forecast_protocol.json'
CANDIDATE=ROOT/'data/v016_forecast_candidate.json'
PRECOMMIT='3a56378244dd1f3621f862ac89cea3db8ccea6af'
SEPT_START,SEPT_END=date(2025,9,1),date(2025,9,30)
START,END=date(2025,10,1),date(2025,12,31)
SOURCE={'programs':('BoatraceOpenAPI/programs','d3e37a2b5bce2bc10ac9d8154713cfe250aa5fa1'),
        'previews':('BoatraceOpenAPI/previews','5089ce91e150538a8adc8da86ca403f578343318'),
        'results':('BoatraceOpenAPI/results','04dfd55682c1f083963ca80b5bfce93ed43cb755')}


def preregistration():
    raw=subprocess.check_output(['git','-C',str(ROOT),'show',PRECOMMIT+':data/v016_q4_forecast_protocol.json'])
    if hashlib.sha256(raw).hexdigest()!=digest(PROTOCOL): raise ValueError('Q4 preregistered protocol changed')
    subprocess.run(['git','-C',str(ROOT),'merge-base','--is-ancestor',PRECOMMIT,'HEAD'],check=True)
    p=json.loads(raw)
    assert p['period']['holdoutStart']==START.isoformat() and p['period']['holdoutEnd']==END.isoformat()
    assert p['scope']['marketInputs'] is False and p['scope']['oddsAcquisition'] is False
    assert p['scope']['retraining'] is False and p['scope']['postHoldoutRescue'] is False
    return p


def allowed(day,warmup=False):
    if warmup:
        if not SEPT_START<=day<=SEPT_END: raise ValueError('Warmup date outside already-opened September')
    elif not START<=day<=END:
        raise ValueError('Q4 fetch date outside preregistered holdout')


def source_url(day,kind,warmup=False):
    allowed(day,warmup)
    if kind not in SOURCE: raise ValueError('Only programs/previews/results allowed')
    repo,sha=SOURCE[kind]
    return f'https://raw.githubusercontent.com/{repo}/{sha}/docs/v3/2025/{day:%Y%m%d}.json'


def read_day(day,warmup=False):
    out={}; hashes={}
    for kind in SOURCE:
        url=source_url(day,kind,warmup)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BOAT-AI-v016-q4-final'}),timeout=45) as r: raw=r.read()
                records=json.loads(raw)[kind]; keyed={}
                for row in records:
                    if row.get('date')!=day.isoformat(): raise ValueError('Source date mismatch')
                    key=(int(row['stadium_number']),int(row['number']))
                    if key in keyed: raise ValueError('Duplicate source race')
                    if kind=='results':
                        keyed[key]={'date':row['date'],'stadium_number':row['stadium_number'],'number':row['number'],
                                    'boats':[{k:b.get(k) for k in ('racer_boat_number','racer_number','racer_place_number')} for b in row.get('boats',[])]}
                    else: keyed[key]=row
                out[kind]=keyed; hashes[kind]=hashlib.sha256(raw).hexdigest(); break
            except ValueError: raise
            except Exception:
                if attempt==2: raise
                time.sleep(attempt+1)
    return out,hashes


def finish_index(program,result):
    if not result:return None
    pb={b['racer_boat_number']:b for b in program.get('boats',[])}; rb={b['racer_boat_number']:b for b in result.get('boats',[])}
    if len(pb)!=6 or len(rb)!=6 or set(pb)!=set(range(1,7)) or set(rb)!=set(pb): return None
    places=[rb[i].get('racer_place_number') for i in range(1,7)]
    if set(places)!=set(range(1,7)): return None
    if any(rb[i].get('racer_number')!=pb[i].get('racer_number') for i in range(1,7)): raise ValueError('Settled racer ID mismatch')
    order=tuple(places.index(i) for i in (1,2,3)); ix=np.flatnonzero(np.all(COMBOS==order,axis=1))
    if len(ix)!=1: raise ValueError('Nonunique finish combo')
    return int(ix[0])


def fetch_period(start,end,warmup=False):
    days=[start+timedelta(days=i) for i in range((end-start).days+1)]
    rows=[]; hashes={}; counts=Counter()
    with ThreadPoolExecutor(max_workers=10) as pool:
        tasks={pool.submit(read_day,d,warmup):d for d in days}
        for task in as_completed(tasks):
            day=tasks[task]; src,hs=task.result(); hashes[day.isoformat()]=hs; counts['sourceRaces']+=len(src['programs'])
            counts['resultWithoutProgram']+=len(set(src['results'])-set(src['programs']))
            for venue,race in sorted(src['programs']):
                program=src['programs'][venue,race]; label=finish_index(program,src['results'].get((venue,race)))
                if label is None: counts['notSixBoatUniqueFinish']+=1; continue
                counts['eligibleSettled']+=1
                b,g,ids,classes,usable=extract_pre(program,src['previews'].get((venue,race)),day,venue,race)
                if not usable: counts['modelMissingRequiredInput']+=1
                rows.append((day.toordinal(),day.month,venue,race,label,b,g,ids,classes,usable))
    if len(hashes)!=len(days) or sorted(hashes)!=[d.isoformat() for d in days]: raise ValueError('Incomplete source days')
    if counts['sourceRaces']!=counts['eligibleSettled']+counts['notSixBoatUniqueFinish']: raise ValueError('Population partition mismatch')
    rows.sort(key=lambda x:(x[0],x[2],x[3]))
    names=('day_ordinal','month','venue','race_number','actual_index','current','global_features','racer_id','racer_class','usable')
    c={name:np.asarray([r[i] for r in rows]) for i,name in enumerate(names)}
    c['year']=np.asarray([2025]); c['combos']=COMBO_TEXT
    keys=np.stack([c[k].astype(np.int64) for k in ('day_ordinal','venue','race_number')],axis=1)
    if len(np.unique(keys,axis=0))!=len(keys): raise ValueError('Duplicate race keys')
    return c,hashes,dict(counts)


def model_predictions(c,model_dir,proto):
    candidate=json.loads(CANDIDATE.read_text()); manifest=json.loads((model_dir/'manifest.json').read_text())
    if candidate['modelArtifactDigest']!=proto['candidate']['modelArtifactDigest'] or candidate['temperature']!=1.0: raise ValueError('Candidate changed')
    if digest(model_dir/'manifest.json')!=proto['candidate']['modelManifestSha256']: raise ValueError('Manifest SHA mismatch')
    if manifest['variant']!='reaction' or manifest['temperature']!=1.0 or manifest['marketInOutcomeModel'] or manifest['racerIdInModel']: raise ValueError('Model not frozen market-free reaction candidate')
    if manifest['codeSha256']!=code_hashes() or manifest['protocolSha256']!=candidate['protocolSha256']: raise ValueError('Frozen model code/protocol drift')
    schema=canonical([c[k].tolist() for k in ('boat_names','history_names','reaction_names')])
    if schema!=proto['candidate']['featureSchemaSha256'] or schema!=manifest['schemaSha256']: raise ValueError('Feature schema drift')
    import lightgbm as lgb
    models={}
    for stage in range(3):
        path=model_dir/f'stage{stage}.txt'; expected=proto['candidate']['modelFileSha256'][path.name]
        if digest(path)!=expected or digest(path)!=manifest['stages'][str(stage)]['sha256']: raise ValueError('Tree SHA mismatch')
        models[stage]=lgb.Booster(model_file=str(path))
    q=calibrated(predict(inputs(c,'reaction'),'fundamental',models),1.0)
    if q.shape!=(len(c['month']),120) or not np.isfinite(q).all() or np.any(q<0) or not np.allclose(q.sum(axis=1),1,atol=1e-5): raise ValueError('Invalid Model A probabilities')
    return q


def paired_bootstrap(days,mp,bp,labels,settings):
    idx=np.arange(len(labels)); ml=-np.log(np.maximum(mp[idx,labels],1e-15)); bl=-np.log(np.maximum(bp[idx,labels],1e-15))
    mb=np.square(mp).sum(axis=1)-2*mp[idx,labels]+1; bb=np.square(bp).sum(axis=1)-2*bp[idx,labels]+1
    unique=np.unique(days); expected=settings['drawDaysPerReplicate']
    if len(unique)!=expected: raise ValueError(f'Expected {expected} calendar-day blocks, got {len(unique)}')
    nday=np.asarray([(days==d).sum() for d in unique]); vals=(ml-bl,mb-bb)
    totals=np.asarray([[v[days==d].sum() for d in unique] for v in vals]); rng=np.random.default_rng(settings['seed'])
    draw=rng.integers(0,len(unique),size=(settings['replicates'],expected)); den=nday[draw].sum(axis=1)
    names=('trifectaLogloss','trifectaBrier')
    return {names[i]:{'point':float(v.mean()),'ci95':np.percentile(totals[i][draw].sum(axis=1)/den,[2.5,97.5]).tolist()} for i,v in enumerate(vals)}


def run(args):
    proto=preregistration()
    if digest(args.state)!=proto['candidate']['historySeedSha256']: raise ValueError('August history seed SHA mismatch')
    if digest(ROOT/proto['baseline']['sourcePath'])!=proto['baseline']['sourceSha256'] or digest(ROOT/proto['baseline']['replayReferencePath'])!=proto['baseline']['replayReferenceSha256']: raise ValueError('Baseline drift')
    history=PlayerHistory(json.loads(args.state.read_text()))
    if history.state['lastDay']!=date(2025,8,31).toordinal(): raise ValueError('History seed not through Aug 31')

    sep,sep_hashes,sep_counts=fetch_period(SEPT_START,SEPT_END,True)
    enrich(sep,history)
    if history.state['lastDay']!=SEPT_END.toordinal(): raise ValueError('September history warmup incomplete')

    raw,q4_hashes,counts=fetch_period(START,END,False)
    enriched=enrich(raw,history)
    if set(enriched['month'].astype(int))!={10,11,12}: raise ValueError('Q4 month fence failed')
    if int((enriched['history_through']>=enriched['day_ordinal']).sum())!=0: raise ValueError('Same-day history leak')
    take=enriched['usable'].astype(bool); c={k:(v[take] if isinstance(v,np.ndarray) and len(v)==len(take) else v) for k,v in enriched.items()}
    labels=enriched['actual_index'][take].astype(int); days=enriched['day_ordinal'][take].astype(int)
    venues=enriched['venue'][take].astype(int)
    mp=model_predictions(c,args.model,proto); bp=baseline_prob({'current':c['current']})
    if mp.shape!=bp.shape or mp.shape!=(len(labels),120): raise ValueError('Unpaired prediction population')
    mm,bm=score(mp,labels),score(bp,labels); boot=paired_bootstrap(days,mp,bp,labels,proto['evaluation']['bootstrap'])
    eligible=counts.get('eligibleSettled',0); coverage=len(labels)/eligible if eligible else 0.0
    issues=[]
    if len(q4_hashes)!=92 or coverage<proto['population']['coverageMinimumOfEligible']: issues.append('source/coverage guard failed')
    if len(np.unique(np.stack([days,venues,enriched['race_number'][take].astype(int)],axis=1),axis=0))!=len(labels): issues.append('duplicate comparison key')
    if days.min()!=START.toordinal() or days.max()!=END.toordinal(): issues.append('comparison date boundary mismatch')
    primary=mm['trifectaLogloss']<bm['trifectaLogloss'] and boot['trifectaLogloss']['ci95'][1]<0 and mm['trifectaBrier']<bm['trifectaBrier']
    safety=mm['firstTop1']>=bm['firstTop1'] and mm['trifectaTop4']>=bm['trifectaTop4']
    decision='INCONCLUSIVE_Q4_FINAL_FORECAST' if issues else ('PASS_Q4_FINAL_FORECAST' if primary and safety else 'FAIL_Q4_FINAL_FORECAST')
    months={}
    for month in (10,11,12):
        m=enriched['month'][take].astype(int)==month
        months[str(month)]={'races':int(m.sum()),'model':score(mp[m],labels[m]),'baseline':score(bp[m],labels[m])}
    out={'decision':decision,'protocolCommitSha':PRECOMMIT,'protocolSha256':digest(PROTOCOL),'comparisonRaces':len(labels),'coverage':coverage,
         'population':counts,'modelMetrics':mm,'baselineMetrics':bm,'pairedDayBlockBootstrap95':boot,'primaryPass':bool(primary),'secondarySafetyPass':bool(safety),
         'validityIssues':issues,'months':months,'sourceDays':len(q4_hashes),'sameDayHistoryLeakRows':0,'duplicateRaceKeys':0,
         'historyWarmupThrough':SEPT_END.isoformat(),'historyEndThrough':END.isoformat(),'historyUpdateRacesEnd':history.state['updateRaces'],
         'modelRunId':proto['candidate']['modelRunId'],'modelArtifactId':proto['candidate']['modelArtifactId'],'modelArtifactDigest':proto['candidate']['modelArtifactDigest'],
         'marketInputs':False,'oddsRead':False,'payoutRead':False,'q4Opened':True,'autoBuyPromotion':False,'productionPromotion':False,
         'sourceHashes':q4_hashes,'septemberWarmupSourceHashes':sep_hashes,'septemberWarmupPopulation':sep_counts}
    args.output.mkdir(parents=True,exist_ok=True)
    dump(args.output/'v016_q4_forecast_result.json',out); dump(args.output/'v016_q4_forecast_decision.json',{k:v for k,v in out.items() if k not in ('sourceHashes','septemberWarmupSourceHashes')})
    audit={'protocolCommitSha':PRECOMMIT,'sourceDays':len(q4_hashes),'population':counts,'comparisonRaces':len(labels),'coverage':coverage,
           'sameDayHistoryLeakRows':0,'duplicateRaceKeys':0,'oddsRead':False,'payoutRead':False,'historyWarmupThrough':SEPT_END.isoformat(),'historyEndThrough':END.isoformat()}
    dump(args.output/'v016_q4_forecast_data_audit.json',audit); dump(args.output/'history_state_2025-12-31.json',history.state)
    pct=lambda x:f'{x*100:.3f}%'
    lines=['# v0.16 Model A 2025 Q4 final forecast holdout','',f'- Protocol: `{PRECOMMIT}` (committed before Q4 access).',f'- Decision: **{decision}**.',
           f'- Comparison races: {len(labels):,}; coverage {pct(coverage)}; same-day leak 0; duplicate keys 0.',
           '', '## Frozen Model A vs v0.15.16 baseline',
           f"- LogLoss: {mm['trifectaLogloss']:.6f} vs {bm['trifectaLogloss']:.6f}",f"- Brier: {mm['trifectaBrier']:.6f} vs {bm['trifectaBrier']:.6f}",
           f"- First Top1: {pct(mm['firstTop1'])} vs {pct(bm['firstTop1'])}",f"- First Top2: {pct(mm['firstTop2'])} vs {pct(bm['firstTop2'])}",
           f"- Trifecta Top1: {pct(mm['trifectaTop1'])} vs {pct(bm['trifectaTop1'])}",f"- Trifecta Top4: {pct(mm['trifectaTop4'])} vs {pct(bm['trifectaTop4'])}",f"- Trifecta Top8: {pct(mm['trifectaTop8'])} vs {pct(bm['trifectaTop8'])}",
           '',f"- Paired day-block LogLoss delta 95% CI: {boot['trifectaLogloss']['ci95']}",f"- Primary pass: {primary}; secondary safety: {safety}.",
           '', '- Forecast-only. Odds/payout/ROI/BUY were not read or evaluated. Automatic BUY remains OFF.']
    (args.output/'v016_q4_forecast_report.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'decision':decision,'races':len(labels),'coverage':coverage,'model':mm,'baseline':bm,'bootstrap':boot},ensure_ascii=False))
    if decision!='PASS_Q4_FINAL_FORECAST': raise SystemExit(2)


if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--state',type=Path,required=True); ap.add_argument('--model',type=Path,required=True); ap.add_argument('--output',type=Path,required=True)
    run(ap.parse_args())
