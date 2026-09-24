#!/usr/bin/env python3
"""v0.16 integrity audit. Only already-opened July/August 2025 may enter comparisons."""
import argparse
import hashlib
import json
import os
import re
import time
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
import numpy as np

from v016_core_research import digest, dump, canonical
from v016_r4_features import COMBO_TEXT, COMBOS

ROOT=Path(__file__).resolve().parents[1]
PROTOCOL=ROOT/'data/v016_integrity_protocol.json'
R4=ROOT/'data/v016_r4_protocol.json'
PRECOMMIT='44c617f78f25baeb19aff9d5fdd466c51cfd6c95'
SOURCE_COMMIT='ddd2f0c1011889779d04dfb802bee4e152b35b30'
MODEL_ARTIFACT_DIGEST='sha256:58b845fa8d07efe258b08a23ac6caafab2e4854ce4b84618fb4af6ae3f3687fe'
SOURCE_SHA={
    'README.md':'edec8fe8adf4f7d776dfd70a8850c607d565cdded089b9808911dbbd9106baff',
    'scraper.php':'ed1dd19fedbe8ed796db831d10629f6935b602a47acb509460501f73019e4a71',
    'src/OddsSaver.php':'5a20a2cdf18504f6661ebfb27bcbbe2de378daabf549bd0d5df6d716c27aa126',
    'src/OddsScraper.php':'8a4ce84844f07904fe31605d31dcaf51c6b93f84a7f4e742133e5c4a050c7f61',
    '.github/workflows/cron.yml':'93ed7ad7e389b8d07ee0f54e9faadb4a8e36c403123a4ec8d727b8f12453e6cf',
    '.github/workflows/get_past.yml':'a0fb87fbd1ce0a12569d95f6af8417ae59727454784893b49f02cf0fcf8f35d4'}

def allowed(day):
    if day.year!=2025 or day.month not in (7,8): raise ValueError('Only already-opened July-August 2025 is permitted')

def checked_npz(path):
    with np.load(path,allow_pickle=False) as z:
        # Check date/index before reading results, odds or features.
        days=z['day_ordinal']; months=z['month']
        if not len(days): raise ValueError('Empty cache')
        if any(date.fromordinal(int(d)).year!=2025 or int(m)!=date.fromordinal(int(d)).month or int(d)>=date(2025,9,1).toordinal() for d,m in zip(days,months)):
            raise ValueError('Prohibited date in cache')
        c={k:z[k] for k in z.files}
    if not np.array_equal(c['combos'],COMBO_TEXT): raise ValueError('Trifecta order changed')
    keys=np.stack([c[k] for k in ('day_ordinal','venue','race_number')],axis=1)
    if len(np.unique(keys,axis=0))!=len(keys): raise ValueError('Duplicate race key')
    return c

def context(raw,meta):
    p=json.loads(PROTOCOL.read_text()); original=json.loads(R4.read_text())
    if p['boundary']['sealedFrom']!='2025-09-01' or original['sources']['odds']['commit']!=SOURCE_COMMIT:
        raise ValueError('Source/boundary drift')
    if meta['start']!='2025-01-01' or meta['end']!='2025-08-31' or meta['sourceCommits']!=original['sources']:
        raise ValueError('Unpinned raw archive')
    c=checked_npz(raw)
    if c['year'].tolist()!=[2025] or len(c['month'])!=meta['races']: raise ValueError('Raw population drift')
    return c

def summary(x):
    x=np.asarray(x,dtype=float)
    return {'count':int(len(x)),'mean':float(np.mean(x)) if len(x) else None,
            'min':float(np.min(x)) if len(x) else None,'median':float(np.median(x)) if len(x) else None,
            'p90':float(np.quantile(x,.9)) if len(x) else None,'p95':float(np.quantile(x,.95)) if len(x) else None,
            'p99':float(np.quantile(x,.99)) if len(x) else None,'max':float(np.max(x)) if len(x) else None}

def payout_metrics(c,mask):
    ix=np.flatnonzero(mask); n=len(ix); winner=c['actual_index'][ix].astype(int)
    if n and (winner.min()<0 or winner.max()>=120): raise ValueError('Invalid winner index')
    odds=c['odds'][ix,winner].astype(float); pay=c['amount'][ix].astype(float)/100.
    valid=np.isfinite(odds)&(odds>0)&np.isfinite(pay)&(pay>0)
    if not valid.all(): raise ValueError('Missing winning quote/payout: comparison would silently drop races')
    diff=odds-pay; absolute=np.abs(diff); relative=absolute/pay
    return {'races':n,'exactStoredValue':int((absolute<=.0001).sum()),
            'withinAbsolute0_1':int((absolute<=.1001).sum()),'withinAbsolute0_5':int((absolute<=.5001).sum()),
            'withinRelative1Pct':int((relative<=.01).sum()),'withinRelative3Pct':int((relative<=.03).sum()),
            'withinRelative5Pct':int((relative<=.05).sum()),
            'signedOddsMinusPayout':summary(diff),'absoluteOddsMinusPayout':summary(absolute),
            'relativeAbsolute':summary(relative)}

def read_source(kind,day,meta):
    allowed(day)
    source=meta['sourceCommits'][kind]
    if source!=json.loads(R4.read_text())['sources'][kind]: raise ValueError('Unpinned source')
    url=f"https://raw.githubusercontent.com/{source['repo']}/{source['commit']}/docs/v3/{day.year}/{day:%Y%m%d}.json"
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BOAT-AI-integrity-pinned'}),timeout=50) as response:
                raw=response.read()
            if hashlib.sha256(raw).hexdigest()!=meta['sourceHashes'][day.isoformat()][kind]:
                raise ValueError('Source SHA mismatch '+kind+' '+day.isoformat())
            result=json.loads(raw)[kind]
            if any(r.get('date')!=day.isoformat() for r in result): raise ValueError('Source date mismatch')
            return result
        except ValueError: raise
        except Exception:
            if attempt==2: raise
            time.sleep(attempt+1)

def keyset(rows):
    out={}
    for x in rows:
        key=(int(x['stadium_number']),int(x['number']))
        if key in out: raise ValueError('Duplicate source race')
        out[key]=x
    return out

def refund_markers(record):
    # Count only explicit named fields. Unknown schema is reported as unobservable.
    found=[]
    def walk(obj,prefix=''):
        if isinstance(obj,dict):
            for k,v in obj.items():
                path=f'{prefix}.{k}' if prefix else k
                if any(t in k.lower() for t in ('refund','return','返還')) and v not in (None,False,0,'',[],{}):
                    found.append(path)
                walk(v,path)
        elif isinstance(obj,list):
            for item in obj: walk(item,prefix)
    if record: walk(record)
    return sorted(set(found))

def population_day(day,meta,raw_keys):
    programs=keyset(read_source('programs',day,meta)); results=keyset(read_source('results',day,meta))
    reasons=Counter(); marker_keys=Counter(); eligible=set(); multiple=0
    for key,program in programs.items():
        result=results.get(key)
        for field in refund_markers(result): marker_keys[field]+=1
        if result is None: reasons['missingResult']+=1; continue
        boats=result.get('boats') or []
        if len(boats)!=6 or set(x.get('racer_place_number') for x in boats)!=set(range(1,7)):
            reasons['nonSixBoatOrIncompleteFinish']+=1; continue
        pays=result.get('payouts',{}).get('trifecta',[]) or []
        if len(pays)>1:
            reasons['multipleTrifectaPayout']+=1; multiple+=1; continue
        if len(pays)<1: reasons['noTrifectaPayout']+=1; continue
        if pays[0].get('combination') not in COMBO_TEXT or not isinstance(pays[0].get('amount'),(int,float)) or pays[0]['amount']<=0:
            reasons['invalidTrifectaPayout']+=1; continue
        # Normal eligible race according to original r4 source-result definition.
        eligible.add(key)
    if eligible!=raw_keys: raise ValueError(f'Eligible source/raw race mismatch {day}: source {len(eligible)} raw {len(raw_keys)}')
    if sum(reasons.values())+len(eligible)!=len(programs): raise ValueError('Population partition mismatch')
    return {'sourceRaces':len(programs),'sourceResults':len(results),'eligibleSettled':len(eligible),
            'excludedReasons':dict(reasons),'multiplePayout':multiple,'refundFieldPaths':dict(marker_keys),
            'resultWithoutProgram':len(set(results)-set(programs))}

def odds_month(args):
    meta=json.loads(args.metadata.read_text()); c=context(args.raw,meta); month=args.month
    if month not in (7,8): raise ValueError('Forbidden month')
    take=c['month']==month; selected=np.flatnonzero(take)
    keys=np.stack([c[k] for k in ('day_ordinal','venue','race_number')],axis=1)
    payout=payout_metrics(c,take); venues={str(int(v)):payout_metrics(c,take&(c['venue']==v)) for v in sorted(set(c['venue'][take]))}
    strongest=[]
    for i in selected:
        w=int(c['actual_index'][i]); quote=float(c['odds'][i,w]); true=float(c['amount'][i])/100
        strongest.append({'day':date.fromordinal(int(c['day_ordinal'][i])).isoformat(),'venue':int(c['venue'][i]),'race':int(c['race_number'][i]),
                          'winningCombo':str(COMBO_TEXT[w]),'archivedOdds':quote,'payoutOdds':true,'signedOddsMinusPayout':quote-true})
    strongest.sort(key=lambda x:(-abs(x['signedOddsMinusPayout']),x['day'],x['venue'],x['race']))
    # Intermediate only; final publication keeps summaries and the 20 largest race keys.
    samples=[{'venue':x['venue'],'difference':x['signedOddsMinusPayout'],'payoutOdds':x['payoutOdds']} for x in strongest]
    counts=meta['months'][f'2025-{month:02d}'];
    if counts['eligibleSettled']!=int(take.sum()): raise ValueError('Metadata/NPZ population drift')
    output={'month':month,'payoutComparison':payout,'venues':venues,'top20Mismatches':strongest[:20],
            'internalSamples':samples,
            'population':dict(sourceRaces=counts['sourceRaces'],eligibleSettled=counts['eligibleSettled'],
                              preRaceFeatureUsable=int(c['usable'][take].sum()),all120OddsUsable=int(c['odds_usable'][take].sum()),
                              jointUsable=int((c['usable'][take]&c['odds_usable'][take]).sum()),
                              winningOddsUsable=int(np.isfinite(c['odds'][selected,c['actual_index'][selected]]).sum())),
            'rawSha256':digest(args.raw),'rawMetadataSha256':digest(args.metadata),'protocolCommitSha':PRECOMMIT,
            'protocolSha256':digest(PROTOCOL),'sealedAfterAugust':True}
    # Source-provenance-aligned results/program classifications, fetched only for opened days.
    days=[date(2025,month,d) for d in range(1,32) if d<=__import__('calendar').monthrange(2025,month)[1]]
    accumulated=Counter(); reasons=Counter(); refund=Counter()
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures={executor.submit(population_day,day,meta,{tuple(row[1:]) for row in keys[keys[:,0]==day.toordinal()]}):day for day in days}
        for future in as_completed(futures):
            day=futures[future]; row=future.result()
            for k in ('sourceRaces','sourceResults','eligibleSettled','multiplePayout','resultWithoutProgram'): accumulated[k]+=row[k]
            reasons.update(row['excludedReasons']); refund.update(row['refundFieldPaths'])
    if accumulated['sourceRaces']!=counts['sourceRaces'] or accumulated['eligibleSettled']!=counts['eligibleSettled']:
        raise ValueError('Source ledger mismatch')
    output['sourcePopulation']=dict(accumulated,excludedReasons=dict(reasons),refundFieldPaths=dict(refund),
                                    refundObservability='explicit field paths only; no refund stake/count inferred when absent')
    dump(args.output,output)

def source_provenance(args):
    proto=json.loads(PROTOCOL.read_text()); meta=json.loads(args.metadata.read_text())
    if proto['oddsProvenance']['pinnedCommit']!=SOURCE_COMMIT or meta['sourceCommits']['odds']['commit']!=SOURCE_COMMIT:
        raise ValueError('Odds source changed')
    texts={}
    for path,expected in SOURCE_SHA.items():
        url=f'https://raw.githubusercontent.com/lamrongol/BoatraceOdds/{SOURCE_COMMIT}/{path}'
        for attempt in range(3):
            try:
                with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'BOAT-AI-integrity-pinned'}),timeout=50) as response: raw=response.read()
                break
            except Exception:
                if attempt==2: raise
                time.sleep(attempt+1)
        if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError('Source file hash drift '+path)
        texts[path]=raw.decode()
    scraper=texts['scraper.php']; saver=texts['src/OddsSaver.php']; cron=texts['.github/workflows/cron.yml']; past=texts['.github/workflows/get_past.yml']
    if "Carbon::yesterday('Asia/Tokyo')" not in scraper or "->subDay()" not in scraper or 'file_put_contents($path, $contents)' not in saver:
        raise ValueError('Postrace archive evidence changed')
    if '0 0 * * *' not in cron or '21 */1 * * *' not in past: raise ValueError('Schedule evidence changed')
    # Sample within opened interval, byte-for-byte tied to raw source SHA.
    sample=read_source('odds',date(2025,7,1),meta); races=keyset(sample)
    key_names=sorted({k for race in races.values() for k in race})
    timestamp=[k for k in key_names if any(t in k.lower() for t in ('timestamp','captured','updated','snapshot','time'))]
    output={'sourceRepository':'lamrongol/BoatraceOdds','pinnedCommit':SOURCE_COMMIT,'sourceFileSha256':SOURCE_SHA,
        'evidence':{'scraper.php':['Carbon::yesterday(\'Asia/Tokyo\')','recorded_day.json then subDay()','save to docs/v3/YYYY/YYYYMMDD.json'],
                    '.github/workflows/cron.yml':['cron: 0 0 * * * UTC (09:00 JST)','php scraper.php v3'],
                    '.github/workflows/get_past.yml':['cron: 21 */1 * * * UTC','php scraper.php v3 True'],
                    'src/OddsSaver.php':['json_encode([\'odds\' => $odds])','file_put_contents($path, $contents): overwrites one daily file']},
        'sample':{'day':'2025-07-01','raceCount':len(sample),'rootKey':'odds','raceKeys':key_names,'timestampKeys':timestamp,
                  'sha256':meta['sourceHashes']['2025-07-01']['odds']},
        'interpretation':{'oneStoredArrayPerDay':True,'historicalPerRaceSnapshots':False,
                          'storedPerRaceTimestamp':False,'scheduledPrecloseQuote':False,
                          'regularDayArchiveGeneratedFromPreviousDay':True,
                          'backfillCanBeAfterRace':True,'TMinus5Proven':False},
        'decision':'ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST','protocolCommitSha':PRECOMMIT,'protocolSha256':digest(PROTOCOL)}
    dump(args.output,output)

def forecast(args):
    model=json.loads((args.model/'manifest.json').read_text()); r4=json.loads(R4.read_text()); oof=json.loads((ROOT/'data/v016_oof_result.json').read_text());
    baseline=json.loads((ROOT/'data/v01516_forecast_audit.json').read_text()); feature=json.loads((args.features/'feature_metadata.json').read_text())
    if model['variant']!='reaction' or model['marketInOutcomeModel'] or model['racerIdInModel'] or model['protocolSha256']!=digest(R4):
        raise ValueError('Model is not frozen market-free reaction')
    if args.model_artifact_digest!=MODEL_ARTIFACT_DIGEST or digest(args.features/'train.npz')!=model['trainCacheSha256']:
        raise ValueError('Referenced r4 artifact or train cache changed')
    if model['codeSha256']!={name:digest(ROOT/name) for name in model['codeSha256']}:
        raise ValueError('Model inference source hash changed')
    if model['trainEndOrdinal']>=model['validationEndOrdinal'] or date.fromordinal(model['validationEndOrdinal'])!=date(2025,6,30):
        raise ValueError('Model training dates invalid')
    model_files={}
    for stage,info in model['stages'].items():
        path=args.model/f'stage{stage}.txt'
        if digest(path)!=info['sha256']: raise ValueError('Stage file changed')
        model_files[path.name]={'sha256':digest(path),'bytes':path.stat().st_size,'features':info['features'],
                                'iterations':info['iterations']}
    c=checked_npz(args.features/'development.npz')
    if set(c['month'])!={7,8}: raise ValueError('Development cache changed')
    schema=canonical([c[k].tolist() for k in ('boat_names','history_names','reaction_names')])
    if schema!=model['schemaSha256'] or feature['rawSha256']!=digest(args.raw): raise ValueError('Feature/raw mismatch')
    if len(c['month'])!=baseline['population']['cacheRaces'] or int(c['usable'].sum())!=baseline['overall']['races']:
        raise ValueError('Android comparison population drift')
    if not np.array_equal(c['usable'],c['usable']&c['odds_usable']):
        raise ValueError('Forecast comparison population differs from r4 OOF')
    if oof['modelA']['races']!=baseline['overall']['races'] or oof['modelA']['races']!=int(c['usable'].sum()):
        raise ValueError('Different development sample')
    state_path=args.features/'history_state.json'; state=json.loads(state_path.read_text())
    if state['lastDay']!=date(2025,8,31).toordinal(): raise ValueError('History state date drift')
    if np.any(c['history_through']>=c['day_ordinal']): raise ValueError('Same-day history leak')
    names={k:c[k].tolist() for k in ('boat_names','history_names','reaction_names')}
    asset={'manifest.json':{'sha256':digest(args.model/'manifest.json'),'bytes':(args.model/'manifest.json').stat().st_size},
           'history_state.json':{'sha256':digest(state_path),'bytes':state_path.stat().st_size},**model_files}
    candidate={'kind':'FORECAST_ONLY','status':'PENDING_INDEPENDENT_HOLDOUT','productionPromotion':False,'marketInputs':False,
       'purchaseCandidate':False,'releaseQualified':False,'modelRunId':35940833546,'modelArtifactId':10784912368,
       'modelArtifactDigest':args.model_artifact_digest,'modelManifestSha256':digest(args.model/'manifest.json'),
       'protocolSha256':model['protocolSha256'],'featureSchemaSha256':model['schemaSha256'],
       'integrityProtocolCommitSha':PRECOMMIT,'integrityProtocolSha256':digest(PROTOCOL),
       'architecture':'3 conditional grouped-softmax LightGBM stages, 6/5/4 candidate rows, joint 120 trifecta probabilities',
       'hyperparameters':r4['estimator'],'temperature':model['temperature'],
       'trainingMaxDate':str(date.fromordinal(model['trainEndOrdinal'])),
       'earlyStoppingMaxDate':str(date.fromordinal(model['validationEndOrdinal'])),
       'historySeed':{'year':2024,'runId':35870380669,'artifact':'v016-annual-cache-2024',
                      'featureRunId':35940833546,'featureArtifactId':10784104679,
                      'featureMetadataSha256':digest(args.features/'feature_metadata.json'),
                      'currentStateThrough':str(date.fromordinal(state['lastDay']))},
       'assets':asset,'sourceCodeSha256':model['codeSha256'],'featureNames':names,
       'developmentPopulation':{'races':oof['modelA']['races'],'featureCacheRaces':len(c['month']),
                                'androidAuditedRaces':baseline['overall']['races']},
       'forecastMetrics':{k:oof['modelA'][k] for k in ('logloss','brier','topChoiceEce','firstTop1','firstTop2','trifectaTop1','trifectaTop2','trifectaTop4','trifectaTop8')},
       'androidBaseline':{k:baseline['overall'][k] for k in ('trifectaLogloss','trifectaBrier','firstTop1Accuracy','firstTop2Coverage','trifectaTop1HitRate','trifectaTop4HitRate','trifectaTop8HitRate')},
       'septemberOpened':False,'q4Opened':False}
    args.output.mkdir(parents=True,exist_ok=True)
    dump(args.output/'forecast_candidate.json',candidate)
    deploy={'sourceRunId':35940833546,'modelFiles':asset,'statePlayers':len(state['recent']),
            'stateUpdateRaces':state['updateRaces'],'stateThrough':str(date.fromordinal(state['lastDay'])),
            'featureNames':names,'conditionalRowsPerRace':{'stage0':6,'stage1':30,'stage2':120,'total':156},
            'missingData':'r4 LightGBM NaN handling; required preview racer IDs, exhibition time, ST and valid course must be present',
            'fallback':'when required fields/history state missing, suppress Model A forecast and use existing production forecast only after explicit design approval; never invent player history or infer odds',
            'readiness':'FORECAST_READY_FOR_INTEGRATION_DESIGN_PENDING_HOLDOUT',
            'limitations':['LightGBM text-model evaluation not implemented or benchmarked on Android',
                           '2025-08-31 state is historical, not a current live-ready 2026 state',
                           'independent holdout remains sealed and is not passed'],
            'protocolCommitSha':PRECOMMIT,'protocolSha256':digest(PROTOCOL)}
    dump(args.output/'deployability.json',deploy)
    # Export only model/state/schema research assets, no odds, labels, app or production files.
    import shutil
    bundle=args.output/'bundle'; bundle.mkdir(exist_ok=True)
    for name in ('manifest.json','stage0.txt','stage1.txt','stage2.txt'): shutil.copy2(args.model/name,bundle/name)
    shutil.copy2(state_path,bundle/'history_state.json')
    dump(bundle/'feature_schema.json',names)
    dump(bundle/'integrity_manifest.json',candidate)

def publish(args):
    p=json.loads((args.input/'provenance.json').read_text()); months=[json.loads((args.input/f'odds-{m}.json').read_text()) for m in (7,8)]
    candidate=json.loads((args.input/'forecast_candidate.json').read_text()); deploy=json.loads((args.input/'deployability.json').read_text())
    if p['decision']!='ODDS_NOT_SUITABLE_FOR_REALIZABLE_BACKTEST' or candidate['marketInputs'] or candidate['productionPromotion'] or candidate['status']!='PENDING_INDEPENDENT_HOLDOUT':
        raise ValueError('Decision or forecast guard violation')
    if any(x.get('protocolCommitSha',x.get('integrityProtocolCommitSha'))!=PRECOMMIT for x in [p,*months,candidate,deploy]):
        raise ValueError('Protocol provenance mismatch')
    counts=Counter(); pop=Counter(); excluded=Counter(); refunds=Counter(); examples=[]; samples=[]
    for x in months:
        samples+=x.pop('internalSamples')
        counts.update({k:v for k,v in x['payoutComparison'].items() if k.startswith(('exact','within')) or k=='races'})
        pop.update(x['population']); excluded.update(x['sourcePopulation']['excludedReasons']); refunds.update(x['sourcePopulation']['refundFieldPaths'])
        examples+=x['top20Mismatches']
    examples.sort(key=lambda x:-abs(x['signedOddsMinusPayout']))
    signed=np.asarray([x['difference'] for x in samples]); absolute=np.abs(signed)
    venues={str(v):{'races':sum(x['venue']==v for x in samples),
                    'signed':summary([x['difference'] for x in samples if x['venue']==v]),
                    'absolute':summary([abs(x['difference']) for x in samples if x['venue']==v])}
            for v in sorted({x['venue'] for x in samples})}
    overall_diff={'signedOddsMinusPayout':summary(signed),'absoluteOddsMinusPayout':summary(absolute),
                  'relativeAbsolute':summary([abs(x['difference'])/x['payoutOdds'] for x in samples])}
    result={'runId':args.run,'oddsDecision':p['decision'],'forecastDecision':deploy['readiness'],
            'provenance':p,'monthly':months,'payoutCounts':dict(counts),'population':dict(pop),
            'excludedReasons':dict(excluded),'refundFieldPaths':dict(refunds),'venues':venues,
            'overallDifference':overall_diff,
            'top20Mismatches':examples[:20],'forecastMetrics':candidate['forecastMetrics'],
            'androidBaseline':candidate['androidBaseline'],'candidateStatus':candidate['status'],
            'protocolCommitSha':PRECOMMIT,'protocolSha256':digest(PROTOCOL),
            'septemberOpened':False,'q4Opened':False,'productionPromotion':False}
    args.output.mkdir(parents=True,exist_ok=True); dump(args.output/'v016_integrity_result.json',result)
    dump(args.output/'v016_forecast_candidate.json',candidate)
    report=['# v0.16 オッズ整合性とforecast-only候補','',f'- Run: {args.run} / 事前登録commit `{PRECOMMIT}`',
            f"- オッズ判定: **{p['decision']}**。購入可能な締切前オッズとして扱えないため、このアーカイブによるROI基準の本番昇格を停止。",
            f"- [オッズソース固定commit](https://github.com/{p['sourceRepository']}/tree/{p['pinnedCommit']}) の `scraper.php` は東京時間の前日を取得し、`cron.yml` は毎日00:00 UTC起動。`get_past.yml` は過去日を遡る。`OddsSaver.php` は日付ごとに1配列を上書き保存。7月1日のJSONは144レース、取得時刻フィールドなし。READMEの「約30分間隔」は、この保存経路の時刻証明にならない。",
            '- 2025年7〜8月の既存cacheと、同一SHAのprogram/resultソースだけを照合。9月/Q4は未取得。','',
            '| 集計 | 7月 | 8月 | 合計 |','|---|---:|---:|---:|']
    for field in ('sourceRaces','eligibleSettled','preRaceFeatureUsable','all120OddsUsable','jointUsable'):
        report.append(f"| {field} | {months[0]['population'][field]:,} | {months[1]['population'][field]:,} | {pop[field]:,} |")
    for field in ('races','exactStoredValue','withinAbsolute0_1','withinAbsolute0_5','withinRelative1Pct','withinRelative3Pct','withinRelative5Pct'):
        report.append(f"| payout {field} | {months[0]['payoutComparison'][field]:,} | {months[1]['payoutComparison'][field]:,} | {counts[field]:,} |")
    report+=['',f"差分(オッズ−払戻/100): 平均 {overall_diff['signedOddsMinusPayout']['mean']:.6f}、絶対差平均 {overall_diff['absoluteOddsMinusPayout']['mean']:.6f}、絶対差中央値 {overall_diff['absoluteOddsMinusPayout']['median']:.8f}、最大 {overall_diff['absoluteOddsMinusPayout']['max']:.1f} オッズ点。月別・場別の分位点と最大不一致20レースのキーは `data/v016_integrity_result.json`。",
             '完全一致は保存数値の浮動小数点誤差を許容した判定（絶対差≤0.0001）。資料から高配当時の丸め・切捨て規則を確証できないため、別の換算規則による一致率は仮定しない。',
             f'対象外の分類: `{dict(excluded)}`。返還を示す明示フィールド: `{dict(refunds)}`。項目がない場合、返還が0件と断定しない。中止・欠場・不成立の内訳も現行の除外理由だけでは確定しない。',
             '払戻との一致は事後・最終に近い値を示し得るが、事前取得の証明にはならない。除外に伴うROIバイアスの方向は、この母集団だけから確定できない。','',
             f"- forecast判定: **{deploy['readiness']}**。候補は市場入力なし、`PENDING_INDEPENDENT_HOLDOUT`、本番昇格なし。",
             f"- Model A 9,583レース: 1着Top1 {candidate['forecastMetrics']['firstTop1']*100:.2f}%、Top2 {candidate['forecastMetrics']['firstTop2']*100:.2f}%、3連単Top1 {candidate['forecastMetrics']['trifectaTop1']*100:.2f}%、Top4 {candidate['forecastMetrics']['trifectaTop4']*100:.2f}%、Top8 {candidate['forecastMetrics']['trifectaTop8']*100:.2f}%。Logloss {candidate['forecastMetrics']['logloss']:.6f}、Brier {candidate['forecastMetrics']['brier']:.6f}。",
             f"- 現行Android純AI監査の同9,583レース: 1着Top1 {candidate['androidBaseline']['firstTop1Accuracy']:.2f}%、Top2 {candidate['androidBaseline']['firstTop2Coverage']:.2f}%、3連単Top1 {candidate['androidBaseline']['trifectaTop1HitRate']:.2f}%、Top4 {candidate['androidBaseline']['trifectaTop4HitRate']:.2f}%、Top8 {candidate['androidBaseline']['trifectaTop8HitRate']:.2f}%。ただし開発期間の比較であり、独立holdoutは未実施。",
             '- 推論/履歴stateの詳細は `data/v016_forecast_deployability.md`。Android実装、version、Releaseには未着手。','']
    (args.output/'v016_integrity_report.md').write_text('\n'.join(report))
    d=deploy; f=candidate
    fields=f['featureNames']; assets=f['assets']
    body=['# Model A forecast-only Android deployability監査','',f"- 判定: **{d['readiness']}**。独立holdout待ち、Android搭載・本番昇格は未実施。",
          f"- モデルArtifact: Run {f['modelRunId']} / ID {f['modelArtifactId']} / ZIP digest `{f['modelArtifactDigest']}`。manifest `{f['modelManifestSha256']}`。",
          f"- 履歴state: {d['statePlayers']:,}選手、{d['stateUpdateRaces']:,}レース更新、{d['stateThrough']}まで。これはライブ時点のstateではない。",
          f"- 1レースあたり条件付きモデル評価: 1着6行 + 2着30行 + 3着120行 = **156行**。LightGBM 3モデル（{[assets['stage'+str(i)+'.txt']['bytes'] for i in range(3)]} bytes）、履歴state {assets['history_state.json']['bytes']:,} bytes。",
          '', '## 必要な入力と計算', '',
          '- 出走表: 選手登録番号、級別、下記のprogram特徴。直前情報: 展示タイム、展示ST、進入コース、風速・波高・気温・水温・風向。場・R番号を使用。レース結果、払戻、実ST/実進入、市場オッズは推論入力にしない。',
          f"- boat/current ({len(fields['boat_names'])}): {', '.join(fields['boat_names'])}。",
          f"- history ({len(fields['history_names'])}): {', '.join(fields['history_names'])}。",
          f"- reaction ({len(fields['reaction_names'])}): {', '.join(fields['reaction_names'])}。",
          '- 登録番号は履歴テーブルのキーのみ。2024 seed→日単位に全レースの特徴量snapshotを先に生成→当日の確定結果をまとめて履歴へ反映する。同日の他レース結果を混ぜない。30/60/90/180日窓とglobal/course/class→player→player-courseの縮約を再現する。',
          '- 数値欠損は既存のNaN特徴・LightGBM欠損分岐で扱う。ただし登録番号/6艇/展示・ST/進入コースの必須入力がない場合はModel A予想を出さず、別途承認後に既存予想へフォールバックする。',
          '- Android側はLightGBMのテキストツリーを互換に評価する実装または検証済み変換形式が必要。現在のAndroidで3モデルのパーサ・156行推論・性能・メモリ・端末差は未実装/未計測。',
          '- 推論時に3つのモデルSHA、schema SHA、r4 protocol SHA、履歴state SHA、特徴量計算コード版を検証する。120通り確率和と1着周辺確率和=1を確認する。2025-08-31後のライブ履歴再生は独立holdout方針が確定してから設計する。',
          '- r4モデルと履歴stateの研究用bundle Artifactを保存する。app/へコピーしない。','',
          '## 未解決の実装事項','',
          '- 再現可能なAndroid推論エンジンと端末ベンチマーク。',
          '- 更新遅延/結果訂正/中止・返還と日次state versionの運用設計。',
          '- 独立した未開封期間でforecast精度を検証した後、通常チャット側で統合判断。','']
    (args.output/'v016_forecast_deployability.md').write_text('\n'.join(body))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest='cmd',required=True)
    a=sub.add_parser('odds-month'); a.add_argument('--month',type=int,choices=[7,8],required=True); a.add_argument('--raw',type=Path,required=True); a.add_argument('--metadata',type=Path,required=True); a.add_argument('--output',type=Path,required=True)
    b=sub.add_parser('provenance'); b.add_argument('--metadata',type=Path,required=True); b.add_argument('--output',type=Path,required=True)
    f=sub.add_parser('forecast'); f.add_argument('--model',type=Path,required=True); f.add_argument('--features',type=Path,required=True); f.add_argument('--raw',type=Path,required=True); f.add_argument('--model-artifact-digest',required=True); f.add_argument('--output',type=Path,required=True)
    z=sub.add_parser('publish'); z.add_argument('--input',type=Path,required=True); z.add_argument('--output',type=Path,required=True); z.add_argument('--run',required=True)
    args=ap.parse_args(); {'odds-month':odds_month,'provenance':source_provenance,'forecast':forecast,'publish':publish}[args.cmd](args)
