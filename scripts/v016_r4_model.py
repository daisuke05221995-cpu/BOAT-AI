#!/usr/bin/env python3
"""r4 ablations, identical learner; no racer ID, odds or outcomes in prediction inputs."""
import argparse
import json
from pathlib import Path
import numpy as np
from v016_core_research import dump, digest, canonical, normalize
from v016_r4_features import ROOT, PROTOCOL, COMBOS, read_cache, subset, frozen_lock
from v016_r2_model import context, rows, objective, metric, predict

CODE_FILES=['scripts/v016_r4_features.py','scripts/v016_r4_player_history.py','scripts/v016_r4_model.py',
            'scripts/v016_r4_evaluate.py','scripts/v016_r2_model.py','scripts/v016_r2_features.py','scripts/v016_core_research.py']

def code_hashes(): return {name:digest(ROOT/name) for name in CODE_FILES}

def inputs(c,variant):
    if variant not in ('current','history','reaction'): raise ValueError('Unregistered model variant')
    pieces=[c['current']]
    if variant in ('history','reaction'): pieces.append(c['history'])
    if variant=='reaction': pieces.append(c['reaction'])
    glob=c['global_features']
    if variant=='reaction':
        r=c['reaction']; weak=np.maximum(r[:,0,1],0)+np.maximum(r[:,0,3],0)
        strong=((r[:,1:,1]<=-.5)|(r[:,1:,3]<=-.5)).sum(axis=1)
        glob=np.concatenate([glob[:,:-2],weak[:,None],strong[:,None],glob[:,-2:]],axis=1)
    out={k:c[k] for k in ['year','combos','month','day_ordinal','venue','race_number']}
    out['boat']=np.concatenate(pieces,axis=2); out['global_features']=glob
    # The generic probability engine receives an artificial uniform placeholder.
    # No real odds/market array is ever read by this outcome-model adapter.
    out['market_p']=np.full((len(c['month']),120),1/120,np.float32)
    return out

def calibrated(p,temperature):
    return normalize(np.maximum(p,1e-15).astype(np.float64)**(1/temperature))

def quality(p,actual):
    ix=np.arange(len(p)); top=p.argmax(axis=1); confidence=p[ix,top]; win=top==actual
    bins=[]; ece=0.
    for low,high in zip([0,.05,.1,.2,.3,.4,.5],[.05,.1,.2,.3,.4,.5,1.00001]):
        mask=(confidence>=low)&(confidence<high); n=int(mask.sum())
        predicted=float(confidence[mask].mean()) if n else None; observed=float(win[mask].mean()) if n else None
        if n: ece+=n/len(p)*abs(predicted-observed)
        bins.append({'from':low,'to':min(high,1.),'races':n,'predicted':predicted,'observed':observed})
    return {'races':len(p),'logloss':float(-np.log(np.maximum(p[ix,actual],1e-15)).mean()),
            'brier':float((np.square(p).sum(axis=1)-2*p[ix,actual]+1).mean()),
            'topChoiceEce':float(ece),'calibration':bins}

def fit(args):
    import lightgbm as lgb
    c=read_cache(args.cache)
    if set(c['year'])!={2025} or set(c['month'])!=set(range(1,7)): raise ValueError('Train file must be Jan-Jun 2025 only')
    if np.any(c['history_through']>=c['day_ordinal']): raise ValueError('History leak')
    train=subset(c,(c['month']<=5)&c['usable']); valid=subset(c,(c['month']==6)&c['usable'])
    if len(train['month'])<1000 or len(valid['month'])<500: raise ValueError('Insufficient fit data')
    if max(train['day_ordinal'])>=min(valid['day_ordinal']): raise ValueError('Temporal split violation')
    contexts=[context(inputs(x,args.variant)) for x in (train,valid)]
    args.output.mkdir(parents=True,exist_ok=True); models={}; stages={}
    for stage in range(3):
        ds=[]; xs=[]; k=6-stage
        for part,ctx in zip((train,valid),contexts):
            actual=COMBOS[part['actual_index']]; x,base,candidates=rows(ctx,np.arange(len(actual)),actual[:,:stage],'fundamental')
            if np.any(base!=0): raise ValueError('Market offset in outcome learner')
            y=(candidates==actual[:,stage,None]).astype(np.float32).ravel()
            ds.append(lgb.Dataset(x,label=y,free_raw_data=False,reference=ds[0] if ds else None)); xs.append(x)
        params=dict(objective=objective(k),metric='None',num_leaves=15,max_depth=4,min_data_in_leaf=300,
                    learning_rate=.03,lambda_l2=20,num_threads=2,seed=1604,deterministic=True,
                    force_col_wise=True,verbosity=-1,feature_pre_filter=False)
        model=lgb.train(params,ds[0],num_boost_round=500,valid_sets=[ds[1]],feval=metric(k),
                        callbacks=[lgb.early_stopping(30,verbose=False)])
        loss=metric(k)(model.predict(xs[1],raw_score=True,num_threads=2),ds[1])[1]
        if abs(loss-model.best_score['valid_0']['conditional_logloss'])>1e-7: raise ValueError('Training/prediction mismatch')
        path=args.output/f'stage{stage}.txt'; model.save_model(str(path)); models[stage]=model
        stages[str(stage)]={'sha256':digest(path),'iterations':model.best_iteration,'features':xs[1].shape[1],'validationLogloss':loss}
        print(f'{args.variant} stage {stage}, rounds {model.best_iteration}, loss {loss:.6f}',flush=True)
    pv=predict(inputs(valid,args.variant),'fundamental',models)
    losses={str(t):quality(calibrated(pv,t),valid['actual_index'])['logloss'] for t in (.8,1.,1.2,1.5,2.)}
    temp=min(losses,key=lambda t:(losses[t],float(t)))
    manifest={'variant':args.variant,'trainRaces':len(train['month']),'validationRaces':len(valid['month']),
              'trainEndOrdinal':int(max(train['day_ordinal'])),'validationEndOrdinal':int(max(valid['day_ordinal'])),
              'temperature':float(temp),'temperatureValidationLoss':losses,'stages':stages,
              'schemaSha256':canonical([c[k].tolist() for k in ['boat_names','history_names','reaction_names']]),
              'protocolSha256':digest(PROTOCOL),'codeSha256':code_hashes(),'trainCacheSha256':digest(args.cache),
              'holdoutOpened':False,'septemberOpened':False,'racerIdInModel':False,'marketInOutcomeModel':False}
    dump(args.output/'manifest.json',manifest)

def infer(args):
    import lightgbm as lgb
    lock=frozen_lock(args.lock) if args.lock else None
    manifest=json.loads((args.model/'manifest.json').read_text())
    if lock and digest(args.model/'manifest.json')!=lock['candidate']['modelManifestSha256']: raise ValueError('Frozen model changed')
    if manifest['codeSha256']!=code_hashes() or manifest['protocolSha256']!=digest(PROTOCOL): raise ValueError('Model code/protocol changed')
    c=read_cache(args.cache,bool(lock)); months={9} if lock else {7,8}
    if set(c['year'])!={2025} or set(c['month'])!=months: raise ValueError('Wrong inference period')
    if manifest['validationEndOrdinal']>=min(c['day_ordinal']): raise ValueError('Fit reaches inference period')
    schema=canonical([c[k].tolist() for k in ['boat_names','history_names','reaction_names']])
    if schema!=manifest['schemaSha256']: raise ValueError('Feature schema drift')
    models={}
    for stage,meta in manifest['stages'].items():
        path=args.model/f'stage{stage}.txt'
        if digest(path)!=meta['sha256']: raise ValueError('Tree checksum mismatch')
        models[int(stage)]=lgb.Booster(model_file=str(path))
    p=calibrated(predict(inputs(c,manifest['variant']),'fundamental',models),manifest['temperature']).astype(np.float32)
    good=c['usable']&c['odds_usable']; actual=c['actual_index'][good]
    market=normalize(1/c['odds'][good]); stats=quality(p[good],actual); market_stats=quality(market,actual)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(args.output,p=p,day_ordinal=c['day_ordinal'],venue=c['venue'],race_number=c['race_number'])
    dump(args.output.with_suffix('.json'),{'variant':manifest['variant'],'modelManifestSha256':digest(args.model/'manifest.json'),
         'featureCacheSha256':digest(args.cache),'model':stats,'market':market_stats,'manifest':manifest,
         'months':{str(m):quality(p[good&(c['month']==m)],c['actual_index'][good&(c['month']==m)]) for m in sorted(months)},
         'holdoutOpened':False,'septemberOpened':bool(lock)})
    print(json.dumps({'variant':manifest['variant'],'modelLogloss':stats['logloss'],'marketLogloss':market_stats['logloss'],'temperature':manifest['temperature']}))

if __name__=='__main__':
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='command',required=True)
    f=s.add_parser('fit'); f.add_argument('--cache',type=Path,required=True); f.add_argument('--variant',choices=['current','history','reaction'],required=True); f.add_argument('--output',type=Path,required=True)
    i=s.add_parser('infer'); i.add_argument('--cache',type=Path,required=True); i.add_argument('--model',type=Path,required=True)
    i.add_argument('--lock',type=Path); i.add_argument('--output',type=Path,required=True)
    args=p.parse_args(); {'fit':fit,'infer':infer}[args.command](args)
