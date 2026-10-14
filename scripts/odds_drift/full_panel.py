"""Deterministic outcome-independent full-odds panel and paired bias check."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import threading
import time
import urllib.request
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

from analyze import COMBOS, PRIOR, RANKS, TIMES, grouped, parse_snapshot, read_csv, ROOT, stats

SEED = 20261014
PER_DAY = 8
LOCK = threading.Lock()
NEXT_REQUEST = 0.

def parse_final(body):
    lines = body.decode('utf-8-sig').splitlines()
    if len(lines) < 8 or lines[0].strip() != 'data=' or lines[1].split('\t')[0] != '1':
        raise ValueError('invalid_final_status_or_header')
    values = []
    for line in lines[2:8]:
        cells = line.split('\t')
        if len(cells) < 21:
            raise ValueError('short_final_row')
        values.extend(float(cell) for cell in cells[1:21])
    if len(values) != 120 or not all(math.isfinite(v) and v > 0 for v in values):
        raise ValueError('nonpositive_or_nonfinite_final_snapshot')
    return dict(zip(COMBOS, values))

def throttle():
    global NEXT_REQUEST
    with LOCK:
        now = time.monotonic()
        delay = max(0, NEXT_REQUEST-now)
        NEXT_REQUEST = max(now, NEXT_REQUEST) + .5
    if delay:
        time.sleep(delay)

def fetch(race, cache):
    code = race['race_code']
    url = f'https://race.boatcast.jp/txt/{code[8:10]}/bc_kakutei_od3_{code[:8]}_{code[8:10]}_{code[10:12]}.txt'
    path = cache / ('final_' + code + '.txt')
    error = None
    for attempt in range(2):
        try:
            if path.exists():
                body = path.read_bytes()
            else:
                throttle()
                req = urllib.request.Request(url, headers={'User-Agent':'BOAT-AI-Odds-Drift-Research/1.0'})
                with urllib.request.urlopen(req, timeout=30) as response:
                    body = response.read()
                path.write_bytes(body)
            odds = parse_final(body)
            winner_final = odds[race['winner']]
            difference = winner_final - race['final_odds']
            # Retain complete files even if their winner column disagrees with
            # payout. Filtering on that outcome would introduce selection again.
            # >=1000x display values are integers, while the payout can retain
            # one decimal. Check that display precision interval as well.
            exact_match = abs(difference) <= .051
            display_match = exact_match or (winner_final >= 1000 and winner_final.is_integer() and -.999 <= difference <= .001)
            return {'race_code':code, 'date':race['date'], 'url':url, 'sha256':hashlib.sha256(body).hexdigest(), 'bytes':len(body), 'status':'ok',
                    'winnerExactMatch':exact_match, 'winnerMatch':display_match, 'winnerPayoutDifference':difference,
                    'retrievedAt':datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()}, odds
        except Exception as exc:
            error = f'{type(exc).__name__}: {exc}'
            if isinstance(exc, ValueError):
                break
    return {'race_code':code, 'date':race['date'], 'url':url, 'status':'error', 'error':error}, None

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--analyze-only', action='store_true')
    args = parser.parse_args()
    root = args.root
    winners = pd.read_csv(root/'output/odds_drift_winner_matches_20261014.csv', dtype={'race_code':str,'venue':str})
    plan = []
    for day, frame in winners.groupby('date', sort=True):
        rows = sorted(frame.to_dict('records'), key=lambda r:r['race_code'])
        day_seed = int.from_bytes(hashlib.sha256(f'{SEED}:{day}'.encode()).digest()[:8], 'big')
        rng = random.Random(day_seed)
        plan.extend(sorted(rng.sample(rows, min(PER_DAY,len(rows))), key=lambda r:r['race_code']))
    plan_payload = {'protocolVersion':1, 'seed':SEED, 'perDay':PER_DAY,
                    'sampling':'Uniform without replacement within each calendar day among primary valid pre-close/payout matches; no winner rank, payout or odds-ratio criterion',
                    'sourceRef':'31b03b22989700a9f3a94152ae88edcaa1642124',
                    'races':[{'race_code':r['race_code'],'date':r['date']} for r in plan]}
    plan_path=root/'output/odds_drift_full_panel_plan_20261014.json'
    plan_path.write_text(json.dumps(plan_payload,ensure_ascii=False,indent=2)+'\n')
    print(f'Frozen full panel plan: {len(plan)} races, sha256={hashlib.sha256(plan_path.read_bytes()).hexdigest()}',flush=True)
    results=[]
    final_odds={}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(fetch,r,root/'cache') for r in plan]
        for future in as_completed(futures):
            manifest, odds=future.result()
            results.append(manifest)
            if odds:
                final_odds[manifest['race_code']]=odds
            else:
                print(json.dumps(manifest,ensure_ascii=False),flush=True)
            if len(results)%60==0:
                print(f'Full snapshots {len(results)}/{len(plan)}, valid {len(final_odds)}',flush=True)
    manifests=sorted(results,key=lambda r:r['race_code'])
    (root/'output/odds_drift_full_panel_manifest_20261014.json').write_text(json.dumps({'plan':plan_payload,'files':manifests},ensure_ascii=False,indent=2)+'\n')
    pre_maps={}
    for day in winners.date.unique():
        for r in read_csv(root/f'cache/od3_{day}.csv'):
            pre_maps[r['レースコード']]=r
    rows=[]
    for race in plan:
        code=race['race_code']
        if code not in final_odds:
            continue
        _,pre,ranks,minutes=parse_snapshot(pre_maps[code])
        invsum=sum(1/v for v in pre.values())
        for combo in COMBOS:
            from analyze import rank_bucket, time_bucket
            rank=ranks[combo]
            b=rank_bucket(rank)
            final=final_odds[code][combo]
            factor=1+(PRIOR[b]-1)*min(minutes/8,1)
            rows.append({'race_code':code,'date':race['date'],'month':race['date'][:7],'venue':code[8:10],
                         'combo':combo,'is_winner':combo==race['winner'],'pre_rank':rank,'rank_bucket':b,
                         'minutes':minutes,'time_bucket':time_bucket(minutes),'pre_odds':pre[combo],
                         'final_odds':final,'ratio':final/pre[combo],'difference':final-pre[combo],
                         'pre_implied_prob':(1/pre[combo])/invsum,
                         'android_estimate':round(max(1,pre[combo]*factor)*10)/10,
                         'tied_odds':sum(v==pre[combo] for v in pre.values())>1,'final_rank_delta':None})
    panel=pd.DataFrame(rows)
    winner_panel=panel[panel.is_winner]
    comparisons=[]
    for b in RANKS:
        full=stats(panel[panel.rank_bucket==b],True)
        win=stats(winner_panel[winner_panel.rank_bucket==b],True)
        comparisons.append({'rank_bucket':b,'all':full,'winner':win,
                            'winnerMinusAllMedian':win['medianRatio']-full['medianRatio'] if win['n'] else None})
    aligned_codes={r['race_code'] for r in manifests if r['status']=='ok' and r['winnerMatch']}
    aligned_panel=panel[panel.race_code.isin(aligned_codes)]
    payload={'schemaVersion':1,'exploratory':True,'samplingPlan':plan_payload,
             'plannedRaces':len(plan),'validRaces':len(final_odds),'failedRaces':[r for r in manifests if r['status']!='ok'],
             'pairs':len(panel),'days':int(panel.date.nunique()),'venues':int(panel.venue.nunique()),
             'overall':stats(panel,True),'winnerOverall':stats(winner_panel,True),'byRank':comparisons,
             'byTimeRank':grouped(panel,['time_bucket','rank_bucket'],[TIMES,RANKS],True),
             'byMonthRank':grouped(panel,['month','rank_bucket']),
             'winnerPayoutAgreement':{'alignedRaces':len(aligned_codes),'mismatches':[r for r in manifests if r['status']=='ok' and not r['winnerMatch']],
                                     'sensitivityAlignedOnlyByRank':grouped(aligned_panel,['rank_bucket'],[RANKS])},
             'warnings':['8 races per calendar day: equal-day exploratory panel, not race-volume-weighted national census.',
                         'All 120 combinations in a race are dependent; effective race count, day bootstrap and bucket coverage matter, not just pair count.',
                         'Historical source timestamps use job-start time; scheduled close is not observed actual close.',
                         'Official final files are fetched now and are not immutable archived snapshots; raw hashes are recorded.',
                         'Complete files with winner/payout disagreement are retained and flagged; filtering them could reintroduce outcome selection. The payout-aligned-only sensitivity is still conditional.',
                         'Payout/quote agreement respects integer display rounding at >=1000x. Dividend adjustment such as a dead heat can still differ from the displayed final odds.',
                         'The mapping has an independent official HTML check (recorded separately). It does not establish final-file reliability for every special race state.']}
    (root/'output/odds_drift_full_panel_20261014.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    panel.to_csv(root/'output/odds_drift_full_panel_pairs_20261014.csv',index=False)
    print(json.dumps({'planned':len(plan),'valid':len(final_odds),'pairs':len(panel),'days':payload['days'],'venues':payload['venues'],'overall':payload['overall'],'byRank':comparisons},ensure_ascii=False,indent=2),flush=True)

if __name__=='__main__':
    main()
