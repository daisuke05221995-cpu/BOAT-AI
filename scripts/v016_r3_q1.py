#!/usr/bin/env python3
"""Evaluate the preregistered r3 place-small model on 2024 Q1.

Training uses only 2023 Q4 pre-race sidecar: Oct-Nov fit, Dec validation.
Evaluation uses 2024 Jan-Mar. The fixed r2 betting policy is unchanged.
"""
import argparse, json
from datetime import date
from pathlib import Path
import numpy as np

from v016_core_research import digest, dump, normalize, summarize, tickets
from v016_r2_features import FEATURES, GLOBALS, PROTOCOL as R2_PROTOCOL, load
from v016_r2_model import COMBOS, context, metric, objective, predict, rows, subset, validate_combos
from v016_r3_walkforward import fixed_policy, load_baseline

ROOT=Path(__file__).resolve().parents[1]
R3_PROTOCOL=ROOT/'data/v016_r3_protocol.json'


def prior_load(path):
    with np.load(path,allow_pickle=False) as z:
        needed=['year','combos','month','day_ordinal','venue','race_number','actual_index','amount','market_p','odds','boat','global_features','usable']
        if any(k not in z.files for k in needed): raise ValueError('pre2024 sidecar schema incomplete')
        c={k:z[k] for k in needed}
    if int(c['year'][0])!=2023 or set(map(int,np.unique(c['month'])))!={10,11,12}: raise ValueError('pre2024 sidecar must be 2023 Q4 only')
    if c['boat'].shape[2]!=len(FEATURES) or c['global_features'].shape[1]!=len(GLOBALS): raise ValueError('feature schema drift')
    for d in c['day_ordinal']:
        dt=date.fromordinal(int(d))
        if not date(2023,10,1)<=dt<=date(2023,12,31): raise ValueError('pre2024 date fence')
    validate_combos(c)
    order=np.lexsort((c['race_number'],c['venue'],c['day_ordinal']))
    return subset(c,order)


def fit_place(prior, outdir):
    import lightgbm as lgb
    train=subset(prior,np.isin(prior['month'],[10,11]) & prior['usable'])
    valid=subset(prior,(prior['month']==12) & prior['usable'])
    if len(train['month'])<5000 or len(valid['month'])<2500: raise ValueError('Q4 training/validation too sparse')
    if max(train['day_ordinal'])>=min(valid['day_ordinal']): raise ValueError('Q1 training chronology violation')
    if max(valid['day_ordinal'])>=date(2024,1,1).toordinal(): raise ValueError('validation crosses Q1 evaluation')
    cap=json.loads(R2_PROTOCOL.read_text())['capacities']['small']; models={}; stages={}
    contexts=[context(train),context(valid)]; outdir.mkdir(parents=True,exist_ok=True)
    for stage in (1,2):
        k=6-stage; datasets=[]; arrays=[]
        for part,ctx in zip((train,valid),contexts):
            actual=COMBOS[part['actual_index']]
            x,base,candidate=rows(ctx,np.arange(len(actual)),actual[:,:stage],'place')
            y=(candidate==actual[:,stage,None]).astype(np.float32).ravel()
            if not np.all(y.reshape(-1,k).sum(axis=1)==1): raise ValueError('invalid Q1 conditional label')
            ds=lgb.Dataset(x,label=y,init_score=base,free_raw_data=False,reference=datasets[0] if datasets else None)
            datasets.append(ds); arrays.append((x,base))
        params=dict(cap,objective=objective(k),metric='None',learning_rate=.03,lambda_l2=20,num_threads=2,seed=1602,
                    deterministic=True,force_col_wise=True,verbosity=-1,feature_pre_filter=False)
        model=lgb.train(params,datasets[0],num_boost_round=400,valid_sets=[datasets[1]],feval=metric(k),
                        callbacks=[lgb.early_stopping(30,verbose=False)])
        x,base=arrays[1]; loss=metric(k)(model.predict(x,raw_score=True,num_threads=2)+base,datasets[1])[1]
        file=outdir/f'stage{stage}.txt'; model.save_model(str(file)); models[stage]=model
        stages[str(stage)]={'iterations':int(model.best_iteration),'validationLogloss':float(loss),'sha256':digest(file)}
    return models,{'train':'2023-10-01..2023-11-30','validation':'2023-12-01..2023-12-31',
                   'trainRaces':int(len(train['month'])),'validationRaces':int(len(valid['month'])),'stages':stages}


def run(args):
    protocol=json.loads(R3_PROTOCOL.read_text())
    q1=protocol['chronology']['2024_q1']
    if not isinstance(q1,dict) or q1.get('train_end')!='2023-11-30' or q1.get('validation')!=['2023-12-01','2023-12-31']:
        raise ValueError('Q1 split was not preregistered')
    if protocol['holdout']['state']!='SEALED': raise ValueError('final holdout not sealed')
    prior=prior_load(args.prior_cache); current=load(args.current_cache,2024)
    baseline,baseline_path=load_baseline(args.baseline_dir,current)
    mask=np.isin(current['month'],[1,2,3]); c=subset(current,mask); static=baseline[mask]
    if set(map(int,np.unique(c['month'])))!={1,2,3} or len(c['month'])<12000: raise ValueError('Q1 current cache incomplete')
    models,manifest=fit_place(prior,args.output_dir/'model')
    p=predict(c,'place',models).astype(np.float64); p[~c['usable']]=0
    mutated={k:(v.copy() if hasattr(v,'copy') else v) for k,v in c.items()}; mutated['actual_index']=(mutated['actual_index']+41)%120
    pm=predict(mutated,'place',models).astype(np.float64); pm[~mutated['usable']]=0
    if not np.allclose(p,pm,atol=1e-12): raise ValueError('Q1 future-label mutation changed predictions')
    good=c['usable']; actual=c['actual_index'][good]; ix=np.arange(int(good.sum())); market=normalize(c['market_p'][good])
    def ll(q): return float(-np.log(np.maximum(q[ix,actual],1e-15)).mean())
    wf=ll(p[good]); st=ll(static[good]); mk=ll(market)
    policy=fixed_policy(); chosen,units,counts=tickets(p,c['odds'],policy)
    wins=(units*(chosen==c['actual_index'][:,None])).sum(axis=1); stake=np.where(counts>0,policy['budget'],0); payout=wins*c['amount']
    total=summarize(stake,payout,counts); total['largestHitPayout']=int(payout.max(initial=0))
    result={'protocol':protocol['protocol'],'family':'place','capacity':'small','quarter':'q1','manifest':manifest,'total':total,
            'predictionMetrics':{'walkForwardLogloss':wf,'staticR2Logloss':st,'marketLogloss':mk,'deltaVsStatic':wf-st,'deltaVsMarket':wf-mk,
                                 'usableRaces':int(good.sum()),'allRaces':int(len(good))},
            'fixedPolicy':policy,'priorCacheSha256':digest(args.prior_cache),'currentCacheSha256':digest(args.current_cache),
            'baselinePredictionSha256':digest(baseline_path),'futureLabelMutationInvariant':True,'finalHoldoutOpened':False,'releaseQualified':False}
    args.output_dir.mkdir(parents=True,exist_ok=True); dump(args.output_dir/'result.json',result)
    np.savez_compressed(args.output_dir/'predictions.npz',p=p,day_ordinal=c['day_ordinal'],venue=c['venue'],race_number=c['race_number'])
    print(json.dumps({'total':total,'metrics':result['predictionMetrics']},ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--prior-cache',type=Path,required=True); p.add_argument('--current-cache',type=Path,required=True)
    p.add_argument('--baseline-dir',type=Path,required=True); p.add_argument('--output-dir',type=Path,required=True); run(p.parse_args())
