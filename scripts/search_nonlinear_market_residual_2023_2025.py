#!/usr/bin/env python3
"""Nonlinear market-residual strategy with a frozen 2025 evaluation.

Protocol
--------
* Train ONE strongly regularized HistGradientBoosting binary residual model on
  preview-enhanced 2023 May-Sep combo rows.
* 2024 May-Sep selects only the market-shrink beta (by race log-loss) and a small,
  pre-declared ticket grid. Model weights are never refit on 2024.
* Freeze model, beta, and ticket config; evaluate 2025 May-Sep once.
* 2025 Oct-Dec is never loaded and remains the pristine final holdout.

The model is deliberately small and interpretable at the feature level. It uses only
pre-race model probability, archived market probability/odds, their ranks/ratio, and
trifecta lane structure. No venue/month identifiers are included.
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from sklearn.ensemble import HistGradientBoostingClassifier

import search_multiyear_strategy_v14 as v14

MONTHS = (5, 6, 7, 8, 9)
BUDGET = 1200
BUDGET_UNITS = 12
MAX_ODDS_DOMAIN = 80.0

BETAS = (0.25, 0.50, 0.75, 1.00)
MIN_EV_OPTIONS = (1.02, 1.05, 1.08, 1.10, 1.15)
MIN_PROB_OPTIONS = (0.003, 0.005, 0.010, 0.020)
MAX_ODDS_OPTIONS = (20.0, 40.0, 80.0)
MAX_POINTS_OPTIONS = (1, 2, 3)

DESIGN_MIN_TOTAL_BUYS = 100
DESIGN_MIN_MONTH_BUYS = 10
TARGET_MIN_TOTAL_BUYS = 100
TARGET_MIN_MONTH_BUYS = 10
TARGET_MIN_ROI = 105.0
TARGET_MIN_POSITIVE_MONTHS = 4
TARGET_MIN_WORST_ROI = 90.0
TARGET_MAX_LARGEST_HIT_SHARE = 25.0

EPS = 1e-8


def load_cache(cache_dir: Path, year: int) -> v14.Cache:
    path = cache_dir / f"signal_cache_{year}.npz"
    if not path.exists():
        raise FileNotFoundError(path)
    cache = v14.Cache(path)
    if cache.year != year:
        raise RuntimeError(f"cache year mismatch: {cache.year} != {year}")
    return cache


def ranks(prob: np.ndarray) -> np.ndarray:
    order = np.argsort(-prob, axis=1)
    out = np.empty_like(order, dtype=np.int16)
    vals = np.broadcast_to(np.arange(1, prob.shape[1] + 1, dtype=np.int16), order.shape)
    np.put_along_axis(out, order, vals, axis=1)
    return out


def combo_lanes(combos: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    parsed = np.asarray([[int(x) for x in str(combo).split('-')] for combo in combos], dtype=np.int8)
    return parsed[:, 0], parsed[:, 1], parsed[:, 2]


def domain(cache: v14.Cache) -> np.ndarray:
    return (
        (cache.market_p > 0.0)
        & (cache.model_p > 0.0)
        & (cache.odds > 1.0)
        & (cache.odds <= MAX_ODDS_DOMAIN)
    )


def feature_cube(cache: v14.Cache) -> np.ndarray:
    model = np.maximum(cache.model_p.astype(np.float64), EPS)
    market = np.maximum(cache.market_p.astype(np.float64), EPS)
    odds = np.maximum(cache.odds.astype(np.float64), 1.0001)
    mrank = ranks(model).astype(np.float64)
    krank = ranks(market).astype(np.float64)
    ratio_log = np.log(model / market)
    first, second, third = combo_lanes(cache.combos)
    n, k = model.shape

    first_oh = np.eye(6, dtype=np.float32)[first - 1]
    second_oh = np.eye(6, dtype=np.float32)[second - 1]
    third_oh = np.eye(6, dtype=np.float32)[third - 1]
    f1 = np.broadcast_to(first_oh[None, :, :], (n, k, 6))
    f2 = np.broadcast_to(second_oh[None, :, :], (n, k, 6))
    f3 = np.broadcast_to(third_oh[None, :, :], (n, k, 6))

    numeric = np.stack([
        np.log(market),
        np.log(model),
        ratio_log,
        np.log(odds),
        mrank / 120.0,
        krank / 120.0,
        (krank - mrank) / 120.0,
        (mrank <= 5).astype(np.float64),
        (krank <= 5).astype(np.float64),
        (mrank <= 10).astype(np.float64),
        (krank <= 10).astype(np.float64),
        (mrank <= 20).astype(np.float64),
        (krank <= 20).astype(np.float64),
        ratio_log * (first[None, :] == 1),
        ratio_log * (first[None, :] >= 4),
        np.log(odds) * (first[None, :] == 1),
        np.log(odds) * (first[None, :] >= 4),
    ], axis=2).astype(np.float32)
    return np.concatenate([numeric, f1, f2, f3], axis=2).astype(np.float32)


def training_rows(cache: v14.Cache) -> tuple[np.ndarray, np.ndarray]:
    cube = feature_cube(cache)
    valid = domain(cache) & np.isin(cache.month, MONTHS)[:, None]
    row_idx, combo_idx = np.where(valid)
    x = cube[row_idx, combo_idx]
    y = (combo_idx == cache.actual[row_idx]).astype(np.int8)
    return x, y


def fit_model(cache: v14.Cache) -> HistGradientBoostingClassifier:
    x, y = training_rows(cache)
    positives = int(y.sum())
    if positives < 1000 or len(y) < 500_000:
        raise RuntimeError(f"training set unexpectedly sparse rows={len(y)} positives={positives}")
    model = HistGradientBoostingClassifier(
        loss="log_loss",
        learning_rate=0.045,
        max_iter=120,
        max_leaf_nodes=15,
        max_depth=5,
        min_samples_leaf=250,
        l2_regularization=5.0,
        early_stopping=True,
        validation_fraction=0.10,
        n_iter_no_change=12,
        random_state=20260923,
    )
    model.fit(x, y)
    return model


def raw_predictions(cache: v14.Cache, model: HistGradientBoostingClassifier) -> np.ndarray:
    cube = feature_cube(cache)
    valid = domain(cache)
    out = cache.market_p.astype(np.float64).copy()
    row_idx, combo_idx = np.where(valid)
    pred = model.predict_proba(cube[row_idx, combo_idx])[:, 1]
    out[row_idx, combo_idx] = np.clip(pred, EPS, 1.0 - EPS)
    return out


def shrink_to_market(cache: v14.Cache, raw: np.ndarray, beta: float) -> np.ndarray:
    market = np.maximum(cache.market_p.astype(np.float64), EPS)
    valid = domain(cache)
    # Treat the nonlinear model only as a multiplicative market residual, shrink it,
    # then renormalize to a proper 120-way probability distribution per race.
    lift = np.ones_like(market)
    lift[valid] = np.clip(raw[valid] / market[valid], 0.25, 4.0)
    adjusted = market * np.power(lift, float(beta))
    total = adjusted.sum(axis=1, keepdims=True)
    return adjusted / np.maximum(total, EPS)


def race_logloss(cache: v14.Cache, p: np.ndarray) -> float:
    mask = np.isin(cache.month, MONTHS)
    rows = np.where(mask)[0]
    actual_p = p[rows, cache.actual[rows]]
    return float(-np.log(np.clip(actual_p, EPS, 1.0)).mean())


def select_beta(cache: v14.Cache, raw: np.ndarray) -> tuple[float, list[dict[str, float]]]:
    trials=[]
    for beta in BETAS:
        p=shrink_to_market(cache,raw,beta)
        trials.append({"beta":beta,"logLoss":round(race_logloss(cache,p),8)})
    trials.sort(key=lambda row:row["logLoss"])
    return float(trials[0]["beta"]),trials


def prepared(cache: v14.Cache, p: np.ndarray, month: int) -> dict[str, np.ndarray]:
    mask=cache.month==month
    prob=p[mask]
    odds=cache.odds[mask].astype(np.float64)
    ev=prob*odds
    order=np.argsort(-ev,axis=1)
    return {
        "p":np.take_along_axis(prob,order,axis=1),
        "ev":np.take_along_axis(ev,order,axis=1),
        "odds":np.take_along_axis(odds,order,axis=1),
        "comboIndex":order,
        "actual":cache.actual[mask],
        "amount":cache.amount[mask].astype(np.int64),
    }


def config_grid() -> list[dict[str,Any]]:
    return [
        {"minEv":ev,"minProbability":prob,"maxOdds":odds,"maxPoints":pts,"budget":BUDGET}
        for ev in MIN_EV_OPTIONS
        for prob in MIN_PROB_OPTIONS
        for odds in MAX_ODDS_OPTIONS
        for pts in MAX_POINTS_OPTIONS
    ]


def finalize(buys:int,hits:int,payout:int,bets:int,largest:int)->dict[str,Any]:
    stake=buys*BUDGET
    return {
        "purchaseRaces":buys,"hits":hits,"stake":stake,"payout":payout,
        "profit":payout-stake,"roi":round(payout*100.0/stake,1) if stake else 0.0,
        "hitRate":round(hits*100.0/buys,1) if buys else 0.0,
        "bets":bets,"avgPoints":round(bets/buys,2) if buys else 0.0,
        "largestHitPayout":largest,
        "largestHitShare":round(largest*100.0/payout,1) if payout else 0.0,
    }


def evaluate_month(data:dict[str,np.ndarray],cfg:dict[str,Any])->dict[str,Any]:
    eligible=(data["ev"]>=cfg["minEv"])&(data["p"]>=cfg["minProbability"])&(data["odds"]>1.0)&(data["odds"]<=cfg["maxOdds"])
    rank=np.cumsum(eligible,axis=1)
    take=eligible&(rank<=cfg["maxPoints"])
    count=take.sum(axis=1).astype(np.int64)
    buy=count>0
    buys=int(buy.sum())
    if not buys:return finalize(0,0,0,0,0)
    base=np.zeros(len(count),dtype=np.int64); base[buy]=BUDGET_UNITS//count[buy]
    rem=np.zeros(len(count),dtype=np.int64); rem[buy]=BUDGET_UNITS-base[buy]*count[buy]
    units=np.where(take,base[:,None]+((rank<=rem[:,None])&take).astype(np.int64),0)
    actual_match=data["comboIndex"]==data["actual"][:,None]
    actual_units=(units*actual_match).sum(axis=1).astype(np.int64)
    race_payout=data["amount"]*actual_units
    return finalize(buys,int((actual_units>0).sum()),int(race_payout.sum()),int(count[buy].sum()),int(race_payout.max(initial=0)))


def evaluate_year(prep:dict[int,dict[str,np.ndarray]],cfg:dict[str,Any])->tuple[dict[int,dict[str,Any]],dict[str,Any]]:
    monthly={m:evaluate_month(prep[m],cfg) for m in MONTHS}
    rows=list(monthly.values())
    buys=sum(r["purchaseRaces"] for r in rows); hits=sum(r["hits"] for r in rows)
    payout=sum(r["payout"] for r in rows); bets=sum(r["bets"] for r in rows)
    largest=max((r["largestHitPayout"] for r in rows),default=0)
    return monthly,finalize(buys,hits,payout,bets,largest)


def metrics(monthly:dict[int,dict[str,Any]],total:dict[str,Any])->dict[str,Any]:
    rows=list(monthly.values())
    positive=sum(r["purchaseRaces"]>0 and r["profit"]>0 for r in rows)
    worst=min((r["roi"] for r in rows),default=0.0)
    volume=all(r["purchaseRaces"]>=TARGET_MIN_MONTH_BUYS for r in rows)
    target=bool(total["purchaseRaces"]>=TARGET_MIN_TOTAL_BUYS and total["roi"]>=TARGET_MIN_ROI and positive>=TARGET_MIN_POSITIVE_MONTHS and worst>=TARGET_MIN_WORST_ROI and total["largestHitShare"]<=TARGET_MAX_LARGEST_HIT_SHARE and volume)
    return {"positiveMonths":positive,"worstMonthRoi":worst,"volumeOk":volume,"targetMet":target}


def design_score(monthly:dict[int,dict[str,Any]],total:dict[str,Any])->tuple[Any,...]:
    m=metrics(monthly,total)
    return (m["positiveMonths"],m["worstMonthRoi"],-total["largestHitShare"],total["roi"],total["purchaseRaces"])


def main()->None:
    ap=argparse.ArgumentParser(); ap.add_argument('--cache-dir',type=Path,required=True); ap.add_argument('--output',type=Path,required=True); args=ap.parse_args()
    c23=load_cache(args.cache_dir,2023); c24=load_cache(args.cache_dir,2024); c25=load_cache(args.cache_dir,2025)
    model=fit_model(c23)
    raw24=raw_predictions(c24,model)
    beta,beta_trials=select_beta(c24,raw24)
    p24=shrink_to_market(c24,raw24,beta)
    market24=c24.market_p.astype(np.float64); market24/=np.maximum(market24.sum(axis=1,keepdims=True),EPS)
    market_ll=race_logloss(c24,market24); model_ll=race_logloss(c24,p24)
    prep24={m:prepared(c24,p24,m) for m in MONTHS}

    ranked=[]; diagnostics=[]
    for cfg in config_grid():
        mon,total=evaluate_year(prep24,cfg); min_month=min(r["purchaseRaces"] for r in mon.values())
        diagnostics.append({"config":cfg,"minMonthBuys":min_month,"total":total,**metrics(mon,total)})
        if total["purchaseRaces"]>=DESIGN_MIN_TOTAL_BUYS and min_month>=DESIGN_MIN_MONTH_BUYS:
            ranked.append((design_score(mon,total),cfg,mon,total))
    diagnostics.sort(key=lambda r:(r["minMonthBuys"],r["total"]["purchaseRaces"],r["positiveMonths"],r["worstMonthRoi"],r["total"]["roi"]),reverse=True)

    result:dict[str,Any]={
        "schemaVersion":21,"generatedAt":datetime.now(timezone.utc).isoformat(),"researchOnly":True,"releaseQualified":False,
        "method":"strongly regularized nonlinear combo classifier trained on 2023 preview-era data, shrunk to market by 2024 log-loss, ticket config designed on 2024 and frozen for 2025",
        "model":{"type":"HistGradientBoostingClassifier","trainingPeriod":"2023-05-01..2023-09-30","maxLeafNodes":15,"maxDepth":5,"l2":5.0,"iterations":int(getattr(model,'n_iter_',0))},
        "betaSelection":{"selected":beta,"trials":beta_trials,"market2024LogLoss":round(market_ll,8),"adjusted2024LogLoss":round(model_ll,8),"improved":bool(model_ll<market_ll)},
        "basicVolumeFeasible":bool(ranked),"bestByVolume":diagnostics[:10],
        "holdoutPolicy":{"reserved":"2025-10-01..2025-12-31","opened":False},
    }
    if ranked:
        ranked.sort(key=lambda x:x[0],reverse=True); score,cfg,m24,t24=ranked[0]; met24=metrics(m24,t24)
        raw25=raw_predictions(c25,model); p25=shrink_to_market(c25,raw25,beta); prep25={m:prepared(c25,p25,m) for m in MONTHS}; m25,t25=evaluate_year(prep25,cfg); met25=metrics(m25,t25)
        result.update({"selectedTicketConfig":cfg,"design2024":{"score":list(score),"months":{f'2024-{m:02d}':m24[m] for m in MONTHS},"total":t24,**met24},"frozenEvaluation2025":{"months":{f'2025-{m:02d}':m25[m] for m in MONTHS},"total":t25,**met25},"readyForFinalHoldout":bool(met24["targetMet"] and met25["targetMet"])})
    else: result["readyForFinalHoldout"]=False
    args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    print(json.dumps({"betaSelection":result["betaSelection"],"basicVolumeFeasible":result["basicVolumeFeasible"],"bestByVolume":result["bestByVolume"][:3],"selected":result.get("selectedTicketConfig"),"design2024":result.get("design2024"),"frozen2025":result.get("frozenEvaluation2025"),"readyForFinalHoldout":result["readyForFinalHoldout"],"holdoutOpened":False},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
