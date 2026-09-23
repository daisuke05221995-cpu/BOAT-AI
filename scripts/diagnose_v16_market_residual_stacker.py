#!/usr/bin/env python3
"""Regularized market-residual stacker feasibility diagnostic.

Only 2023 Feb-Apr outcomes are used:
- Feb-Mar fit candidate regularization strengths.
- Apr chooses L2 by log-loss, never ROI.
- Feb-Apr refit the selected stacker.
- May-Sep outcomes are NOT read; only candidate EV availability is measured.
- 2024/2025 and reserved 2025-Q4 are not loaded.

The model keeps normalized market probability as the base logit and learns small,
regularized corrections from BOAT-AI-vs-market residual and lane-position biases.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

import search_multiyear_strategy_v14 as v14

TRAIN_MONTHS=(2,3)
VALID_MONTHS=(4,)
REFIT_MONTHS=(2,3,4)
CANDIDATE_MONTHS=(5,6,7,8,9)
L2_OPTIONS=(0.02,0.05,0.10,0.25,0.50,1.00,2.00)
EPOCHS=90
LR=0.04
EV_THRESHOLDS=(0.95,1.00,1.02,1.05,1.10,1.20)
MAX_ODDS_LEVELS=(20.0,40.0,80.0,150.0)
MIN_PROBABILITY=0.005
EPS=1e-12


def combo_meta(combos:np.ndarray)->tuple[np.ndarray,np.ndarray,np.ndarray,np.ndarray]:
    first=[]; second=[]; third=[]; group=[]
    for raw in combos.tolist():
        a,b,c=[int(x) for x in str(raw).split('-')]
        first.append(a-1); second.append(b-1); third.append(c-1)
        group.append(0 if a==1 else 1 if a in (2,3) else 2)
    return tuple(np.asarray(x,dtype=np.int8) for x in (first,second,third,group))


def softmax(logits:np.ndarray)->np.ndarray:
    shifted=logits-logits.max(axis=1,keepdims=True)
    values=np.exp(np.clip(shifted,-40.0,40.0))
    total=values.sum(axis=1,keepdims=True)
    return np.divide(values,total,out=np.zeros_like(values),where=total>0.0)


def params_size()->int:
    return 2+6+6+6+3


def correction(theta:np.ndarray,residual:np.ndarray,meta:tuple[np.ndarray,np.ndarray,np.ndarray,np.ndarray])->np.ndarray:
    first,second,third,group=meta
    idx=0
    b1=theta[idx]; idx+=1
    b2=theta[idx]; idx+=1
    fb=theta[idx:idx+6]; idx+=6
    sb=theta[idx:idx+6]; idx+=6
    tb=theta[idx:idx+6]; idx+=6
    gb=theta[idx:idx+3]
    return (
        b1*residual + b2*(residual*residual) +
        fb[first][None,:] + sb[second][None,:] + tb[third][None,:] +
        gb[group][None,:]*residual
    )


def probabilities(theta:np.ndarray,model:np.ndarray,market:np.ndarray,meta)->np.ndarray:
    residual=np.clip(np.log(np.maximum(model,EPS))-np.log(np.maximum(market,EPS)),-4.0,4.0)
    logits=np.log(np.maximum(market,EPS))+correction(theta,residual,meta)
    return softmax(logits)


def loss(theta:np.ndarray,model:np.ndarray,market:np.ndarray,actual:np.ndarray,meta,l2:float=0.0)->float:
    p=probabilities(theta,model,market,meta)
    ll=-np.log(np.maximum(p[np.arange(len(actual)),actual],EPS)).mean()
    return float(ll+0.5*l2*np.square(theta).sum())


def gradient(theta:np.ndarray,model:np.ndarray,market:np.ndarray,actual:np.ndarray,meta,l2:float)->np.ndarray:
    first,second,third,group=meta
    residual=np.clip(np.log(np.maximum(model,EPS))-np.log(np.maximum(market,EPS)),-4.0,4.0)
    logits=np.log(np.maximum(market,EPS))+correction(theta,residual,meta)
    p=softmax(logits)
    diff=p
    diff[np.arange(len(actual)),actual]-=1.0
    n=max(1,len(actual))
    grad=np.zeros_like(theta)
    idx=0
    grad[idx]=np.sum(diff*residual)/n; idx+=1
    grad[idx]=np.sum(diff*residual*residual)/n; idx+=1
    for lane in range(6):
        grad[idx+lane]=np.sum(diff[:,first==lane])/n
    idx+=6
    for lane in range(6):
        grad[idx+lane]=np.sum(diff[:,second==lane])/n
    idx+=6
    for lane in range(6):
        grad[idx+lane]=np.sum(diff[:,third==lane])/n
    idx+=6
    for g in range(3):
        mask=group==g
        grad[idx+g]=np.sum(diff[:,mask]*residual[:,mask])/n
    grad+=l2*theta
    return grad


def fit(model:np.ndarray,market:np.ndarray,actual:np.ndarray,meta,l2:float)->np.ndarray:
    theta=np.zeros(params_size(),dtype=np.float64)
    m=np.zeros_like(theta); v=np.zeros_like(theta)
    beta1=0.9; beta2=0.999
    best=theta.copy(); best_loss=float('inf'); stale=0
    for epoch in range(1,EPOCHS+1):
        g=gradient(theta,model,market,actual,meta,l2)
        m=beta1*m+(1-beta1)*g
        v=beta2*v+(1-beta2)*(g*g)
        mh=m/(1-beta1**epoch); vh=v/(1-beta2**epoch)
        theta-=LR*mh/(np.sqrt(vh)+1e-8)
        # Remove softmax-unidentifiable mean lane offsets.
        theta[2:8]-=theta[2:8].mean()
        theta[8:14]-=theta[8:14].mean()
        theta[14:20]-=theta[14:20].mean()
        if epoch%5==0 or epoch==EPOCHS:
            current=loss(theta,model,market,actual,meta,l2)
            if current<best_loss-1e-6:
                best_loss=current; best=theta.copy(); stale=0
            else:
                stale+=1
                if stale>=5:
                    break
    return best


def subset(cache:v14.Cache,months:tuple[int,...]):
    mask=np.isin(cache.month,months)
    return cache.model_p[mask].astype(np.float64),cache.market_p[mask].astype(np.float64),cache.actual[mask]


def plain_logloss(market:np.ndarray,actual:np.ndarray)->float:
    return float(-np.log(np.maximum(market[np.arange(len(actual)),actual],EPS)).mean())


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument('--cache-dir',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    cache=v14.Cache(args.cache_dir/'signal_cache_2023.npz')
    if cache.year!=2023: raise SystemExit('2023 cache required')
    meta=combo_meta(cache.combos)
    train_model,train_market,train_actual=subset(cache,TRAIN_MONTHS)
    val_model,val_market,val_actual=subset(cache,VALID_MONTHS)

    trials=[]
    for l2 in L2_OPTIONS:
        theta=fit(train_model,train_market,train_actual,meta,l2)
        val_loss=loss(theta,val_model,val_market,val_actual,meta,0.0)
        trials.append({"l2":l2,"validationLogLoss":val_loss,"theta":theta})
        print(f'l2={l2:.2f} validationLogLoss={val_loss:.8f}',flush=True)
    trials.sort(key=lambda row:row['validationLogLoss'])
    selected_l2=float(trials[0]['l2'])

    refit_model,refit_market,refit_actual=subset(cache,REFIT_MONTHS)
    theta=fit(refit_model,refit_market,refit_actual,meta,selected_l2)
    calibration_loss=loss(theta,refit_model,refit_market,refit_actual,meta,0.0)
    market_calibration_loss=plain_logloss(refit_market,refit_actual)

    monthly={}; aggregate={f'ev{thr:.2f}':0 for thr in EV_THRESHOLDS}; max_ev=0.0
    for month in CANDIDATE_MONTHS:
        mask=cache.month==month
        # Deliberately do not read cache.actual for candidate months.
        model=cache.model_p[mask].astype(np.float64)
        market=cache.market_p[mask].astype(np.float64)
        odds=cache.odds[mask].astype(np.float64)
        p=probabilities(theta,model,market,meta)
        ev=p*odds
        max_ev=max(max_ev,float(ev.max(initial=0.0)))
        row={"races":int(len(ev)),"maxEv":round(float(ev.max(initial=0.0)),4)}
        for thr in EV_THRESHOLDS:
            candidate=(ev>=thr)&(p>=MIN_PROBABILITY)&(odds>0.0)
            key=f'ev{thr:.2f}'
            row[key]={"racesWithCandidate":int(candidate.any(axis=1).sum()),"candidateCombos":int(candidate.sum())}
            aggregate[key]+=row[key]['racesWithCandidate']
        row['byMaxOdds']={}
        for cap in MAX_ODDS_LEVELS:
            candidate=(ev>=1.02)&(p>=MIN_PROBABILITY)&(odds>0.0)&(odds<=cap)
            row['byMaxOdds'][str(int(cap))]={"racesWithCandidate":int(candidate.any(axis=1).sum()),"candidateCombos":int(candidate.sum())}
        monthly[f'2023-{month:02d}']=row

    result={
        "schemaVersion":1,
        "generatedAt":datetime.now(timezone.utc).isoformat(),
        "diagnosticOnly":True,
        "fitPeriod":"2023-02-01..2023-03-31",
        "regularizationSelectionPeriod":"2023-04-01..2023-04-30",
        "refitPeriod":"2023-02-01..2023-04-30",
        "candidatePeriod":"2023-05-01..2023-09-30",
        "candidateOutcomesRead":False,
        "evaluationYearsOpened":[],
        "reservedHoldoutOpened":False,
        "selectedL2":selected_l2,
        "l2Trials":[{"l2":float(row['l2']),"validationLogLoss":round(float(row['validationLogLoss']),8)} for row in trials],
        "marketValidationLogLoss":round(plain_logloss(val_market,val_actual),8),
        "stackerValidationLogLoss":round(float(trials[0]['validationLogLoss']),8),
        "marketRefitPeriodLogLoss":round(market_calibration_loss,8),
        "stackerRefitPeriodLogLoss":round(calibration_loss,8),
        "theta":[round(float(x),8) for x in theta.tolist()],
        "maxCalibratedEv":round(max_ev,4),
        "monthlyCandidateVolume":monthly,
        "aggregateRaceCounts":aggregate,
        "modelSpec":"log(market_p) base + regularized AI/market log-residual + 1st/2nd/3rd lane biases + residual-by-first-lane-group",
        "note":"May-Sep outcomes are not read. Diagnostic measures whether a log-loss-selected residual stacker creates actionable pre-race EV volume.",
    }
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({"selectedL2":selected_l2,"marketValidationLogLoss":result['marketValidationLogLoss'],"stackerValidationLogLoss":result['stackerValidationLogLoss'],"maxCalibratedEv":result['maxCalibratedEv'],"aggregateRaceCounts":aggregate,"monthlyCandidateVolume":monthly},ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
