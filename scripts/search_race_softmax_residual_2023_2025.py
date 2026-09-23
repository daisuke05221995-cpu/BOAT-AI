#!/usr/bin/env python3
"""Race-level softmax residual model on top of market probabilities.

A shared small MLP scores every trifecta combo, but its residual is added to the
archived market log-probability and normalized jointly across all 120 combos in a
race. This preserves the race probability simplex and avoids the independent-binary
calibration problem of the previous experiment.

Protocol:
- Train on 2023 May-Aug only.
- Use 2023 Sep only for early stopping (model selection).
- Never refit on 2024. Select only residual shrink beta by 2024 race log-loss and
  ticket config by 2024 May-Sep development outcomes.
- Freeze weights, beta and ticket config; evaluate 2025 May-Sep.
- Never load 2025 Oct-Dec; it remains the pristine final holdout.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_multiyear_strategy_v14 as v14

TRAIN_MONTHS=(5,6,7,8)
EARLY_STOP_MONTH=9
OP_MONTHS=(5,6,7,8,9)
BUDGET=1200
BUDGET_UNITS=12
EPS=1e-8
HIDDEN=24
RESIDUAL_SCALE=1.25
L2=2e-4
LR=0.003
MAX_EPOCHS=35
PATIENCE=6
BATCH_RACES=128
BETAS=(0.25,0.50,0.75,1.00)

MIN_EV_OPTIONS=(1.02,1.05,1.08,1.10,1.15)
MIN_PROB_OPTIONS=(0.003,0.005,0.010,0.020)
MAX_ODDS_OPTIONS=(20.0,40.0,80.0)
MAX_POINTS_OPTIONS=(1,2,3)
DESIGN_MIN_TOTAL_BUYS=100
DESIGN_MIN_MONTH_BUYS=10
TARGET_MIN_TOTAL_BUYS=100
TARGET_MIN_MONTH_BUYS=10
TARGET_MIN_ROI=105.0
TARGET_MIN_POSITIVE_MONTHS=4
TARGET_MIN_WORST_ROI=90.0
TARGET_MAX_LARGEST_HIT_SHARE=25.0


def load_cache(cache_dir:Path,year:int)->v14.Cache:
    c=v14.Cache(cache_dir/f'signal_cache_{year}.npz')
    if c.year!=year: raise RuntimeError(f'cache year mismatch {c.year} != {year}')
    return c


def rank_matrix(prob:np.ndarray)->np.ndarray:
    order=np.argsort(-prob,axis=1)
    out=np.empty_like(order,dtype=np.int16)
    vals=np.broadcast_to(np.arange(1,prob.shape[1]+1,dtype=np.int16),order.shape)
    np.put_along_axis(out,order,vals,axis=1)
    return out


def combo_lanes(combos:np.ndarray)->tuple[np.ndarray,np.ndarray,np.ndarray]:
    arr=np.asarray([[int(x) for x in str(c).split('-')] for c in combos],dtype=np.int8)
    return arr[:,0],arr[:,1],arr[:,2]


def feature_cube(cache:v14.Cache)->np.ndarray:
    market=np.maximum(cache.market_p.astype(np.float64),EPS)
    model=np.maximum(cache.model_p.astype(np.float64),EPS)
    odds=cache.odds.astype(np.float64)
    safe_odds=np.where(odds>1.0,np.minimum(odds,200.0),200.0)
    mrank=rank_matrix(model).astype(np.float64)
    krank=rank_matrix(market).astype(np.float64)
    log_ratio=np.log(model/market)
    first,second,third=combo_lanes(cache.combos)
    n,k=model.shape
    one=np.eye(6,dtype=np.float32)
    f1=np.broadcast_to(one[first-1][None,:,:],(n,k,6))
    f2=np.broadcast_to(one[second-1][None,:,:],(n,k,6))
    f3=np.broadcast_to(one[third-1][None,:,:],(n,k,6))
    numeric=np.stack([
        np.log(market),np.log(model),log_ratio,np.log(safe_odds),
        mrank/120.0,krank/120.0,(krank-mrank)/120.0,
        (mrank<=5).astype(float),(krank<=5).astype(float),
        (mrank<=10).astype(float),(krank<=10).astype(float),
        (mrank<=20).astype(float),(krank<=20).astype(float),
        log_ratio*(first[None,:]==1),log_ratio*(first[None,:]>=4),
        np.log(safe_odds)*(first[None,:]==1),np.log(safe_odds)*(first[None,:]>=4),
        (odds<=1.0).astype(float),
    ],axis=2).astype(np.float32)
    return np.concatenate([numeric,f1,f2,f3],axis=2).astype(np.float32)


def softmax(scores:np.ndarray)->np.ndarray:
    x=scores-scores.max(axis=1,keepdims=True)
    e=np.exp(x)
    return e/np.maximum(e.sum(axis=1,keepdims=True),EPS)


@dataclass
class MLP:
    w1:np.ndarray
    b1:np.ndarray
    w2:np.ndarray
    b2:float
    mean:np.ndarray
    std:np.ndarray

    def residual(self,x:np.ndarray)->np.ndarray:
        z=(x-self.mean)/self.std
        h=np.tanh(z@self.w1+self.b1)
        raw=h@self.w2+self.b2
        return RESIDUAL_SCALE*np.tanh(raw)


def probabilities(cache:v14.Cache,cube:np.ndarray,net:MLP,beta:float)->np.ndarray:
    n,k,d=cube.shape
    resid=net.residual(cube.reshape(-1,d)).reshape(n,k)
    base=np.log(np.maximum(cache.market_p.astype(np.float64),EPS))
    return softmax(base+float(beta)*resid)


def logloss(cache:v14.Cache,p:np.ndarray,months:tuple[int,...])->float:
    rows=np.where(np.isin(cache.month,months))[0]
    return float(-np.log(np.clip(p[rows,cache.actual[rows]],EPS,1.0)).mean())


def train(cache:v14.Cache,seed:int=20260923)->tuple[MLP,list[dict[str,Any]]]:
    cube=feature_cube(cache)
    train_rows=np.where(np.isin(cache.month,TRAIN_MONTHS))[0]
    val_rows=np.where(cache.month==EARLY_STOP_MONTH)[0]
    x_train=cube[train_rows]
    # Standardize from training combos only.
    mean=x_train.mean(axis=(0,1),dtype=np.float64).astype(np.float32)
    std=x_train.std(axis=(0,1),dtype=np.float64).astype(np.float32)
    std=np.where(std<1e-4,1.0,std).astype(np.float32)
    d=cube.shape[2]
    rng=np.random.default_rng(seed)
    w1=(rng.standard_normal((d,HIDDEN))*0.025).astype(np.float32)
    b1=np.zeros(HIDDEN,dtype=np.float32)
    w2=(rng.standard_normal(HIDDEN)*0.025).astype(np.float32)
    b2=np.float32(0.0)
    params=[w1,b1,w2]
    m=[np.zeros_like(p) for p in params]; v=[np.zeros_like(p) for p in params]
    mb=np.float32(0.0); vb=np.float32(0.0); step=0
    best=None; best_loss=float('inf'); patience=0; history=[]

    base=np.log(np.maximum(cache.market_p.astype(np.float64),EPS))
    for epoch in range(1,MAX_EPOCHS+1):
        order=rng.permutation(train_rows)
        total_loss=0.0; batches=0
        for start in range(0,len(order),BATCH_RACES):
            rows=order[start:start+BATCH_RACES]
            xb=((cube[rows]-mean)/std).astype(np.float32)
            b,k,_=xb.shape
            flat=xb.reshape(-1,d)
            h=np.tanh(flat@w1+b1).reshape(b,k,HIDDEN)
            raw=(h.reshape(-1,HIDDEN)@w2+b2).reshape(b,k)
            tanh_raw=np.tanh(raw)
            resid=RESIDUAL_SCALE*tanh_raw
            prob=softmax(base[rows]+resid)
            actual=cache.actual[rows]
            loss=float(-np.log(np.clip(prob[np.arange(b),actual],EPS,1.0)).mean())
            total_loss+=loss; batches+=1

            ds=prob
            ds[np.arange(b),actual]-=1.0
            ds/=b
            dz=ds*RESIDUAL_SCALE*(1.0-tanh_raw*tanh_raw)
            hflat=h.reshape(-1,HIDDEN); dzflat=dz.reshape(-1)
            gw2=(hflat.T@dzflat).astype(np.float32)+L2*w2
            gb2=np.float32(dzflat.sum())
            dh=(dzflat[:,None]*w2[None,:]).reshape(b,k,HIDDEN)
            da=dh*(1.0-h*h)
            daflat=da.reshape(-1,HIDDEN)
            gw1=(flat.T@daflat).astype(np.float32)+L2*w1
            gb1=daflat.sum(axis=0).astype(np.float32)
            grads=[gw1,gb1,gw2]
            step+=1
            for i,(param,g) in enumerate(zip(params,grads)):
                m[i]=0.9*m[i]+0.1*g; v[i]=0.999*v[i]+0.001*(g*g)
                mh=m[i]/(1.0-0.9**step); vh=v[i]/(1.0-0.999**step)
                param-=LR*mh/(np.sqrt(vh)+1e-8)
            mb=np.float32(0.9*mb+0.1*gb2); vb=np.float32(0.999*vb+0.001*gb2*gb2)
            mhb=mb/(1.0-0.9**step); vhb=vb/(1.0-0.999**step)
            b2=np.float32(b2-LR*mhb/(np.sqrt(vhb)+1e-8))

        net=MLP(w1.copy(),b1.copy(),w2.copy(),float(b2),mean,std)
        pval=probabilities(cache,cube,net,1.0)
        val_loss=logloss(cache,pval,(EARLY_STOP_MONTH,))
        market=np.maximum(cache.market_p.astype(np.float64),EPS); market/=market.sum(axis=1,keepdims=True)
        market_val=logloss(cache,market,(EARLY_STOP_MONTH,))
        history.append({'epoch':epoch,'trainLoss':round(total_loss/max(1,batches),8),'validationLogLoss':round(val_loss,8),'marketValidationLogLoss':round(market_val,8)})
        print(history[-1],flush=True)
        if val_loss<best_loss-1e-5:
            best_loss=val_loss; best=(w1.copy(),b1.copy(),w2.copy(),float(b2)); patience=0
        else:
            patience+=1
            if patience>=PATIENCE: break
    if best is None: raise RuntimeError('no MLP checkpoint')
    return MLP(best[0],best[1],best[2],best[3],mean,std),history


def select_beta(cache:v14.Cache,cube:np.ndarray,net:MLP)->tuple[float,list[dict[str,float]]]:
    trials=[]
    for beta in BETAS:
        p=probabilities(cache,cube,net,beta)
        trials.append({'beta':beta,'logLoss':round(logloss(cache,p,OP_MONTHS),8)})
    trials.sort(key=lambda r:r['logLoss'])
    return float(trials[0]['beta']),trials


def prep_month(cache:v14.Cache,p:np.ndarray,month:int)->dict[str,np.ndarray]:
    mask=cache.month==month; prob=p[mask]; odds=cache.odds[mask].astype(np.float64); ev=prob*odds
    order=np.argsort(-ev,axis=1)
    return {'p':np.take_along_axis(prob,order,axis=1),'ev':np.take_along_axis(ev,order,axis=1),'odds':np.take_along_axis(odds,order,axis=1),'comboIndex':order,'actual':cache.actual[mask],'amount':cache.amount[mask].astype(np.int64)}


def configs()->list[dict[str,Any]]:
    return [{'minEv':e,'minProbability':p,'maxOdds':o,'maxPoints':n,'budget':BUDGET} for e in MIN_EV_OPTIONS for p in MIN_PROB_OPTIONS for o in MAX_ODDS_OPTIONS for n in MAX_POINTS_OPTIONS]


def final(buys:int,hits:int,payout:int,bets:int,largest:int)->dict[str,Any]:
    stake=buys*BUDGET
    return {'purchaseRaces':buys,'hits':hits,'stake':stake,'payout':payout,'profit':payout-stake,'roi':round(payout*100.0/stake,1) if stake else 0.0,'hitRate':round(hits*100.0/buys,1) if buys else 0.0,'bets':bets,'avgPoints':round(bets/buys,2) if buys else 0.0,'largestHitPayout':largest,'largestHitShare':round(largest*100.0/payout,1) if payout else 0.0}


def eval_month(data:dict[str,np.ndarray],cfg:dict[str,Any])->dict[str,Any]:
    elig=(data['ev']>=cfg['minEv'])&(data['p']>=cfg['minProbability'])&(data['odds']>1)&(data['odds']<=cfg['maxOdds'])
    r=np.cumsum(elig,axis=1); take=elig&(r<=cfg['maxPoints']); cnt=take.sum(axis=1).astype(np.int64); buy=cnt>0; buys=int(buy.sum())
    if not buys:return final(0,0,0,0,0)
    base=np.zeros(len(cnt),dtype=np.int64); base[buy]=BUDGET_UNITS//cnt[buy]; rem=np.zeros(len(cnt),dtype=np.int64); rem[buy]=BUDGET_UNITS-base[buy]*cnt[buy]
    units=np.where(take,base[:,None]+((r<=rem[:,None])&take).astype(np.int64),0)
    hitmask=data['comboIndex']==data['actual'][:,None]; au=(units*hitmask).sum(axis=1).astype(np.int64); pay=data['amount']*au
    return final(buys,int((au>0).sum()),int(pay.sum()),int(cnt[buy].sum()),int(pay.max(initial=0)))


def eval_year(prep:dict[int,dict[str,np.ndarray]],cfg:dict[str,Any])->tuple[dict[int,dict[str,Any]],dict[str,Any]]:
    m={month:eval_month(prep[month],cfg) for month in OP_MONTHS}; rows=list(m.values())
    return m,final(sum(x['purchaseRaces'] for x in rows),sum(x['hits'] for x in rows),sum(x['payout'] for x in rows),sum(x['bets'] for x in rows),max((x['largestHitPayout'] for x in rows),default=0))


def metric(m:dict[int,dict[str,Any]],t:dict[str,Any])->dict[str,Any]:
    rows=list(m.values()); pos=sum(x['purchaseRaces']>0 and x['profit']>0 for x in rows); worst=min((x['roi'] for x in rows),default=0.0); vol=all(x['purchaseRaces']>=TARGET_MIN_MONTH_BUYS for x in rows)
    return {'positiveMonths':pos,'worstMonthRoi':worst,'volumeOk':vol,'targetMet':bool(t['purchaseRaces']>=TARGET_MIN_TOTAL_BUYS and t['roi']>=TARGET_MIN_ROI and pos>=TARGET_MIN_POSITIVE_MONTHS and worst>=TARGET_MIN_WORST_ROI and t['largestHitShare']<=TARGET_MAX_LARGEST_HIT_SHARE and vol)}


def score(m:dict[int,dict[str,Any]],t:dict[str,Any])->tuple[Any,...]:
    x=metric(m,t); return (x['positiveMonths'],x['worstMonthRoi'],-t['largestHitShare'],t['roi'],t['purchaseRaces'])


def main()->None:
    ap=argparse.ArgumentParser(); ap.add_argument('--cache-dir',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--model-output',type=Path,required=True); args=ap.parse_args()
    c23=load_cache(args.cache_dir,2023); c24=load_cache(args.cache_dir,2024); c25=load_cache(args.cache_dir,2025)
    net,history=train(c23); cube24=feature_cube(c24); beta,beta_trials=select_beta(c24,cube24,net); p24=probabilities(c24,cube24,net,beta)
    market24=np.maximum(c24.market_p.astype(np.float64),EPS); market24/=market24.sum(axis=1,keepdims=True)
    market_ll=logloss(c24,market24,OP_MONTHS); adjusted_ll=logloss(c24,p24,OP_MONTHS); prep24={m:prep_month(c24,p24,m) for m in OP_MONTHS}
    ranked=[]; diag=[]
    for cfg in configs():
        m,t=eval_year(prep24,cfg); mm=min(x['purchaseRaces'] for x in m.values()); met=metric(m,t); diag.append({'config':cfg,'minMonthBuys':mm,'total':t,**met})
        if t['purchaseRaces']>=DESIGN_MIN_TOTAL_BUYS and mm>=DESIGN_MIN_MONTH_BUYS: ranked.append((score(m,t),cfg,m,t))
    diag.sort(key=lambda x:(x['minMonthBuys'],x['total']['purchaseRaces'],x['positiveMonths'],x['worstMonthRoi'],x['total']['roi']),reverse=True)
    result:dict[str,Any]={'schemaVersion':22,'generatedAt':datetime.now(timezone.utc).isoformat(),'researchOnly':True,'releaseQualified':False,'method':'race-level softmax MLP residual on market probabilities; 2023 May-Aug train, Sep early stop, 2024 beta/ticket design, frozen 2025 evaluation','model':{'hidden':HIDDEN,'residualScale':RESIDUAL_SCALE,'l2':L2,'learningRate':LR,'bestValidationLogLoss':min(x['validationLogLoss'] for x in history),'epochsRun':len(history)},'trainingHistory':history,'betaSelection':{'selected':beta,'trials':beta_trials,'market2024LogLoss':round(market_ll,8),'adjusted2024LogLoss':round(adjusted_ll,8),'improved':bool(adjusted_ll<market_ll)},'basicVolumeFeasible':bool(ranked),'bestByVolume':diag[:10],'holdoutPolicy':{'reserved':'2025-10-01..2025-12-31','opened':False}}
    if ranked:
        ranked.sort(key=lambda x:x[0],reverse=True); sc,cfg,m24,t24=ranked[0]; met24=metric(m24,t24); cube25=feature_cube(c25); p25=probabilities(c25,cube25,net,beta); prep25={m:prep_month(c25,p25,m) for m in OP_MONTHS}; m25,t25=eval_year(prep25,cfg); met25=metric(m25,t25); result.update({'selectedTicketConfig':cfg,'design2024':{'score':list(sc),'months':{f'2024-{m:02d}':m24[m] for m in OP_MONTHS},'total':t24,**met24},'frozenEvaluation2025':{'months':{f'2025-{m:02d}':m25[m] for m in OP_MONTHS},'total':t25,**met25},'readyForFinalHoldout':bool(met24['targetMet'] and met25['targetMet'])})
    else:result['readyForFinalHoldout']=False
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    args.model_output.parent.mkdir(parents=True,exist_ok=True); np.savez_compressed(args.model_output,w1=net.w1,b1=net.b1,w2=net.w2,b2=np.asarray([net.b2],dtype=np.float32),mean=net.mean,std=net.std,beta=np.asarray([beta],dtype=np.float32),residualScale=np.asarray([RESIDUAL_SCALE],dtype=np.float32))
    print(json.dumps({'betaSelection':result['betaSelection'],'basicVolumeFeasible':result['basicVolumeFeasible'],'bestByVolume':result['bestByVolume'][:3],'selected':result.get('selectedTicketConfig'),'design2024':result.get('design2024'),'frozen2025':result.get('frozenEvaluation2025'),'readyForFinalHoldout':result['readyForFinalHoldout'],'holdoutOpened':False},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
