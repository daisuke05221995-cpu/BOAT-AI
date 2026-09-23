#!/usr/bin/env python3
"""Bounded CORE BUY screen; never opens Q4 and never qualifies a release.

Only numpy is required. Each command is a separate Actions stage. Candidate
selection accepts 2023/2024 only; 2025 scoring requires the frozen manifest.
"""
from __future__ import annotations
import argparse
import hashlib
import itertools
import json
from datetime import date
from pathlib import Path
import numpy as np

FAMILIES = ('power', 'blend', 'calibration')
PARAMETERS = {'power': (1.10, 1.25), 'blend': (0.15, 0.35), 'calibration': (20., 100.)}
MONTHS = (5, 6, 7, 8, 9)
BUDGET = 1200
MIN_BUYS = 150  # 30/month equivalent, without requiring each month to buy
MIN_ANNUAL_BUYS = 360
HOLDOUT = '2025-10-01..2025-12-31'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(path, obj):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def canonical(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def load_cache(path, year):
    with np.load(path, allow_pickle=False) as z:
        # Inspect date axes BEFORE loading any outcome arrays. Fail closed.
        y = int(z['year'][0]); months = z['month']; days = z['day_ordinal']
        if y != year or not np.all((months >= 2) & (months <= 9)):
            raise ValueError('Only the pre-existing February-September caches are allowed')
        if not len(days) or any(date.fromordinal(int(d)).year != year or
                               date.fromordinal(int(d)).month != int(m)
                               for d, m in zip(days, months)):
            raise ValueError('Cache date/month mismatch')
        if year == 2025 and np.any(days >= date(2025, 10, 1).toordinal()):
            raise ValueError('Q4 holdout access forbidden')
        c = {k: z[k] for k in z.files}
    n = len(months)
    for key in ('model_p', 'market_p', 'odds'):
        if c[key].shape != (n, 120) or not np.all(np.isfinite(c[key])):
            raise ValueError(f'Invalid {key}')
    keys = np.stack([days, c['venue'], c['race_number']], axis=1)
    if len(np.unique(keys, axis=0)) != n:
        raise ValueError('Duplicate race key')
    if not np.all((c['actual_index'] >= 0) & (c['actual_index'] < 120)):
        raise ValueError('Invalid outcome index')
    if not np.all(c['amount'] > 0):
        raise ValueError('Invalid payout')
    return c


def normalize(p):
    p = np.maximum(p.astype(np.float64), 0)
    totals = p.sum(axis=1, keepdims=True)
    if np.any(totals <= 0): raise ValueError('Zero probability row')
    return p / totals


def cells(c):
    market = normalize(c['market_p']); model = normalize(c['model_p'])
    order = np.argsort(-market, axis=1, kind='stable')
    rank = np.empty_like(order)
    np.put_along_axis(rank, order, np.broadcast_to(np.arange(1,121), order.shape), axis=1)
    rank_bin = np.digitize(rank, [2, 4, 7, 11, 21, 41])
    lane = np.asarray([int(str(s).split('-')[0]) for s in c['combos']])
    lane_group = np.where(lane == 1, 0, np.where(lane <= 3, 1, 2))
    ratio = np.log(np.maximum(model, 1e-12) / np.maximum(market, 1e-12))
    ratio_bin = np.digitize(ratio, [-0.5, 0., 0.5])
    return (lane_group[None,:] * 7 + rank_bin) * 4 + ratio_bin


def fit(args):
    c = load_cache(args.cache, 2023)
    take = np.isin(c['month'], [2,3,4])
    cell = cells(c)[take]; market = normalize(c['market_p'])[take]
    actual = c['actual_index'][take]
    expected = np.bincount(cell.ravel(), weights=market.ravel(), minlength=84)
    wins = np.bincount(cell[np.arange(len(cell)), actual], minlength=84)
    models = {}
    for prior in PARAMETERS['calibration']:
        # Shrink toward the normalized market, not the observed maximum ROI.
        models[str(prior)] = np.clip((wins+prior)/(expected+prior), 0.5, 1.75).tolist()
    dump(args.output, {'trainingPeriod':'2023-02-01..2023-04-30', 'trainingRaces':int(take.sum()),
                       'cacheSha256':digest(args.cache), 'multipliers':models,
                       'cellDefinition':'first-lane group x market-rank bin x log(model/market) bin'})


def probabilities(c, family, parameter, model):
    market = normalize(c['market_p'])
    if family == 'power': return normalize(market ** parameter)
    if family == 'blend': return normalize((1-parameter)*market + parameter*normalize(c['model_p']))
    if family == 'calibration':
        return normalize(market*np.asarray(model['multipliers'][str(parameter)])[cells(c)])
    raise ValueError(family)


def prepare(args):
    c = load_cache(args.cache, args.year)
    model = json.loads(args.model.read_text())
    out = {k:c[k] for k in ('year','combos','month','day_ordinal','venue','race_number','actual_index','amount','odds')}
    for family in FAMILIES:
        for i, param in enumerate(PARAMETERS[family]):
            out[f'p_{family}_{i}'] = probabilities(c, family, param, model).astype(np.float32)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(args.output, **out)
    dump(args.output.with_suffix('.json'), {'year':args.year, 'cacheSha256':digest(args.cache),
         'calibrationSha256':digest(args.model), 'races':len(c['month']), 'holdoutOpened':False})


def configurations(family, cap):
    return [dict(family=family, parameterIndex=i, parameter=param, minEv=ev,
                 minProbability=prob, maxOdds=cap, maxPoints=points, budget=BUDGET)
            for (i,param), ev, prob, points in itertools.product(
                enumerate(PARAMETERS[family]), (1.,1.05,1.10), (.01,.03), (3,4))]


def tickets(p, odds, cfg):
    ev = p*odds
    eligible = (odds>1)&(odds<=cfg['maxOdds'])&(p>=cfg['minProbability'])&(ev>=cfg['minEv'])
    # Stable combination index breaks ties without access to race outcomes.
    order = np.argsort(-np.where(eligible, ev, -np.inf), axis=1, kind='stable')[:, :cfg['maxPoints']]
    selected = np.take_along_axis(eligible, order, axis=1)
    cnt = selected.sum(axis=1); buy = cnt>0
    basic = np.zeros(len(cnt), dtype=np.int64); rem = basic.copy()
    basic[buy] = 12//cnt[buy]; rem[buy] = 12%cnt[buy]
    units = selected * (basic[:,None] + (np.arange(cfg['maxPoints'])[None,:]<rem[:,None]))
    return order, units.astype(np.int64), cnt


def summarize(stake, payout, count):
    total_stake=int(stake.sum()); total_payout=int(payout.sum()); largest=int(payout.max(initial=0))
    bought=stake>0; buys=int(bought.sum())
    # Include initial zero in peak equity for the initial losing streak.
    equity=np.concatenate([[0],np.cumsum(payout-stake)])
    return {'purchaseRaces':buys, 'bets':int(count.sum()), 'hits':int((payout>0).sum()),
            'stake':total_stake,'payout':total_payout,'profit':total_payout-total_stake,
            'roi':100*total_payout/total_stake if total_stake else 0.,
            'largestHitShare':100*largest/total_payout if total_payout else 0.,
            'roiWithoutLargestHit':100*(total_payout-largest)/total_stake if total_stake else 0.,
            'maxDrawdown':int(np.max(np.maximum.accumulate(equity)-equity)),
            'payoutMinus5PercentRoi':95*total_payout/total_stake if total_stake else 0.}


def evaluate(c, cfg):
    mask=np.isin(c['month'], MONTHS)
    order_by_time=np.lexsort((c['race_number'][mask],c['venue'][mask],c['day_ordinal'][mask]))
    # Intraday order is venue/race order, not actual timestamps: drawdown is a diagnostic.
    data={k:c[k][mask][order_by_time] for k in ('month','actual_index','amount','odds')}
    p=c[f"p_{cfg['family']}_{cfg['parameterIndex']}"][mask][order_by_time].astype(np.float64)
    chosen, units, counts=tickets(p,data['odds'],cfg)
    winning_units=(units*(chosen==data['actual_index'][:,None])).sum(axis=1)
    stake=np.where(counts>0,BUDGET,0); payout=winning_units*data['amount']
    total=summarize(stake,payout,counts)
    monthly={str(m):summarize(stake[data['month']==m],payout[data['month']==m],counts[data['month']==m]) for m in MONTHS}
    return {'config':cfg,'total':total,'months':monthly,'screenPass':screen_pass(total)}


def screen_pass(total):
    # Annual gates will be applied only to complete 12-month data. This is a screen.
    return (total['purchaseRaces']>=MIN_BUYS and total['roi']>=105.
            and total['largestHitShare']<=25. and total['roiWithoutLargestHit']>=100.)


def load_prepared(path, year):
    with np.load(path, allow_pickle=False) as z:
        if int(z['year'][0])!=year: raise ValueError('Prepared year mismatch')
        if not np.all(np.isin(z['month'], range(2,10))): raise ValueError('Forbidden months')
        if year==2025 and np.any(z['day_ordinal']>=date(2025,10,1).toordinal()):
            raise ValueError('Q4 forbidden')
        return {k:z[k] for k in z.files}


def screen(args):
    if args.year not in (2023,2024): raise ValueError('2025 cannot enter candidate selection')
    c=load_prepared(args.cache,args.year)
    rows=[evaluate(c,cfg) for cfg in configurations(args.family,args.cap)]
    dump(args.output, {'year':args.year,'family':args.family,'cap':args.cap,
                      'preparedSha256':digest(args.cache),'rows':rows,'holdoutOpened':False})


def select(args):
    reports=[json.loads(p.read_text()) for p in sorted(args.input.glob('screen-*.json'))]
    expected={(y,f,cap) for y in (2023,2024) for f in FAMILIES for cap in (20,40)}
    actual=[(r['year'],r['family'],r['cap']) for r in reports]
    if len(actual)!=len(expected) or set(actual)!=expected: raise ValueError('Missing/duplicate matrix results')
    groups={}
    for r in reports:
        for row in r['rows']:
            groups.setdefault(canonical(row['config']),{})[str(r['year'])]=row
    eligible=[]; diagnostics=[]
    for key, ys in groups.items():
        if set(ys)!={'2023','2024'}: raise ValueError('Unpaired configuration')
        totals=[ys[y]['total'] for y in ('2023','2024')]
        item={'configHash':key,'config':ys['2023']['config'],'years':ys,
              'minRoi':min(t['roi'] for t in totals),
              'pooledRoi':100*sum(t['payout'] for t in totals)/max(1,sum(t['stake'] for t in totals))}
        diagnostics.append(item)
        if all(ys[y]['screenPass'] for y in ys): eligible.append(item)
    ranking=lambda r:(r['minRoi'],r['pooledRoi'],r['configHash'])
    eligible.sort(key=ranking,reverse=True); diagnostics.sort(key=ranking,reverse=True)
    result={'stage':'core-development-screen','researchOnly':True,'releaseQualified':False,
            'testedConfigurations':len(groups),'eligibleCount':len(eligible),
            'selected':eligible[0] if eligible else None,'bestDiagnostics':diagnostics[:10],
            'holdoutPolicy':{'reserved':HOLDOUT,'opened':False},
            'annualGate':{'roi':105,'minimumPurchaseRaces':MIN_ANNUAL_BUYS,'completeMonths':12,
                          'status':'NOT_EVALUATED'},
            'notes':['May-September is not annual performance.',
                     '2023/2024 are development years; 2025 pre-Q4 has been seen in older research.',
                     'Archived odds timing is not proven to match live 5-minute-before-close odds.',
                     'No monthly profit gate. No production file is modified.']}
    dump(args.output,result)
    manifest={'researchOnly':True,'status':'candidate-fixed-for-next-stage' if eligible else 'no-candidate',
              'selectedConfig':eligible[0]['config'] if eligible else None,
              'selectionReportSha256':digest(args.output),'modelSha256':digest(args.model),
              'sourceRun':args.run,'holdoutOpened':False,'annualQualified':False}
    manifest['manifestHash']=canonical(manifest)
    dump(args.manifest,manifest)
    print(json.dumps({'tested':len(groups),'eligible':len(eligible),'selected':manifest['selectedConfig']},ensure_ascii=False))


def confirm(args):
    manifest=json.loads(args.manifest.read_text()); saved=manifest.pop('manifestHash')
    if canonical(manifest)!=saved: raise ValueError('Manifest modified')
    cfg=manifest['selectedConfig']
    result={'stage':'core-frozen-2025-screen','candidateManifestHash':saved,
            'holdoutPolicy':{'reserved':HOLDOUT,'opened':False},'releaseQualified':False,
            'status':'NO_CANDIDATE','evaluation':None}
    if cfg:
        result['evaluation']=evaluate(load_prepared(args.cache,2025),cfg)
        result['status']='NEEDS_FULL_YEAR_VALIDATION' if result['evaluation']['screenPass'] else 'REJECTED_2025_SCREEN'
    dump(args.output,result)
    print(json.dumps(result,ensure_ascii=False))


def main():
    ap=argparse.ArgumentParser(); ap.add_argument('command',choices=['fit','prepare','screen','select','confirm'])
    ap.add_argument('--cache',type=Path); ap.add_argument('--model',type=Path); ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--year',type=int); ap.add_argument('--family',choices=FAMILIES); ap.add_argument('--cap',type=int,choices=[20,40])
    ap.add_argument('--input',type=Path); ap.add_argument('--manifest',type=Path); ap.add_argument('--run')
    args=ap.parse_args(); globals()[args.command](args)
if __name__=='__main__': main()
