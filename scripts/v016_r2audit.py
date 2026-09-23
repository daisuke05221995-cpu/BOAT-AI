#!/usr/bin/env python3
"""Audit saved r2 predictions without fitting or trying another buying threshold."""
import argparse
import json
from pathlib import Path
import numpy as np
from v016_core_research import dump, digest, normalize, tickets
from v016_r2_features import load, PROTOCOL
from v016_r2_model import subset

def audit(args):
    c=load(args.cache,args.year)
    if args.year==2023: c=subset(c,c['month']==9)
    c=subset(c,np.lexsort((c['race_number'],c['venue'],c['day_ordinal'])))
    with np.load(args.prediction,allow_pickle=False) as z:
        for k in ['day_ordinal','venue','race_number']:
            if not np.array_equal(z[k],c[k]): raise ValueError('Prediction/cache race alignment mismatch')
        p=z['p'].astype(np.float64)
    if p.shape!=c['market_p'].shape: raise ValueError('Prediction shape mismatch')
    result=json.loads(args.prediction.with_suffix('.json').read_text())
    if result['evaluationCacheSha256']!=digest(args.cache): raise ValueError('Feature cache checksum mismatch')
    good=c['usable']; actual=c['actual_index']; ix=np.arange(len(p)); market=normalize(c['market_p'])
    loss=-np.log(np.maximum(p[ix,actual],1e-15))+np.log(np.maximum(market[ix,actual],1e-15))
    days,inverse=np.unique(c['day_ordinal'][good],return_inverse=True)
    sums=np.bincount(inverse,weights=loss[good]); counts=np.bincount(inverse)
    rng=np.random.default_rng(16023); sample=rng.integers(0,len(days),size=(1000,len(days)))
    bootstrap=sums[sample].sum(axis=1)/counts[sample].sum(axis=1)
    policy=json.loads(PROTOCOL.read_text())['fixedPolicy']; chosen,units,number=tickets(p,c['odds'],policy)
    stake=np.where(number>0,1200,0)
    expected=(units*np.take_along_axis(p*c['odds'],chosen,axis=1)*100).sum(axis=1)
    payout=(units*(chosen==actual[:,None])).sum(axis=1)*c['amount']
    for key,v in [('stake',int(stake.sum())),('payout',int(payout.sum())),('purchaseRaces',int((number>0).sum()))]:
        if result['total'][key]!=v: raise ValueError('Saved result accounting mismatch: '+key)
    # Descriptive bins only. They never produce a new buying policy/candidate.
    edges=[0,.5,.75,1,1.1,1.25,1.5,2,float('inf')]
    eligible=good[:,None]&(c['odds']>1)&(c['odds']<=40)&(p>=.01)
    ev=p*c['odds']; hit=np.zeros_like(p); hit[ix,actual]=c['amount']/100
    bins=[]
    for low,high in zip(edges[:-1],edges[1:]):
        mask=eligible&(ev>=low)&(ev<high); n=int(mask.sum())
        bins.append({'evFrom':low,'evTo':high if np.isfinite(high) else None,'ticketObservations':n,
                     'raceObservations':int(mask.any(axis=1).sum()),
                     'meanPredictedReturn':float(ev[mask].mean()) if n else None,
                     'meanRealizedReturn':float(hit[mask].sum()/n) if n else None})
    total=int(stake.sum())
    out={'modelId':result['modelId'],'year':args.year,'sourcePredictionSha256':digest(args.prediction),
         'pairedLoglossDifference':float(loss[good].mean()),
         'dailyClusterBootstrap95':np.quantile(bootstrap,[.025,.975]).tolist(),'bootstrapReplicates':1000,
         'days':len(days),'usableRaces':int(good.sum()),
         'fixedPolicy':{'purchaseRaces':int((number>0).sum()),'expectedRoi':float(100*expected.sum()/total) if total else None,
                        'actualRoi':float(100*payout.sum()/total) if total else None},
         'descriptiveCalibrationBins':bins,'newPolicySelected':False,'holdoutOpened':False,
         'limitations':['Daily resampling does not remove archive bias or development-year selection bias',
                         'Overlapping ticket observations are correlated; bin means are not independent trials']}
    dump(args.output,out)
    print(json.dumps({k:v for k,v in out.items() if k not in ('descriptiveCalibrationBins','limitations')}))

def aggregate(args):
    rows=[json.loads(p.read_text()) for p in sorted(args.input.glob('audit-*.json'))]
    expected={(f+'-'+s,y) for f in ['fundamental','residual','place'] for s in ['small','medium'] for y in (2023,2024)}
    if len(rows)!=12 or {(r['modelId'],r['year']) for r in rows}!=expected: raise ValueError('Incomplete audit')
    dump(args.output,{'runId':args.run,'sourceRunId':35875673825,'results':rows,
                      'candidateSelectionChanged':False,'holdoutOpened':False})

if __name__=='__main__':
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('audit'); a.add_argument('--cache',type=Path,required=True); a.add_argument('--prediction',type=Path,required=True)
    a.add_argument('--year',type=int,required=True); a.add_argument('--output',type=Path,required=True)
    g=s.add_parser('aggregate'); g.add_argument('--input',type=Path,required=True); g.add_argument('--output',type=Path,required=True)
    g.add_argument('--run',required=True)
    args=p.parse_args(); {'audit':audit,'aggregate':aggregate}[args.command](args)
