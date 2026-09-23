#!/usr/bin/env python3
"""Race-softmax residual model using raw 6x32 preview-enhanced racer features.

Protocol:
- Train weights on 2023 May-Aug rich pre-race data only.
- 2023 Sep is used only for early stopping.
- 2024 May-Sep selects market-shrink beta by log-loss and a small fixed ticket grid.
- Freeze weights, beta, ticket config and evaluate 2025 May-Sep once.
- 2025 Oct-Dec is never loaded and remains the pristine final holdout.

Unlike earlier models, each trifecta combo sees the actual 32-feature vectors of its
1st/2nd/3rd candidate racers plus their pairwise numeric differences and market/model
signals. The output is still a single residual added to market log-probability, and all
120 combos are normalized together within each race.
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_race_softmax_residual_2023_2025 as base

TRAIN_MONTHS=(5,6,7,8)
VAL_MONTH=9
OP_MONTHS=base.OP_MONTHS
EPS=base.EPS
HIDDEN=32
RESIDUAL_SCALE=1.50
L2=5e-4
LR=0.0025
MAX_EPOCHS=30
PATIENCE=5
BATCH_RACES=96
BETAS=(0.25,0.50,0.75,1.00)


class RichCache:
    def __init__(self,path:Path):
        z=np.load(path,allow_pickle=False)
        self.year=int(z['year'][0]); self.combos=z['combos']; self.month=z['month'].astype(np.int8)
        self.actual=z['actual_index'].astype(np.int64); self.amount=z['amount'].astype(np.int64)
        self.model_p=z['model_p'].astype(np.float32); self.market_p=z['market_p'].astype(np.float32); self.odds=z['odds'].astype(np.float32)
        self.racer=z['racer_features'].astype(np.float32)
        if self.racer.shape[1:]!=(6,32): raise RuntimeError(f'bad racer feature shape {self.racer.shape}')
        parsed=np.asarray([[int(x) for x in str(c).split('-')] for c in self.combos],dtype=np.int8)-1
        self.first=parsed[:,0]; self.second=parsed[:,1]; self.third=parsed[:,2]
        self.model_rank=self._ranks(self.model_p); self.market_rank=self._ranks(self.market_p)
    @staticmethod
    def _ranks(prob:np.ndarray)->np.ndarray:
        order=np.argsort(-prob,axis=1); out=np.empty_like(order,dtype=np.int16)
        vals=np.broadcast_to(np.arange(1,prob.shape[1]+1,dtype=np.int16),order.shape); np.put_along_axis(out,order,vals,axis=1); return out


def load_cache(cache_dir:Path,year:int)->RichCache:
    c=RichCache(cache_dir/f'signal_cache_{year}.npz')
    if c.year!=year: raise RuntimeError(f'cache year mismatch {c.year} != {year}')
    return c


def combo_features(cache:RichCache,rows:np.ndarray)->np.ndarray:
    rf=cache.racer[rows]
    f1=rf[:,cache.first,:]; f2=rf[:,cache.second,:]; f3=rf[:,cache.third,:]
    model=np.maximum(cache.model_p[rows].astype(np.float32),EPS)
    market=np.maximum(cache.market_p[rows].astype(np.float32),EPS)
    odds=cache.odds[rows].astype(np.float32); safe=np.where(odds>1.0,np.minimum(odds,200.0),200.0).astype(np.float32)
    mr=cache.model_rank[rows].astype(np.float32); kr=cache.market_rank[rows].astype(np.float32)
    ratio=np.log(model/market).astype(np.float32)
    compact=np.stack([
        np.log(market),np.log(model),ratio,np.log(safe),mr/120.0,kr/120.0,(kr-mr)/120.0,
        (mr<=5).astype(np.float32),(kr<=5).astype(np.float32),(mr<=10).astype(np.float32),(kr<=10).astype(np.float32),
        (mr<=20).astype(np.float32),(kr<=20).astype(np.float32),(odds<=1.0).astype(np.float32),
    ],axis=2).astype(np.float32)
    # First eight entries are continuous racer metrics; pairwise deltas give the net
    # strength relationships without exploding the feature count.
    deltas=np.concatenate([f1[:,:,:8]-f2[:,:,:8],f1[:,:,:8]-f3[:,:,:8],f2[:,:,:8]-f3[:,:,:8]],axis=2).astype(np.float32)
    return np.concatenate([compact,f1,f2,f3,deltas],axis=2).astype(np.float32)


def feature_moments(cache:RichCache,rows:np.ndarray)->tuple[np.ndarray,np.ndarray]:
    total=None; sq=None; count=0
    for start in range(0,len(rows),BATCH_RACES):
        x=combo_features(cache,rows[start:start+BATCH_RACES]).astype(np.float64)
        s=x.sum(axis=(0,1)); q=(x*x).sum(axis=(0,1)); n=x.shape[0]*x.shape[1]
        total=s if total is None else total+s; sq=q if sq is None else sq+q; count+=n
    mean=total/count; var=np.maximum(sq/count-mean*mean,1e-8); std=np.sqrt(var)
    std=np.where(std<1e-4,1.0,std)
    return mean.astype(np.float32),std.astype(np.float32)


def softmax(scores:np.ndarray)->np.ndarray:
    x=scores-scores.max(axis=1,keepdims=True); e=np.exp(x); return e/np.maximum(e.sum(axis=1,keepdims=True),EPS)


@dataclass
class Net:
    w1:np.ndarray; b1:np.ndarray; w2:np.ndarray; b2:float; mean:np.ndarray; std:np.ndarray
    def residual(self,x:np.ndarray)->np.ndarray:
        z=(x-self.mean)/self.std; h=np.tanh(z@self.w1+self.b1); raw=h@self.w2+self.b2; return RESIDUAL_SCALE*np.tanh(raw)


def probability_rows(cache:RichCache,net:Net,rows:np.ndarray,beta:float)->np.ndarray:
    out=np.empty((len(rows),120),dtype=np.float64)
    for start in range(0,len(rows),BATCH_RACES):
        rr=rows[start:start+BATCH_RACES]; x=combo_features(cache,rr); b=len(rr); d=x.shape[2]
        residual=net.residual(x.reshape(-1,d)).reshape(b,120)
        logits=np.log(np.maximum(cache.market_p[rr].astype(np.float64),EPS))+float(beta)*residual
        out[start:start+b]=softmax(logits)
    return out


def all_probabilities(cache:RichCache,net:Net,beta:float)->np.ndarray:
    return probability_rows(cache,net,np.arange(len(cache.month)),beta)


def logloss(cache:RichCache,p:np.ndarray,months:tuple[int,...])->float:
    rows=np.where(np.isin(cache.month,months))[0]; return float(-np.log(np.clip(p[rows,cache.actual[rows]],EPS,1.0)).mean())


def train(cache:RichCache)->tuple[Net,list[dict[str,Any]]]:
    train_rows=np.where(np.isin(cache.month,TRAIN_MONTHS))[0]; val_rows=np.where(cache.month==VAL_MONTH)[0]
    mean,std=feature_moments(cache,train_rows)
    sample=combo_features(cache,train_rows[:1]); d=sample.shape[2]
    rng=np.random.default_rng(20260923)
    w1=(rng.standard_normal((d,HIDDEN))*0.02).astype(np.float32); b1=np.zeros(HIDDEN,dtype=np.float32); w2=(rng.standard_normal(HIDDEN)*0.02).astype(np.float32); b2=np.float32(0)
    params=[w1,b1,w2]; m=[np.zeros_like(x) for x in params]; v=[np.zeros_like(x) for x in params]; mb=np.float32(0); vb=np.float32(0); step=0
    best=None; best_loss=float('inf'); stale=0; history=[]
    for epoch in range(1,MAX_EPOCHS+1):
        order=rng.permutation(train_rows); epoch_loss=0.0; batches=0
        for start in range(0,len(order),BATCH_RACES):
            rows=order[start:start+BATCH_RACES]; rawx=combo_features(cache,rows); x=((rawx-mean)/std).astype(np.float32); b,k,d=x.shape; flat=x.reshape(-1,d)
            h=np.tanh(flat@w1+b1).reshape(b,k,HIDDEN); raw=(h.reshape(-1,HIDDEN)@w2+b2).reshape(b,k); tr=np.tanh(raw); residual=RESIDUAL_SCALE*tr
            logits=np.log(np.maximum(cache.market_p[rows].astype(np.float64),EPS))+residual; p=softmax(logits); actual=cache.actual[rows]
            loss=float(-np.log(np.clip(p[np.arange(b),actual],EPS,1)).mean()); epoch_loss+=loss; batches+=1
            ds=p; ds[np.arange(b),actual]-=1; ds/=b; dz=ds*RESIDUAL_SCALE*(1-tr*tr); dzf=dz.reshape(-1)
            hf=h.reshape(-1,HIDDEN); gw2=(hf.T@dzf).astype(np.float32)+L2*w2; gb2=np.float32(dzf.sum()); dh=(dzf[:,None]*w2[None,:]).reshape(b,k,HIDDEN); da=dh*(1-h*h); daf=da.reshape(-1,HIDDEN)
            gw1=(flat.T@daf).astype(np.float32)+L2*w1; gb1=daf.sum(axis=0).astype(np.float32); grads=[gw1,gb1,gw2]; step+=1
            for i,(param,g) in enumerate(zip(params,grads)):
                m[i]=.9*m[i]+.1*g; v[i]=.999*v[i]+.001*g*g; mh=m[i]/(1-.9**step); vh=v[i]/(1-.999**step); param-=LR*mh/(np.sqrt(vh)+1e-8)
            mb=np.float32(.9*mb+.1*gb2); vb=np.float32(.999*vb+.001*gb2*gb2); b2=np.float32(b2-LR*(mb/(1-.9**step))/(np.sqrt(vb/(1-.999**step))+1e-8))
        net=Net(w1.copy(),b1.copy(),w2.copy(),float(b2),mean,std); pv=probability_rows(cache,net,val_rows,1.0); val=float(-np.log(np.clip(pv[np.arange(len(val_rows)),cache.actual[val_rows]],EPS,1)).mean())
        market=cache.market_p[val_rows].astype(np.float64); market/=np.maximum(market.sum(axis=1,keepdims=True),EPS); mll=float(-np.log(np.clip(market[np.arange(len(val_rows)),cache.actual[val_rows]],EPS,1)).mean())
        row={'epoch':epoch,'trainLoss':round(epoch_loss/max(1,batches),8),'validationLogLoss':round(val,8),'marketValidationLogLoss':round(mll,8)}; history.append(row); print(row,flush=True)
        if val<best_loss-1e-5: best_loss=val; best=(w1.copy(),b1.copy(),w2.copy(),float(b2)); stale=0
        else:
            stale+=1
            if stale>=PATIENCE: break
    if best is None: raise RuntimeError('no checkpoint')
    return Net(best[0],best[1],best[2],best[3],mean,std),history


def select_beta(cache:RichCache,net:Net)->tuple[float,list[dict[str,float]],np.ndarray]:
    trials=[]; bestp=None
    for beta in BETAS:
        p=all_probabilities(cache,net,beta); ll=logloss(cache,p,OP_MONTHS); trials.append({'beta':beta,'logLoss':round(ll,8)})
    trials.sort(key=lambda x:x['logLoss']); beta=float(trials[0]['beta']); bestp=all_probabilities(cache,net,beta); return beta,trials,bestp


def main()->None:
    ap=argparse.ArgumentParser(); ap.add_argument('--cache-dir',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); ap.add_argument('--model-output',type=Path,required=True); args=ap.parse_args()
    c23=load_cache(args.cache_dir,2023); c24=load_cache(args.cache_dir,2024); c25=load_cache(args.cache_dir,2025)
    net,history=train(c23); beta,trials,p24=select_beta(c24,net)
    market24=c24.market_p.astype(np.float64); market24/=np.maximum(market24.sum(axis=1,keepdims=True),EPS); market_ll=logloss(c24,market24,OP_MONTHS); adj_ll=logloss(c24,p24,OP_MONTHS)
    prep24={m:base.prep_month(c24,p24,m) for m in OP_MONTHS}; ranked=[]; diag=[]
    for cfg in base.configs():
        m,t=base.eval_year(prep24,cfg); mm=min(x['purchaseRaces'] for x in m.values()); met=base.metric(m,t); diag.append({'config':cfg,'minMonthBuys':mm,'total':t,**met})
        if t['purchaseRaces']>=base.DESIGN_MIN_TOTAL_BUYS and mm>=base.DESIGN_MIN_MONTH_BUYS: ranked.append((base.score(m,t),cfg,m,t))
    diag.sort(key=lambda x:(x['minMonthBuys'],x['total']['purchaseRaces'],x['positiveMonths'],x['worstMonthRoi'],x['total']['roi']),reverse=True)
    result:dict[str,Any]={'schemaVersion':23,'generatedAt':datetime.now(timezone.utc).isoformat(),'researchOnly':True,'releaseQualified':False,'method':'market-base race-softmax residual MLP with raw 1st/2nd/3rd racer 32-feature vectors','model':{'trainingPeriod':'2023-05-01..2023-08-31','earlyStop':'2023-09','hidden':HIDDEN,'residualScale':RESIDUAL_SCALE,'l2':L2,'epochsRun':len(history),'inputDimension':int(net.w1.shape[0]),'bestValidationLogLoss':min(x['validationLogLoss'] for x in history)},'trainingHistory':history,'betaSelection':{'selected':beta,'trials':trials,'market2024LogLoss':round(market_ll,8),'adjusted2024LogLoss':round(adj_ll,8),'improved':bool(adj_ll<market_ll)},'basicVolumeFeasible':bool(ranked),'bestByVolume':diag[:10],'holdoutPolicy':{'reserved':'2025-10-01..2025-12-31','opened':False}}
    if ranked:
        ranked.sort(key=lambda x:x[0],reverse=True); sc,cfg,m24,t24=ranked[0]; met24=base.metric(m24,t24); p25=all_probabilities(c25,net,beta); prep25={m:base.prep_month(c25,p25,m) for m in OP_MONTHS}; m25,t25=base.eval_year(prep25,cfg); met25=base.metric(m25,t25); result.update({'selectedTicketConfig':cfg,'design2024':{'score':list(sc),'months':{f'2024-{m:02d}':m24[m] for m in OP_MONTHS},'total':t24,**met24},'frozenEvaluation2025':{'months':{f'2025-{m:02d}':m25[m] for m in OP_MONTHS},'total':t25,**met25},'readyForFinalHoldout':bool(met24['targetMet'] and met25['targetMet'])})
    else: result['readyForFinalHoldout']=False
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    args.model_output.parent.mkdir(parents=True,exist_ok=True); np.savez_compressed(args.model_output,w1=net.w1,b1=net.b1,w2=net.w2,b2=np.asarray([net.b2],dtype=np.float32),mean=net.mean,std=net.std,beta=np.asarray([beta],dtype=np.float32),residualScale=np.asarray([RESIDUAL_SCALE],dtype=np.float32))
    print(json.dumps({'betaSelection':result['betaSelection'],'basicVolumeFeasible':result['basicVolumeFeasible'],'bestByVolume':result['bestByVolume'][:3],'selected':result.get('selectedTicketConfig'),'design2024':result.get('design2024'),'frozen2025':result.get('frozenEvaluation2025'),'readyForFinalHoldout':result['readyForFinalHoldout'],'holdoutOpened':False},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
