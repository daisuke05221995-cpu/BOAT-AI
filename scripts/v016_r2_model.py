#!/usr/bin/env python3
"""Three preregistered conditional choice hypotheses. No 2025 reader."""
import argparse
import itertools
import json
from pathlib import Path
import numpy as np
from v016_core_research import dump, digest, normalize, tickets, summarize, canonical
from v016_r2_features import load, PROTOCOL, FEATURES, GLOBALS

COMBOS=np.asarray(list(itertools.permutations(range(6),3)))
PREFIXES=[np.empty((1,0),int),np.arange(6)[:,None],np.asarray(list(itertools.permutations(range(6),2)))]

def softmax(x):
    x=x-x.max(axis=1,keepdims=True); p=np.exp(x)
    return p/p.sum(axis=1,keepdims=True)

def objective(k):
    def obj(pred,data):
        p=softmax(pred.reshape(-1,k)); y=data.get_label().reshape(-1,k)
        # Positive diagonal bound for the grouped multinomial Hessian.
        return (p-y).ravel(), np.maximum(2*p*(1-p),1e-5).ravel()
    return obj

def metric(k):
    def score(pred,data):
        p=softmax(pred.reshape(-1,k)); y=data.get_label().reshape(-1,k)
        return 'conditional_logloss',float(-np.sum(y*np.log(np.maximum(p,1e-15)))/len(p)),False
    return score

def subset(c,take):
    return {k:v if k in ('year','combos') else v[take] for k,v in c.items()}

def context(c):
    b=c['boat'].astype(np.float32)
    valid=np.isfinite(b); count=valid.sum(axis=1,keepdims=True)
    mean=np.nansum(b,axis=1,keepdims=True)/np.maximum(count,1)
    mean=np.where(count>0,mean,np.nan)
    low=np.min(np.where(valid,b,np.inf),axis=1,keepdims=True)
    high=np.max(np.where(valid,b,-np.inf),axis=1,keepdims=True)
    spread=np.where(count>0,high-low,np.nan)
    raw=np.concatenate([b,b-mean,np.broadcast_to(spread,b.shape),~valid],axis=2).astype(np.float32)
    # Venue is one-hot: wind direction codes are also opaque categories, not angles.
    venue=c['venue'].astype(int)
    glob=np.concatenate([c['global_features'][:,:-2],np.eye(24,dtype=np.float32)[venue-1],
                         c['race_number'][:,None],b[:,0],b[:,0]-mean[:,0]],axis=1)
    market=normalize(c['market_p'])
    cube=np.zeros((len(b),6,6,6),np.float64)
    cube[:,COMBOS[:,0],COMBOS[:,1],COMBOS[:,2]]=market
    first=cube.sum(axis=(2,3)); second=cube.sum(axis=3)
    popularity=np.stack([first[:,0],market.max(axis=1),-(market*np.log(np.maximum(market,1e-15))).sum(axis=1),
                         (market**2).sum(axis=1),np.sort(market,axis=1)[:,-3:].sum(axis=1)],axis=1)
    return {'raw':raw,'b':b,'glob':glob,'cube':cube,'first':first,'second':second,'popularity':popularity}

def rows(ctx,race,prefix,family):
    """Each row is a candidate in a contiguous 6/5/4-choice group.

    Prefixes are labels only during teacher-forced likelihood training. Prediction
    enumerates every possible prefix and never reads actual_index or amount.
    """
    stage=prefix.shape[1]; k=6-stage
    available=np.ones((len(race),6),bool)
    for s in range(stage): available[np.arange(len(race)),prefix[:,s]]=False
    candidate=np.broadcast_to(np.arange(6),available.shape)[available].reshape(-1,k)
    ri=np.repeat(race,k); lane=candidate.ravel()
    pieces=[ctx['raw'][ri,lane],np.eye(6,dtype=np.float32)[lane],ctx['glob'][ri]]
    for s in range(stage):
        selected=np.repeat(prefix[:,s],k)
        pieces.extend([ctx['b'][ri,selected],ctx['b'][ri,lane]-ctx['b'][ri,selected],
                       np.eye(6,dtype=np.float32)[selected]])
    if stage==0:
        prior=ctx['first'][ri,lane]
    elif stage==1:
        f=np.repeat(prefix[:,0],k)
        prior=ctx['second'][ri,f,lane]/np.maximum(ctx['first'][ri,f],1e-15)
    else:
        f=np.repeat(prefix[:,0],k); s=np.repeat(prefix[:,1],k)
        prior=ctx['cube'][ri,f,s,lane]/np.maximum(ctx['second'][ri,f,s],1e-15)
    prior=np.maximum(prior.reshape(-1,k),1e-12); prior=prior/prior.sum(axis=1,keepdims=True)
    base=np.log(prior).ravel() if family!='fundamental' else np.zeros(len(ri))
    if family!='fundamental':
        pieces.extend([base[:,None],ctx['first'][ri,lane,None],ctx['popularity'][ri],
                       (ctx['b'][ri,lane]-ctx['b'][ri,0])])
    x=np.concatenate(pieces,axis=1).astype(np.float32)
    if np.isinf(x).any(): raise ValueError('Infinite model feature')
    return x,base,candidate

def validate_combos(c):
    expect=np.asarray(['-'.join(str(i+1) for i in row) for row in COMBOS])
    if not np.array_equal(c['combos'],expect): raise ValueError('Unexpected combination ordering')

def fit(args):
    import lightgbm as lgb
    proto=json.loads(PROTOCOL.read_text()); c=load(args.cache,2023); validate_combos(c)
    train=subset(c,(c['month']<=7)&c['usable']); valid=subset(c,(c['month']==8)&c['usable'])
    if len(train['month'])<1000 or len(valid['month'])<500: raise ValueError('Insufficient train/validation races')
    contexts=[context(train),context(valid)]; manifest={'family':args.family,'capacity':args.capacity,
       'trainingRaces':len(train['month']),'earlyStoppingRaces':len(valid['month']),
       'protocolSha256':digest(PROTOCOL),'featureCacheSha256':digest(args.cache),
       'featureSchemaSha256':canonical([FEATURES,GLOBALS]),'stages':{},'holdoutOpened':False,
       'codeSha256':digest(__file__),'lightgbmVersion':lgb.__version__}
    args.output.mkdir(parents=True,exist_ok=True)
    for stage in range(3):
        if args.family=='place' and stage==0: continue
        datasets=[]; arrays=[]; k=6-stage
        for part,ctx in zip((train,valid),contexts):
            actual=COMBOS[part['actual_index']]
            x,base,candidate=rows(ctx,np.arange(len(actual)),actual[:,:stage],args.family)
            y=(candidate==actual[:,stage,None]).astype(np.float32).ravel()
            if not np.all(y.reshape(-1,k).sum(axis=1)==1): raise ValueError('Invalid choice label')
            ds=lgb.Dataset(x,label=y,init_score=base,free_raw_data=False,reference=datasets[0] if datasets else None)
            datasets.append(ds); arrays.append((x,base,y))
        params=dict(proto['capacities'][args.capacity],objective=objective(k),metric='None',
                    learning_rate=.03,lambda_l2=20,num_threads=2,seed=1602,
                    deterministic=True,force_col_wise=True,verbosity=-1,feature_pre_filter=False)
        model=lgb.train(params,datasets[0],num_boost_round=400,valid_sets=[datasets[1]],
                        feval=metric(k),callbacks=[lgb.early_stopping(30,verbose=False)])
        x,base,y=arrays[1]
        # init_score is NOT in serialized Booster predictions: add the prior once.
        logits=model.predict(x,raw_score=True,num_threads=2)+base
        loss=metric(k)(logits,datasets[1])[1]
        recorded=float(model.best_score['valid_0']['conditional_logloss'])
        if abs(loss-recorded)>1e-7: raise ValueError('init_score/prediction consistency failure')
        file=args.output/f'stage{stage}.txt'; model.save_model(str(file))
        manifest['stages'][str(stage)]={'iterations':model.best_iteration,'logloss':loss,'sha256':digest(file),
                                      'features':x.shape[1]}
        print(f'{args.family}/{args.capacity} stage={stage} rounds={model.best_iteration} loss={loss:.6f}',flush=True)
    dump(args.output/'manifest.json',manifest)

def predict(c,family,models):
    """Outcomes are intentionally never accessed in this function or context/rows."""
    output=[]
    for start in range(0,len(c['month']),256):
        part=subset(c,slice(start,start+256)); ctx=context(part); n=len(part['month']); q=[]
        for stage in range(3):
            prefixes=PREFIXES[stage]; race=np.repeat(np.arange(n),len(prefixes))
            prefix=np.tile(prefixes,(n,1)); x,base,candidates=rows(ctx,race,prefix,family)
            raw=models[stage].predict(x,raw_score=True,num_threads=2)+base if stage in models else base
            prob=softmax(raw.reshape(-1,6-stage))
            shape=(n,)+(6,)*(stage+1); table=np.zeros(shape,np.float64)
            ix=[np.repeat(race,6-stage)]
            ix.extend(np.repeat(prefix[:,s],6-stage) for s in range(stage)); ix.append(candidates.ravel())
            table[tuple(ix)]=prob.ravel(); q.append(table)
        p=q[0][:,COMBOS[:,0]]*q[1][:,COMBOS[:,0],COMBOS[:,1]]*q[2][:,COMBOS[:,0],COMBOS[:,1],COMBOS[:,2]]
        if not np.allclose(p.sum(axis=1),1,atol=1e-8) or not np.isfinite(p).all(): raise ValueError('Invalid chain probability')
        output.append(p.astype(np.float32))
    return np.concatenate(output)

def evaluate(args):
    import lightgbm as lgb
    proto=json.loads(PROTOCOL.read_text()); manifest=json.loads((args.model/'manifest.json').read_text())
    if manifest['protocolSha256']!=digest(PROTOCOL) or manifest['codeSha256']!=digest(__file__):
        raise ValueError('Frozen training protocol/code changed')
    c=load(args.cache,args.year); validate_combos(c)
    if args.year==2023: c=subset(c,c['month']==9)
    order=np.lexsort((c['race_number'],c['venue'],c['day_ordinal'])); c=subset(c,order)
    models={}
    for stage,meta in manifest['stages'].items():
        path=args.model/f'stage{stage}.txt'
        if digest(path)!=meta['sha256']: raise ValueError('Model checksum mismatch')
        models[int(stage)]=lgb.Booster(model_file=str(path))
    p=predict(c,manifest['family'],models); p[~c['usable']]=0
    chosen,units,counts=tickets(p,c['odds'],proto['fixedPolicy'])
    wins=(units*(chosen==c['actual_index'][:,None])).sum(axis=1)
    stake=np.where(counts>0,1200,0); payout=wins*c['amount']
    total=summarize(stake,payout,counts)
    months={str(m):summarize(stake[c['month']==m],payout[c['month']==m],counts[c['month']==m]) for m in np.unique(c['month'])}
    good=c['usable']; actual=c['actual_index'][good]; market=normalize(c['market_p'][good]); pp=p[good]
    metrics={'modelLogloss':float(-np.log(np.maximum(pp[np.arange(len(pp)),actual],1e-15)).mean()),
             'marketLogloss':float(-np.log(np.maximum(market[np.arange(len(pp)),actual],1e-15)).mean()),
             'modelBrier':float((np.square(pp).sum(axis=1)-2*pp[np.arange(len(pp)),actual]+1).mean()),
             'usableRaces':int(good.sum()),'allRaces':len(good)}
    gates=proto['annualGate']; reasons=[]
    for key,limit in [('roi',105),('purchaseRaces',360),('hits',30),('roiWithoutLargestHit',100)]:
        if total[key]<limit: reasons.append(f'{key} < {limit}')
    if total['largestHitShare']>25: reasons.append('largestHitShare > 25')
    if set(months)!=set(map(str,range(1,13))): reasons.append('not a complete calendar year')
    out={'modelId':manifest['family']+'-'+manifest['capacity'],'year':args.year,'total':total,'months':months,
         'predictionMetrics':metrics,'annualPass':args.year==2024 and not reasons,'rejectionReasons':reasons,
         'manifest':manifest,'modelManifestSha256':digest(args.model/'manifest.json'),
         'evaluationCacheSha256':digest(args.cache),'fixedPolicy':proto['fixedPolicy'],
         'holdoutOpened':False,'releaseQualified':False}
    dump(args.output,out); print(json.dumps({k:out[k] for k in ('modelId','year','total','annualPass')},ensure_ascii=False))
    np.savez_compressed(args.output.with_suffix('.npz'),p=p,day_ordinal=c['day_ordinal'],venue=c['venue'],race_number=c['race_number'])

def aggregate(args):
    results=[json.loads(p.read_text()) for p in sorted(args.input.glob('result-*.json'))]
    proto=json.loads(PROTOCOL.read_text()); expected={(f+'-'+s,y) for f in proto['families'] for s in proto['capacities'] for y in (2023,2024)}
    if len(results)!=len(expected) or {(r['modelId'],r['year']) for r in results}!=expected:
        raise ValueError('Missing or duplicate model/year results')
    annual=[r for r in results if r['year']==2024]
    passed=sorted([r for r in annual if r['annualPass']],key=lambda r:(-r['total']['roiWithoutLargestHit'],-r['total']['purchaseRaces'],r['modelId']))
    candidate=None
    if passed:
        r=passed[0]; candidate={'modelId':r['modelId'],'modelManifestSha256':r['modelManifestSha256'],
                              'manifest':r['manifest'],'fixedPolicy':proto['fixedPolicy'],'frozenBefore2025':True}
    out={'runId':args.run,'protocolSha256':digest(PROTOCOL),'results':results,'candidate':candidate,
         'decision':'candidate_for_independent_pre_Q4_2025_confirmation' if candidate else 'reject_all_six_r2_models',
         'holdoutOpened':False,'releaseQualified':False,'longshotStarted':False,
         'limitations':proto['limitations']}
    dump(args.output,out)
    lines=['# v0.16 CORE r2 結果','',f'Run: {args.run}', '',
           '| モデル | 2024 ROI | 購入レース | 的中 | 最大的中除外ROI | 年次ゲート |',
           '|---|---:|---:|---:|---:|---|']
    for r in annual:
        t=r['total']; lines.append(f"| {r['modelId']} | {t['roi']:.2f}% | {t['purchaseRaces']} | {t['hits']} | {t['roiWithoutLargestHit']:.2f}% | {'合格候補' if r['annualPass'] else '不採用'} |")
    lines+=['','2023年5〜7月学習・8月早期停止・9月screen。2024年は既に探索済みの開発年。',
            '2023のscreenは独立した通年検証ではない。2025は未参照、Q4封印、本番未変更。',
            'オッズ取得時刻未検証。合格候補でも本番採用・収益再現性の証明ではない。',
            '', '次: '+('固定候補だけを2025 Q4前で独立確認する。' if candidate else '6モデルを不採用として記録。閾値の再調整はしない。')]
    args.output.with_suffix('.md').write_text('\n'.join(lines)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='command',required=True)
    t=sub.add_parser('fit'); t.add_argument('--cache',type=Path,required=True)
    t.add_argument('--family',choices=['fundamental','residual','place'],required=True)
    t.add_argument('--capacity',choices=['small','medium'],required=True); t.add_argument('--output',type=Path,required=True)
    e=sub.add_parser('evaluate'); e.add_argument('--cache',type=Path,required=True); e.add_argument('--year',type=int,required=True)
    e.add_argument('--model',type=Path,required=True); e.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('aggregate'); a.add_argument('--input',type=Path,required=True); a.add_argument('--output',type=Path,required=True)
    a.add_argument('--run',required=True)
    args=p.parse_args(); {'fit':fit,'evaluate':evaluate,'aggregate':aggregate}[args.command](args)
