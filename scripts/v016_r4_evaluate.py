#!/usr/bin/env python3
"""Probability increment first, then preregistered policies; at most one freeze."""
import argparse
import json
from pathlib import Path
import numpy as np
from v016_core_research import canonical, digest, dump, normalize, tickets, summarize
from v016_r4_features import PROTOCOL, COMBOS, read_cache, frozen_lock
from v016_r4_model import quality, code_hashes

def prediction(path,c):
    with np.load(path,allow_pickle=False) as z:
        for key in ['day_ordinal','venue','race_number']:
            if not np.array_equal(z[key],c[key]): raise ValueError('Prediction alignment mismatch')
        p=z['p'].astype(np.float64)
    if p.shape!=(len(c['month']),120) or not np.allclose(p.sum(axis=1),1,atol=1e-6) or not np.isfinite(p).all():
        raise ValueError('Invalid probabilities')
    return p

def difference(p,base,actual,days):
    ix=np.arange(len(p)); delta=-np.log(np.maximum(p[ix,actual],1e-15))+np.log(np.maximum(base[ix,actual],1e-15))
    _,inv=np.unique(days,return_inverse=True); sums=np.bincount(inv,weights=delta); count=np.bincount(inv)
    rng=np.random.default_rng(1604); samples=rng.integers(0,len(count),(1000,len(count)))
    draws=sums[samples].sum(axis=1)/count[samples].sum(axis=1)
    return {'loglossDifference':float(delta.mean()),'dailyBootstrap95':np.quantile(draws,[.025,.975]).tolist()}

def groups(c,p):
    winner=COMBOS[p.argmax(axis=1),0]; ix=np.arange(len(winner))
    count=c['history'][ix,winner,0]; z=c['reaction'][ix,winner,1]
    weakness=np.maximum(c['reaction'][:,0,1],0)+np.maximum(c['reaction'][:,0,3],0)
    return {'month':c['month'].astype(str),
            'predictedWinnerPreviewCourse':c['current'][ix,winner,17].astype(str),
            'predictedWinnerHistoryCountBucket':np.select([count<20,count<50,count<100,count<200],['0-19','20-49','50-99','100-199'],default='200+'),
            'predictedWinnerExhibitionZBucket':np.select([z<=-.5,z>=.5],['improved','worse'],default='usual'),
            'laneOneWeaknessBucket':np.select([weakness<.5,weakness<1.5],['low','medium'],default='high')}

def policy_mask(c,p,name):
    good=c['usable']&c['odds_usable']; mask=np.broadcast_to(good[:,None],p.shape).copy()
    if name=='reaction':
        h=c['history']; r=c['reaction']; first=COMBOS[:,0]
        boat=(h[:,:,0]>=20)&(h[:,:,4]>=5)&(((r[:,:,1]<=-.5)&(r[:,:,11]>h[:,:,7]))|((r[:,:,3]<=-.5)&(r[:,:,13]>h[:,:,5])))
        safe=np.where(np.isfinite(c['odds'])&(c['odds']>0),c['odds'],1.)
        market=normalize(1/safe)
        mask &= boat[:,first] & (p/market>=1.4)
    elif name!='core': raise ValueError('Unregistered policy')
    return mask

def evaluate_policy(c,p,name,phase):
    proto=json.loads(PROTOCOL.read_text()); cfg=proto['policies']['core']
    masked=np.where(policy_mask(c,p,name),p,0.)
    odds=np.where(np.isfinite(c['odds']),c['odds'],0)
    chosen,units,counts=tickets(masked,odds,cfg)
    stake=np.where(counts>0,cfg['budget'],0); payout=(units*(chosen==c['actual_index'][:,None])).sum(axis=1)*c['amount']
    expected=(units*np.take_along_axis(p*odds,chosen,axis=1)*100).sum(axis=1)
    total=summarize(stake,payout,counts)
    total['expectedRoi']=float(100*expected.sum()/stake.sum()) if stake.sum() else None
    total['calibrationGap']=abs(total['expectedRoi']-total['roi']) if stake.sum() else None
    bucketed={group:{label:summarize(stake[values==label],payout[values==label],counts[values==label]) for label in sorted(set(values))}
              for group,values in groups(c,p).items()}
    gate=proto['developmentGate' if phase=='development' else 'frozenCheckGate']; reasons=[]
    for key in ['roi','purchaseRaces','hits']:
        if total[key]<gate[key]: reasons.append(f'{key} < {gate[key]}')
    if total['largestHitShare']>gate['largestHitShareMax']: reasons.append('largest hit dependence')
    if total['roiWithoutLargestHit']<gate['roiWithoutLargestHitMin']: reasons.append('ROI excluding largest hit < 100')
    if total['calibrationGap'] is None or total['calibrationGap']>gate['maxAbsoluteExpectedVsActualRoiGap']:
        reasons.append('expected/realized ROI calibration gap > 15pp or no purchases')
    return {'policy':name,'phase':phase,'total':total,'buckets':bucketed,'partialPeriodPass':not reasons,
            'rejectionReasons':reasons,'annualQualified':False}

def select(args):
    c=read_cache(args.cache)
    if set(c['month'])!={7,8}: raise ValueError('Selection is July-August only')
    p={}; summaries={}; good=c['usable']&c['odds_usable']
    for variant in ['current','history','reaction']:
        path=args.input/f'{variant}.npz'; p[variant]=prediction(path,c); summaries[variant]=json.loads(path.with_suffix('.json').read_text())
        if summaries[variant]['featureCacheSha256']!=digest(args.cache): raise ValueError('Prediction cache changed')
        if summaries[variant]['manifest']['codeSha256']!=code_hashes(): raise ValueError('Model code changed')
    actual=c['actual_index'][good]; days=c['day_ordinal'][good]
    changes={name:difference(p[name][good],p['current'][good],actual,days) for name in ['history','reaction']}
    changes['reaction_vs_history']=difference(p['reaction'][good],p['history'][good],actual,days)
    model=summaries['reaction']['model']; baseline=summaries['current']['model']; d=changes['reaction']; reasons=[]
    if d['loglossDifference']>-.002: reasons.append('reaction logloss gain < 0.002')
    if d['dailyBootstrap95'][1]>=0: reasons.append('paired daily interval does not exclude zero')
    if model['brier']>baseline['brier']: reasons.append('Brier worse than current-only')
    if model['topChoiceEce']>baseline['topChoiceEce']+.005: reasons.append('top-choice calibration worse than allowed')
    policy=[]
    if not reasons:
        policy=[evaluate_policy(c,p['reaction'],name,'development') for name in ['core','reaction']]
    passing=sorted([x for x in policy if x['partialPeriodPass']],key=lambda x:(-x['total']['roiWithoutLargestHit'],-x['total']['purchaseRaces'],x['policy']))
    candidate=None
    if passing:
        candidate={'variant':'reaction','policy':passing[0]['policy'],'policyDefinitions':json.loads(PROTOCOL.read_text())['policies'],
                   'protocolSha256':digest(PROTOCOL),'codeSha256':code_hashes(),
                   'modelManifestSha256':summaries['reaction']['modelManifestSha256'],
                   'schemaSha256':summaries['reaction']['manifest']['schemaSha256'],
                   'historyStateSha256':digest(args.state),'trainingRunId':args.run,'frozenBeforeSeptember':True}
    lock={'candidate':candidate,'freezeSha256':canonical(candidate) if candidate else None,'holdoutOpened':False}
    dump(args.output/'frozen_candidate.json',lock)
    calibration={group:{label:quality(p['reaction'][good&(values==label)],c['actual_index'][good&(values==label)])
                       for label in sorted(set(values[good]))} for group,values in groups(c,p['reaction']).items()}
    result={'runId':args.run,'protocolSha256':digest(PROTOCOL),'period':'2025-07-01..2025-08-31',
            'probability':summaries,'increment':changes,'qualityPass':not reasons,'qualityRejectionReasons':reasons,
            'probabilityBuckets':calibration,'policies':policy,'policyEvaluationStatus':'evaluated' if not reasons else 'not_evaluated_quality_gate_failed',
            'candidate':candidate,'freezeSha256':lock['freezeSha256'],'decision':'frozen_candidate_for_september' if candidate else 'reject_r4_development',
            'holdoutOpened':False,'septemberOpened':False,'annualGateStatus':'NOT_TESTED_Q4_SEALED','releaseQualified':False,'longshotStarted':False}
    dump(args.output/'development_result.json',result)
    if args.github_output:
        with args.github_output.open('a') as file: file.write('candidate='+str(bool(candidate)).lower()+'\n')
    print(json.dumps({'qualityPass':not reasons,'reasons':reasons,'policies':[{k:x[k] for k in ['policy','total','partialPeriodPass']} for x in policy],'candidate':bool(candidate)}))

def confirm(args):
    lock=frozen_lock(args.lock); c=read_cache(args.cache,True)
    if set(c['month'])!={9}: raise ValueError('Confirmation is September only')
    p=prediction(args.prediction,c); meta=json.loads(args.prediction.with_suffix('.json').read_text())
    if meta['modelManifestSha256']!=lock['candidate']['modelManifestSha256'] or meta['featureCacheSha256']!=digest(args.cache):
        raise ValueError('Frozen confirmation mismatch')
    result={'phase':'frozen_september','probability':meta,'policy':evaluate_policy(c,p,lock['candidate']['policy'],'september'),
            'freezeSha256':lock['freezeSha256'],'holdoutOpened':False,'septemberOpened':True,
            'annualGateStatus':'NOT_TESTED_Q4_SEALED','releaseQualified':False,'longshotStarted':False}
    dump(args.output,result)

def publish(args):
    development=json.loads((args.input/'development_result.json').read_text())
    confirmation_path=args.input/'september_result.json'
    confirmation=json.loads(confirmation_path.read_text()) if confirmation_path.exists() else None
    if development['candidate'] and confirmation is None: raise ValueError('Candidate confirmation missing')
    result={'runId':args.run,'development':development,'confirmation':confirmation,
            'holdoutOpened':False,'releaseQualified':False,'annualGateStatus':'NOT_TESTED_Q4_SEALED','longshotStarted':False}
    dump(args.output,result)
    audit={}
    for path in args.metadata.rglob('*.json'):
        if path.name=='history_state.json': continue
        data=json.loads(path.read_text()); data.pop('sourceHashes',None)
        audit[str(path.relative_to(args.metadata))]=data
    dump(args.output.with_name('v016_r4_feature_audit.json'),audit)

if __name__=='__main__':
    p=argparse.ArgumentParser(); s=p.add_subparsers(dest='command',required=True)
    a=s.add_parser('select'); a.add_argument('--cache',type=Path,required=True); a.add_argument('--state',type=Path,required=True)
    a.add_argument('--input',type=Path,required=True); a.add_argument('--output',type=Path,required=True); a.add_argument('--run',required=True)
    a.add_argument('--github-output',type=Path)
    b=s.add_parser('confirm'); b.add_argument('--cache',type=Path,required=True); b.add_argument('--lock',type=Path,required=True)
    b.add_argument('--prediction',type=Path,required=True); b.add_argument('--output',type=Path,required=True)
    z=s.add_parser('publish'); z.add_argument('--input',type=Path,required=True); z.add_argument('--metadata',type=Path,required=True)
    z.add_argument('--output',type=Path,required=True); z.add_argument('--run',required=True)
    args=p.parse_args(); {'select':select,'confirm':confirm,'publish':publish}[args.command](args)
