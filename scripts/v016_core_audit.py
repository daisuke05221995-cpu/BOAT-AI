#!/usr/bin/env python3
"""Audit full matrix output and available periods without opening any new outcomes."""
import argparse
import json
from pathlib import Path
import numpy as np
import v016_core_research as core


def annual_gate(*, months, coverage_verified, roi, buys, out_of_time, odds_timing_verified):
    reasons=[]
    if set(months)!=set(range(1,13)): reasons.append('TWELVE_MONTHS_NOT_COVERED')
    if not coverage_verified: reasons.append('RACE_DENOMINATOR_NOT_VERIFIED')
    if roi is None: reasons.append('ANNUAL_ROI_NOT_EVALUATED')
    elif roi < 105.: reasons.append('ANNUAL_ROI_BELOW_105')
    if buys < core.MIN_ANNUAL_BUYS: reasons.append('ANNUAL_PURCHASE_COUNT_TOO_LOW')
    if not out_of_time: reasons.append('NOT_OUT_OF_TIME_VALIDATION')
    if not odds_timing_verified: reasons.append('PRE_CLOSE_ODDS_TIMING_NOT_VERIFIED')
    return {'passed':not reasons,'reasons':reasons}


def cache_audit(args):
    c=core.load_prepared(args.cache,args.year)
    months={str(m):int((c['month']==m).sum()) for m in sorted(set(c['month'].tolist()))}
    actual_odds=c['odds'][np.arange(len(c['month'])),c['actual_index']]
    # Diagnostic, NOT proof of timestamp or executable prices.
    close_match=np.isclose(actual_odds*100,c['amount'],rtol=0,atol=1)
    report={'year':args.year,'preparedSha256':core.digest(args.cache),
            'cachedRaces':len(c['month']),'cachedMonths':months,
            'firstDate':core.date.fromordinal(int(c['day_ordinal'].min())).isoformat(),
            'lastDate':core.date.fromordinal(int(c['day_ordinal'].max())).isoformat(),
            'missingCalendarMonths':sorted(set(range(1,13))-set(map(int,months))),
            'winningOddsTimes100EqualsPayoutPercent':100*float(close_match.mean()),
            'annualGate':annual_gate(months=map(int,months),coverage_verified=False,roi=None,
                        buys=0,out_of_time=False,odds_timing_verified=False),
            'holdoutOpened':False}
    core.dump(args.output,report)


def aggregate(args):
    files=sorted(args.input.glob('screen-*.json'))
    reports=[json.loads(p.read_text()) for p in files]
    expected={(y,f,cap) for y in (2023,2024) for f in core.FAMILIES for cap in (20,40)}
    ids=[(r['year'],r['family'],r['cap']) for r in reports]
    if set(ids)!=expected or len(ids)!=len(expected): raise ValueError('Incomplete matrix')
    paired={}
    for r in reports:
        for row in r['rows']: paired.setdefault(core.canonical(row['config']),{})[r['year']]=row
    rows=[]
    for key,pair in paired.items():
        if set(pair)!={2023,2024}: raise ValueError('Unpaired candidate')
        reasons=[]
        for y,r in pair.items():
            t=r['total']
            if t['purchaseRaces']<core.MIN_BUYS: reasons.append(f'{y}:INSUFFICIENT_BUYS')
            if t['roi']<105: reasons.append(f'{y}:ROI_BELOW_105')
            if t['largestHitShare']>25: reasons.append(f'{y}:ONE_HIT_DEPENDENT')
            if t['roiWithoutLargestHit']<100: reasons.append(f'{y}:ROI_WITHOUT_LARGEST_BELOW_100')
        rows.append({'configHash':key,'config':pair[2023]['config'],
                     'years':{str(y):r['total'] for y,r in pair.items()},'reasons':reasons})
    def score(r): return min(t['roi'] for t in r['years'].values())
    adequate=[r for r in rows if all(t['purchaseRaces']>=core.MIN_BUYS for t in r['years'].values())]
    adequate.sort(key=score,reverse=True)
    per_family={}
    for f in core.FAMILIES:
        rr=[r for r in rows if r['config']['family']==f]
        aa=[r for r in adequate if r['config']['family']==f]
        per_family[f]={'tested':len(rr),'adequateVolume':len(aa),
                       'passCount':sum(not r['reasons'] for r in rr),
                       'bestAdequateVolume':aa[0] if aa else None}
    caches=[json.loads(p.read_text()) for p in sorted(args.input.glob('cache-audit-*.json'))]
    if {r['year'] for r in caches}!={2023,2024,2025} or len(caches)!=3: raise ValueError('Missing cache audit')
    result={'researchOnly':True,'releaseQualified':False,'sourceRun':args.run,
            'conclusion':'NO_CORE_CANDIDATE; ANNUAL_AND_LIVE_VALIDATION_NOT_COMPLETED',
            'candidateCount':len(rows),'adequateVolumeCount':len(adequate),
            'screenPassCount':sum(not r['reasons'] for r in rows),
            'familySummary':per_family,'bestAdequateVolume':adequate[:5],
            'allCandidates':rows,'cacheAudit':caches,
            'holdoutPolicy':{'reserved':core.HOLDOUT,'opened':False},
            'nextStage':'DATA_REPAIR_REQUIRED_BEFORE_NEW_CORE_PROTOCOL',
            'longshotStatus':'NOT_STARTED_CORE_NOT_QUALIFIED',
            'caveat':'A failed partial-period screen is not a measured full-year ROI failure.'}
    core.dump(args.output,result)
    print(json.dumps({k:result[k] for k in ('candidateCount','adequateVolumeCount','screenPassCount','familySummary')},ensure_ascii=False))


def test():
    base=dict(months=range(1,13),coverage_verified=True,roi=105.,buys=360,
              out_of_time=True,odds_timing_verified=True)
    assert annual_gate(**base)['passed']
    assert not annual_gate(**(base|{'months':range(5,10)}))['passed']
    assert not annual_gate(**(base|{'roi':104.999}))['passed']
    assert not annual_gate(**(base|{'odds_timing_verified':False}))['passed']
    assert not annual_gate(**(base|{'coverage_verified':False}))['passed']
    assert not annual_gate(**(base|{'out_of_time':False}))['passed']
    assert not annual_gate(**(base|{'buys':359}))['passed']
    print('Annual gate boundary/coverage/timing tests passed')


def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['cache','aggregate','test'])
    ap.add_argument('--cache',type=Path);ap.add_argument('--year',type=int)
    ap.add_argument('--input',type=Path);ap.add_argument('--output',type=Path);ap.add_argument('--run')
    a=ap.parse_args()
    if a.command=='test':test()
    elif a.command=='cache':cache_audit(a)
    else:aggregate(a)
if __name__=='__main__':main()
