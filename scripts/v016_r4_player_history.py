#!/usr/bin/env python3
"""Day-batched, ID-keyed history. No same-day outcome enters any same-day feature."""
import argparse
import bisect
import json
from pathlib import Path
import numpy as np
from v016_core_research import dump, digest
from v016_r4_features import read_cache, subset, frozen_lock, CURRENT_NAMES, COMBOS, PROTOCOL

HISTORY_NAMES=['player_count','player_win','player_top2','player_top3','course_count','course_win','course_top2','course_top3',
 'player_ex_mean','player_ex_sd','player_preview_st_mean','player_preview_st_sd',
 'course_ex_mean','course_ex_sd','course_preview_st_mean','course_preview_st_sd']
for w in (30,60,90,180): HISTORY_NAMES.extend([f'w{w}_count',f'w{w}_win',f'w{w}_top2',f'w{w}_top3'])
REACTION_NAMES=['ex_delta_self','ex_z_self','st_delta_self','st_z_self',
 'ex_delta_course','ex_z_course','st_delta_course','st_z_course',
 'fast_count','fast_win','fast_top2','fast_top3','good_st_count','good_st_win','good_st_top2','good_st_top3',
 'changed_count','changed_win','changed_top2','changed_top3']
RELATIVE_NAMES=['ex_rank','preview_st_rank','ex_gap_best','ex_gap_worst','ex_gap_lane1']

def empty(): return [0.,0.,0.,0.,0.,0.,0.,0.]  # count, wins/top2/top3, ex/ex², previewST/ST²

def add(stats,y,ex,st):
    stats[0]+=1
    for i in range(3): stats[i+1]+=float(y[i])
    stats[4]+=float(ex); stats[5]+=float(ex*ex); stats[6]+=float(st); stats[7]+=float(st*st)

def rates(stats,prior):
    return (np.asarray(stats[1:4])+20*np.asarray(prior))/(stats[0]+20)

def moments(stats,prior):
    n=stats[0]; out=[]
    for j,(mean,sd) in zip((4,6),[(prior[0],prior[1]),(prior[2],prior[3])]):
        mu=(stats[j]+20*mean)/(n+20)
        var=(stats[j+1]+20*(sd*sd+mean*mean))/(n+20)-mu*mu
        out.extend([mu,max(np.sqrt(max(var,0)),.02)])
    return np.asarray(out)

class PlayerHistory:
    def __init__(self,state=None):
        self.state=state or {'stats':{},'recent':{},'lastDay':0,'updateRaces':0}

    def get(self,key): return self.state['stats'].get(key,empty())

    def snapshot(self,player,course,cls,ex,st,changed,day):
        if day<=self.state['lastDay']: raise ValueError('History is not strictly earlier than prediction day')
        p=str(int(player)); c=str(int(course)); global_rate=rates(self.get('global'),[1/6,1/3,1/2])
        course_rate=rates(self.get('c:'+c),global_rate); class_rate=rates(self.get('class:'+str(int(cls))),global_rate)
        ps=self.get('p:'+p); pcs=self.get('pc:'+p+':'+c)
        pr=rates(ps,(course_rate+class_rate)/2); pcr=rates(pcs,(pr+course_rate)/2)
        gm=moments(self.get('global'),[6.8,.15,.17,.08]); cm=moments(self.get('c:'+c),gm)
        pm=moments(ps,gm); pcm=moments(pcs,(pm+cm)/2)
        h=[ps[0],*pr,pcs[0],*pcr,*pm,*pcm]
        recent=self.state['recent'].get(p,{'days':[],'cumulative':[[0,0,0]]})
        for w in (30,60,90,180):
            left=bisect.bisect_left(recent['days'],day-w)
            n=len(recent['days'])-left
            wins=np.asarray(recent['cumulative'][-1])-np.asarray(recent['cumulative'][left])
            h.extend([n,*((wins+20*pr)/(n+20))])
        fast=self.get('fast:'+p+':'+c); good=self.get('good:'+p+':'+c); ch=self.get('changed:'+p)
        reaction=[ex-pm[0],(ex-pm[0])/pm[1],st-pm[2],(st-pm[2])/pm[3],
                  ex-pcm[0],(ex-pcm[0])/pcm[1],st-pcm[2],(st-pcm[2])/pcm[3],
                  fast[0],*rates(fast,pcr),good[0],*rates(good,pcr),ch[0],*rates(ch,pr)]
        flags=(bool(ex<pm[0]),bool(st<pm[2]),bool(changed))
        return np.asarray(h,np.float32),np.asarray(reaction,np.float32),flags

    def commit_day(self,day,updates):
        if day<=self.state['lastDay']: raise ValueError('Nonchronological/duplicate day update')
        for player,course,cls,ex,st,y,flags in updates:
            p=str(int(player)); c=str(int(course))
            keys=['global','c:'+c,'class:'+str(int(cls)),'p:'+p,'pc:'+p+':'+c]
            if flags[0]: keys.append('fast:'+p+':'+c)
            if flags[1]: keys.append('good:'+p+':'+c)
            if flags[2]: keys.append('changed:'+p)
            for key in keys: add(self.state['stats'].setdefault(key,empty()),y,ex,st)
            recent=self.state['recent'].setdefault(p,{'days':[],'cumulative':[[0,0,0]]})
            recent['days'].append(int(day)); recent['cumulative'].append((np.asarray(recent['cumulative'][-1])+y).astype(int).tolist())
        self.state['lastDay']=int(day); self.state['updateRaces']+=len(updates)//6

def enrich(c,history):
    n=len(c['month']); hh=np.zeros((n,6,len(HISTORY_NAMES)),np.float32); rr=np.zeros((n,6,len(REACTION_NAMES)),np.float32)
    rel=np.full((n,6,5),np.nan,np.float32); max_history_day=np.empty(n,np.int32)
    for step,day in enumerate(sorted(np.unique(c['day_ordinal'])),1):
        ix=np.flatnonzero(c['day_ordinal']==day); pending=[]
        # All snapshots for this day are complete before any of its outcomes are committed.
        for i in ix:
            max_history_day[i]=history.state['lastDay']
            if not c['usable'][i]: continue
            b=c['current'][i]; exs=b[:,15]; sts=b[:,16]
            rel[i,:,0]=1+(exs[:,None]>exs[None,:]).sum(axis=1)
            rel[i,:,1]=1+(sts[:,None]>sts[None,:]).sum(axis=1)
            rel[i,:,2]=exs-exs.min(); rel[i,:,3]=exs-exs.max(); rel[i,:,4]=exs-exs[0]
            flags=[]
            for lane in range(6):
                h,r,f=history.snapshot(c['racer_id'][i,lane],int(b[lane,17]),c['racer_class'][i,lane],
                                       b[lane,15],b[lane,16],b[lane,24],int(day))
                hh[i,lane]=h; rr[i,lane]=r; flags.append(f)
            # Labels are queued AFTER this race's snapshots; they affect no snapshot today.
            order=COMBOS[c['actual_index'][i]]
            for lane in range(6):
                y=np.array([lane==order[0],lane in order[:2],lane in order],int)
                pending.append((c['racer_id'][i,lane],int(b[lane,17]),c['racer_class'][i,lane],b[lane,15],b[lane,16],y,flags[lane]))
        history.commit_day(int(day),pending)
        if step%60==0: print(f'history: {step} days, players={len(history.state["recent"])}',flush=True)
    out=dict(c); out['current']=np.concatenate([c['current'],rel],axis=2)
    out['history']=hh; out['reaction']=rr; out['history_through']=max_history_day
    out['boat_names']=np.asarray(CURRENT_NAMES+RELATIVE_NAMES); out['history_names']=np.asarray(HISTORY_NAMES); out['reaction_names']=np.asarray(REACTION_NAMES)
    if np.any(max_history_day>=c['day_ordinal']): raise ValueError('Same-day/future history leak')
    return out

def build(args):
    september=bool(args.lock)
    if september:
        lock=frozen_lock(args.lock)
        if digest(args.state)!=lock['candidate']['historyStateSha256']: raise ValueError('Frozen history checkpoint changed')
        history=PlayerHistory(json.loads(args.state.read_text()))
    else:
        history=PlayerHistory(); seed=read_cache(args.seed)
        if set(seed['year'])!={2024}: raise ValueError('Seed must be 2024')
        enrich(seed,history)
    raw=read_cache(args.raw,september)
    if set(raw['year'])!={2025}: raise ValueError('r4 target must be 2025')
    c=enrich(raw,history)
    if not september and set(c['month'])!=set(range(1,9)): raise ValueError('Incomplete Jan-Aug cache')
    if september and set(c['month'])!={9}: raise ValueError('Confirmation must be September only')
    args.output.mkdir(parents=True,exist_ok=True)
    if september: splits={'september':np.ones(len(c['month']),bool)}
    else: splits={'train':c['month']<=6,'development':c['month']>=7}
    for name,take in splits.items():
        np.savez_compressed(args.output/f'{name}.npz',**subset(c,take))
    dump(args.output/'history_state.json',history.state)
    dump(args.output/'feature_metadata.json',{'protocolSha256':digest(PROTOCOL),'rawSha256':digest(args.raw),
         'seedSha256':digest(args.seed) if args.seed else None,'year':2025,'races':len(c['month']),
         'usableRaces':int((c['usable']&c['odds_usable']).sum()),'features':{'current':CURRENT_NAMES+RELATIVE_NAMES,'history':HISTORY_NAMES,'reaction':REACTION_NAMES},
         'registeredPlayers':len(history.state['recent']),'historyRaces':history.state['updateRaces'],
         'sameDayHistoryLeakCount':int((c['history_through']>=c['day_ordinal']).sum()),
         'historyCountQuantiles':np.quantile(c['history'][c['usable'],:,0],[0,.1,.5,.9,1]).tolist(),
         'holdoutOpened':False,'septemberOpened':september})

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('--seed',type=Path); p.add_argument('--raw',type=Path,required=True)
    p.add_argument('--state',type=Path); p.add_argument('--lock',type=Path); p.add_argument('--output',type=Path,required=True)
    build(p.parse_args())
