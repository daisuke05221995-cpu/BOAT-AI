#!/usr/bin/env python3
"""Preregistered forward OOF study. September and Q4 have no reader."""
import argparse
import json
from datetime import date
from pathlib import Path
import numpy as np
from v016_core_research import digest, dump, normalize, tickets, summarize, canonical
from v016_r4_features import read_cache, subset, COMBOS
from v016_r4_model import inputs, calibrated, quality, code_hashes
from v016_r2_model import context, rows, objective, metric, predict

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'data/v016_oof_protocol.json'
SPLIT=ROOT/'data/v016_oof_split_manifest.json'
PROTOCOL_COMMIT='5a9b333eeae78e2d100f0ca69251bec98e223c6a'
CANDIDATES=('raw_ratio','log_residual_half','logistic_residual')

def rules():
    p=json.loads(PROTOCOL.read_text()); m=json.loads(SPLIT.read_text())
    if m['protocolCommitSha']!=PROTOCOL_COMMIT or len(m['folds'])!=4:
        raise ValueError('Preregistration changed')
    for fold in m['folds']:
        if not (fold['fitEnd']<fold['validationStart']<=fold['validationEnd']<fold['predictionStart']<=fold['predictionEnd']<'2025-07-01'):
            raise ValueError('Forward fold violation')
    return p,m

def checked(path, phase):
    # All supported inputs are explicitly identified, and no September/Q4 path is accepted.
    c=read_cache(path)
    lo=min(c['day_ordinal']); hi=max(c['day_ordinal'])
    span={'oof':(date(2025,1,1),date(2025,6,30)),
          'development':(date(2025,7,1),date(2025,8,31))}[phase]
    if lo<span[0].toordinal() or hi>span[1].toordinal() or set(c['year'])!={2025}:
        raise ValueError('Prohibited cache date')
    if np.any(c['history_through']>=c['day_ordinal']): raise ValueError('History timestamp leakage')
    return c

def keys(c):
    k=np.stack((c['day_ordinal'],c['venue'],c['race_number']),axis=1)
    if len(np.unique(k,axis=0))!=len(k): raise ValueError('Duplicate race key')
    return k

def audit_p(p):
    if p.ndim!=2 or p.shape[1]!=120 or not np.isfinite(p).all() or (p<0).any() or not np.allclose(p.sum(axis=1),1,atol=1e-6):
        raise ValueError('Invalid 120-way probability')
    first=np.stack([p[:,COMBOS[:,0]==i].sum(axis=1) for i in range(6)],axis=1)
    if first.shape!=(len(p),6) or not np.allclose(first.sum(axis=1),1,atol=1e-6): raise ValueError('First-place marginal invalid')
    return first

def save_predictions(path,c,p,meta):
    first=audit_p(p); keys(c); path.parent.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(path,p=p.astype(np.float32),first=first.astype(np.float32),
                        day_ordinal=c['day_ordinal'],venue=c['venue'],race_number=c['race_number'])
    meta.update(predictionSha256=digest(path),protocolSha256=digest(PROTOCOL),protocolCommitSha=PROTOCOL_COMMIT,
                splitManifestSha256=digest(SPLIT),septemberOpened=False,q4Opened=False)
    dump(path.with_suffix('.json'),meta)

def load_predictions(path,c):
    with np.load(path,allow_pickle=False) as z:
        for k in ('day_ordinal','venue','race_number'):
            if not np.array_equal(z[k],c[k]): raise ValueError('Prediction alignment: '+k)
        p=z['p'].astype(np.float64)
        if not np.allclose(z['first'],audit_p(p),atol=1e-6): raise ValueError('First marginal mismatch')
    meta=json.loads(path.with_suffix('.json').read_text())
    if meta['protocolCommitSha']!=PROTOCOL_COMMIT or meta['protocolSha256']!=digest(PROTOCOL) or meta['predictionSha256']!=digest(path):
        raise ValueError('Prediction manifest mismatch')
    return p,meta

def fit_fold(args):
    import lightgbm as lgb
    _,m=rules(); fold=next(x for x in m['folds'] if x['id']==args.fold)
    c=checked(args.cache,'oof'); keys(c)
    day=c['day_ordinal']; valid=(day>=date.fromisoformat(fold['validationStart']).toordinal())&(day<=date.fromisoformat(fold['validationEnd']).toordinal())&c['usable']
    train=(day<=date.fromisoformat(fold['fitEnd']).toordinal())&c['usable']
    target=(day>=date.fromisoformat(fold['predictionStart']).toordinal())&(day<=date.fromisoformat(fold['predictionEnd']).toordinal())
    a,b,d=(subset(c,t) for t in (train,valid,target))
    if min(len(a['month']),len(b['month']),len(d['month']))<500 or not (max(a['day_ordinal'])<min(b['day_ordinal']) and max(b['day_ordinal'])<min(d['day_ordinal'])):
        raise ValueError('Insufficient or nonforward fold')
    models={}; stages={}; contexts=[context(inputs(x,'reaction')) for x in (a,b)]
    args.output.mkdir(parents=True,exist_ok=True)
    for stage in range(3):
        k=6-stage; ds=[]; xs=[]
        for part,ctx in zip((a,b),contexts):
            actual=COMBOS[part['actual_index']]
            x,base,candidates=rows(ctx,np.arange(len(actual)),actual[:,:stage],'fundamental')
            if np.any(base): raise ValueError('Market offset in Model A')
            y=(candidates==actual[:,stage,None]).astype(np.float32).ravel()
            ds.append(lgb.Dataset(x,label=y,reference=ds[0] if ds else None,free_raw_data=False)); xs.append(x)
        params=dict(objective=objective(k),metric='None',num_leaves=15,max_depth=4,min_data_in_leaf=300,
                    learning_rate=.03,lambda_l2=20,num_threads=2,seed=1604,deterministic=True,
                    force_col_wise=True,verbosity=-1,feature_pre_filter=False)
        model=lgb.train(params,ds[0],num_boost_round=500,valid_sets=[ds[1]],feval=metric(k),callbacks=[lgb.early_stopping(30,verbose=False)])
        path=args.output/f'stage{stage}.txt'; model.save_model(str(path)); models[stage]=model
        stages[str(stage)]={'sha256':digest(path),'iterations':model.best_iteration,'validationLoss':metric(k)(model.predict(xs[1],raw_score=True,num_threads=2),ds[1])[1]}
    pv=predict(inputs(b,'reaction'),'fundamental',models)
    temps=(.8,1.,1.2,1.5,2.)
    temp=min(temps,key=lambda t:(quality(calibrated(pv,t),b['actual_index'])['logloss'],t))
    p=calibrated(predict(inputs(d,'reaction'),'fundamental',models),temp)
    fit_max=int(max(a['day_ordinal'])); val_max=int(max(b['day_ordinal'])); pred_min=int(min(d['day_ordinal']))
    if not fit_max<val_max<pred_min: raise ValueError('Timestamp leak')
    meta={'fold':args.fold,'fitMaxOrdinal':fit_max,'validationMaxOrdinal':val_max,'predictionMinOrdinal':pred_min,
          'fitRaces':len(a['month']),'validationRaces':len(b['month']),'predictionRaces':len(d['month']),
          'temperature':temp,'stages':stages,'featureCacheSha256':digest(args.cache),'marketInModelA':False,
          'sourceCodeSha256':dict(code_hashes(),**{'scripts/v016_oof_study.py':digest(__file__)})}
    dump(args.output/'manifest.json',meta)
    save_predictions(args.output/'prediction.npz',d,p,meta.copy())

def development(args):
    import lightgbm as lgb
    rules(); c=checked(args.cache,'development'); keys(c)
    manifest=json.loads((args.model/'manifest.json').read_text())
    if manifest['variant']!='reaction' or manifest['marketInOutcomeModel'] or manifest['validationEndOrdinal']>=min(c['day_ordinal']):
        raise ValueError('Development model not frozen before evaluation')
    if manifest['codeSha256']!=code_hashes() or manifest['schemaSha256']!=canonical([c[k].tolist() for k in ('boat_names','history_names','reaction_names')]):
        raise ValueError('r4 code or feature schema drift')
    models={}
    for stage,details in manifest['stages'].items():
        file=args.model/f'stage{stage}.txt'
        if digest(file)!=details['sha256']: raise ValueError('Frozen tree changed')
        models[int(stage)]=lgb.Booster(model_file=str(file))
    p=calibrated(predict(inputs(c,'reaction'),'fundamental',models),manifest['temperature'])
    save_predictions(args.output,c,p,{'fold':'2025-07-08','fitMaxOrdinal':manifest['trainEndOrdinal'],
        'validationMaxOrdinal':manifest['validationEndOrdinal'],'predictionMinOrdinal':int(min(c['day_ordinal'])),
        'featureCacheSha256':digest(args.cache),'r4ModelManifestSha256':digest(args.model/'manifest.json'),
        'marketInModelA':False})

def market(c):
    good=c['usable']&c['odds_usable']&np.isfinite(c['odds']).all(axis=1)&(c['odds']>0).all(axis=1)
    m=np.zeros_like(c['odds'],dtype=np.float64)
    m[good]=normalize(1/c['odds'][good]); return m,good

def joined(args):
    c=checked(args.cache,'oof'); m,g=market(c); rows_out=[]
    for month in (3,4,5,6):
        cut=(c['month']==month); part=subset(c,cut)
        path=args.folds/f'v016-oof-2025-{month:02d}'/'prediction.npz'; p,meta=load_predictions(path,part)
        if not (meta['fitMaxOrdinal']<meta['validationMaxOrdinal']<meta['predictionMinOrdinal']): raise ValueError('Nonforward OOF')
        if meta['featureCacheSha256']!=digest(args.cache): raise ValueError('OOF cache changed')
        rows_out.append((part,p,m[cut],g[cut],meta))
    return rows_out

def logistic_fit(args):
    from sklearn.linear_model import LogisticRegression
    rules(); rows_out=joined(args)
    xs=[]; ys=[]
    for c,p,m,g,_ in rows_out:
        p=p[g]; m=m[g]; actual=c['actual_index'][g]
        x=np.stack((np.log(np.maximum(m,1e-15)),np.clip(np.log(np.maximum(p,1e-15)/np.maximum(m,1e-15)),-4,4)),axis=2).reshape(-1,2)
        y=(np.arange(120)[None,:]==actual[:,None]).ravel().astype(np.int8)
        xs.append(x); ys.append(y)
    model=LogisticRegression(C=.01,fit_intercept=True,random_state=1604,max_iter=200)
    model.fit(np.concatenate(xs),np.concatenate(ys)); args.output.parent.mkdir(parents=True,exist_ok=True)
    dump(args.output,{'coef':model.coef_[0].tolist(),'intercept':float(model.intercept_[0]),'nIter':model.n_iter_.tolist(),
        'oofRaces':int(sum(len(x)//120 for x in xs)),'protocolCommitSha':PROTOCOL_COMMIT,'protocolSha256':digest(PROTOCOL),
        'foldPredictionSha256':{meta['fold']:meta['predictionSha256'] for *_,meta in rows_out},
        'foldAudit':{meta['fold']:{k:meta[k] for k in ('fitMaxOrdinal','validationMaxOrdinal','predictionMinOrdinal','fitRaces','validationRaces','predictionRaces','temperature','stages','featureCacheSha256','sourceCodeSha256')} for *_,meta in rows_out},
        'septemberOpened':False,'q4Opened':False})

def candidate_probability(name,p,m,fit):
    if name=='raw_ratio': return p
    if name=='log_residual_half': return normalize(np.sqrt(np.maximum(p,1e-15)*np.maximum(m,1e-15)))
    x=np.log(np.maximum(m,1e-15))*fit['coef'][0]+np.clip(np.log(np.maximum(p,1e-15)/np.maximum(m,1e-15)),-4,4)*fit['coef'][1]+fit['intercept']
    q=1/(1+np.exp(-np.clip(x,-50,50)))
    return normalize(q)

def probability_metrics(p,actual):
    q=quality(p,actual); first=audit_p(p); winner=COMBOS[actual,0]
    rank=np.argsort(-p,axis=1,kind='stable')
    q.update(firstTop1=float((first.argmax(axis=1)==winner).mean()),
             firstTop2=float((np.argsort(-first,axis=1)[:,:2]==winner[:,None]).any(axis=1).mean()))
    for n in (1,2,4,8): q[f'trifectaTop{n}']=float((rank[:,:n]==actual[:,None]).any(axis=1).mean())
    return q

def evaluation(c,p,m,g,name,fit):
    proto,_=rules(); cfg=dict(budget=1200,maxPoints=3,minEv=1.10,minProbability=.01,maxOdds=40)
    q=candidate_probability(name,p[g],m[g],fit); audit_p(q)
    odds=c['odds'][g]; actual=c['actual_index'][g]; amount=c['amount'][g]; day=c['day_ordinal'][g]; months=c['month'][g]
    eligible=np.ones_like(q,dtype=bool)
    if name=='raw_ratio': eligible=q/np.maximum(m[g],1e-15)>=1.2
    selected,units,count=tickets(np.where(eligible,q,0.),odds,cfg)
    stake=np.where(count>0,1200,0); payout=(units*(selected==actual[:,None])).sum(axis=1)*amount
    expected=(units*np.take_along_axis(q*odds,selected,axis=1)*100).sum(axis=1)
    total=summarize(stake,payout,count); total['buyRate']=float((count>0).mean());
    total['expectedRoi']=float(100*expected.sum()/stake.sum()) if stake.sum() else None
    total['calibrationGap']=abs(total['expectedRoi']-total['roi']) if stake.sum() else None
    monthly={str(x):summarize(stake[months==x],payout[months==x],count[months==x]) for x in (7,8)}
    rng=np.random.default_rng(1604); unique,inv=np.unique(day,return_inverse=True)
    ds=np.bincount(inv,weights=stake); dp=np.bincount(inv,weights=payout)
    draws=rng.integers(0,len(unique),(1000,len(unique)))
    ratios=100*dp[draws].sum(axis=1)/np.maximum(ds[draws].sum(axis=1),1)
    gate=proto['developmentGate']; checks={
        'roi':total['roi']>=gate['roiMinPercent'],
        'roiWithoutLargestHit':total['roiWithoutLargestHit']>=gate['roiExcludingLargestHitMinPercent'],
        'purchaseRaces':total['purchaseRaces']>=gate['purchaseRacesMin'],
        'hits':total['hits']>=gate['hitsMin'],
        'largestHitShare':total['largestHitShare']<=gate['largestHitShareMaxPercent'],
        'calibrationGap':total['calibrationGap'] is not None and total['calibrationGap']<=gate['absoluteExpectedVsRealizedRoiGapMaxPoints']}
    return {'name':name,'probability':probability_metrics(q,actual),'purchase':total,'monthly':monthly,
            'dayBootstrap95':np.quantile(ratios,[.025,.975]).tolist(),'checks':checks,'pass':all(checks.values())}

def assess(args):
    rules(); c=checked(args.cache,'development'); p,meta=load_predictions(args.prediction,c)
    if meta['featureCacheSha256']!=digest(args.cache) or meta['validationMaxOrdinal']>=min(c['day_ordinal']): raise ValueError('Evaluation leak')
    fit=json.loads(args.logistic.read_text())
    if fit['protocolCommitSha']!=PROTOCOL_COMMIT or fit['protocolSha256']!=digest(PROTOCOL): raise ValueError('Selector trained under different protocol')
    m,g=market(c); base=probability_metrics(p[g],c['actual_index'][g])
    return {'base':base,'candidates':[evaluation(c,p,m,g,name,fit) for name in CANDIDATES],
            'protocolCommitSha':PROTOCOL_COMMIT,'protocolSha256':digest(PROTOCOL),'featureCacheSha256':digest(args.cache),
            'predictionSha256':digest(args.prediction),'selectorSha256':digest(args.logistic),'septemberOpened':False,'q4Opened':False}

def evaluate_one(args):
    result=assess(args); candidate=next(x for x in result['candidates'] if x['name']==args.candidate)
    candidate.update({k:result[k] for k in ('protocolCommitSha','protocolSha256','featureCacheSha256','predictionSha256','selectorSha256','septemberOpened','q4Opened')})
    dump(args.output,candidate)

def publish(args):
    proto,_=rules(); c=checked(args.cache,'development'); p,meta=load_predictions(args.prediction,c)
    m,g=market(c); base=probability_metrics(p[g],c['actual_index'][g]); entries=[]
    for name in CANDIDATES:
        x=json.loads((args.input/f'{name}.json').read_text())
        if x['name']!=name or x['protocolCommitSha']!=PROTOCOL_COMMIT or x['protocolSha256']!=digest(PROTOCOL) or x['predictionSha256']!=digest(args.prediction) or x['featureCacheSha256']!=digest(args.cache) or x['selectorSha256']!=digest(args.logistic):
            raise ValueError('Missing or mismatched candidate')
        entries.append(x)
    # Quality gate precedes selection, compared with preregistered r4 reaction metrics.
    gate=proto['developmentGate']
    quality_ok=(base['logloss']<=3.796222+gate['modelLoglossMaxIncreaseVsR4Reaction'] and
                base['brier']<=.960191+gate['modelBrierMaxIncreaseVsR4Reaction'])
    passing=sorted((x for x in entries if x['pass']),key=lambda x:(-x['purchase']['roiWithoutLargestHit'],-x['purchase']['purchaseRaces'],x['name']))
    choice=passing[0]['name'] if quality_ok and passing else None
    common={'protocolCommitSha':PROTOCOL_COMMIT,'protocolSha256':digest(PROTOCOL),'splitManifestSha256':digest(SPLIT),
            'runId':args.run,'developmentPredictionSha256':digest(args.prediction),'selectorSha256':digest(args.logistic),
            'septemberOpened':False,'q4Opened':False,'annualQualified':False,'productionPromotion':False}
    report=dict(common,modelA=base,r4ReactionComparison={'logloss':3.796222,'brier':.960191},
                modelQualityGatePass=quality_ok,candidates=entries,decision='DEVELOPMENT_PASS_ONLY' if choice else 'REJECT',
                frozenCandidate=choice,sourceRunId=35940833546,
                limitations=['Historical odds timing not validated at five minutes before close','Only settled six-boat archived races',
                             'July-August previously examined in r4; cannot constitute independent final holdout','Annual ROI and multiyear reproducibility untested'])
    args.output.mkdir(parents=True,exist_ok=True)
    dump(args.output/'v016_oof_result.json',report)
    dump(args.output/'v016_oof_frozen_candidate.json',dict(common,candidate={'selector':choice,'fixedRule':proto['selector'][choice] if choice and choice!='logistic_residual' else ('OOF logistic coefficients frozen' if choice else None)} if choice else None))
    dump(args.output/'v016_oof_feature_audit.json',dict(common,trainCacheSha256=args.train_sha,
         developmentCacheSha256=digest(args.cache),developmentRaces=len(c['month']),eligibleOddsRaces=int(g.sum()),
         historyLeakCount=int((c['history_through']>=c['day_ordinal']).sum()),duplicateRaceKeys=0,
         foldAudit=json.loads(args.logistic.read_text())['foldAudit'],
         firstMarginalMaxSumError=float(np.abs(audit_p(p).sum(axis=1)-1).max())))
    lines=['# v0.16 OOF市場差校正 — 固定開発評価','',f'- Run: {args.run}; protocol commit: `{PROTOCOL_COMMIT}`',
           '- r4 Artifact再利用: features 10784104679、Model A 10784912368（Run 35940833546）',
           '- 4 forward foldsは3〜6月、7〜8月は追加学習なし。9月とQ4は未取得・未評価。','',
           '| 候補 | 購入 | 的中 | ROI | 最大1的中除外ROI | EV差 | 判定 |','|---|---:|---:|---:|---:|---:|---|']
    for x in entries:
        t=x['purchase']; lines.append(f"| {x['name']} | {t['purchaseRaces']} | {t['hits']} | {t['roi']:.2f}% | {t['roiWithoutLargestHit']:.2f}% | {t['calibrationGap'] if t['calibrationGap'] is not None else 'N/A'} | {'開発gate通過' if x['pass'] else '不採用'} |")
    lines.extend(['',f'採否: {report["decision"]}。候補: {choice or "なし"}。確率品質gate: {quality_ok}。',
                  '年間105%と複数年再現性は未評価。本番統合は行わない。',''])
    (args.output/'v016_oof_report.md').write_text('\n'.join(lines))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); subs=ap.add_subparsers(dest='command',required=True)
    f=subs.add_parser('fold'); f.add_argument('--cache',type=Path,required=True); f.add_argument('--fold',choices=[f'2025-{i:02d}' for i in range(3,7)],required=True); f.add_argument('--output',type=Path,required=True)
    d=subs.add_parser('development'); d.add_argument('--cache',type=Path,required=True); d.add_argument('--model',type=Path,required=True); d.add_argument('--output',type=Path,required=True)
    l=subs.add_parser('logistic'); l.add_argument('--cache',type=Path,required=True); l.add_argument('--folds',type=Path,required=True); l.add_argument('--output',type=Path,required=True)
    e=subs.add_parser('evaluate'); e.add_argument('--cache',type=Path,required=True); e.add_argument('--prediction',type=Path,required=True); e.add_argument('--logistic',type=Path,required=True); e.add_argument('--candidate',choices=CANDIDATES,required=True); e.add_argument('--output',type=Path,required=True)
    z=subs.add_parser('publish'); z.add_argument('--cache',type=Path,required=True); z.add_argument('--prediction',type=Path,required=True); z.add_argument('--logistic',type=Path,required=True); z.add_argument('--input',type=Path,required=True); z.add_argument('--output',type=Path,required=True); z.add_argument('--run',required=True); z.add_argument('--train-sha',required=True)
    a=ap.parse_args(); {'fold':fit_fold,'development':development,'logistic':logistic_fit,'evaluate':evaluate_one,'publish':publish}[a.command](a)
