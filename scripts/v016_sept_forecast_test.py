#!/usr/bin/env python3
"""Boundary, source isolation, result-only label, parity math, and paired bootstrap guards."""
from datetime import date
from pathlib import Path
import tempfile

import numpy as np

from v016_sept_forecast_holdout import (COMBOS, baseline_prob, day_guard, finish_index,
                                        keys, load_features, paired_bootstrap,
                                        preregistration, source_url)

assert preregistration()['scope']['oddsAcquisition'] is False
for d in (date(2025,8,31),date(2025,10,1),date(2025,12,31)):
    try: source_url(d,'results')
    except ValueError: pass
    else: raise AssertionError('Forbidden race source URL')
for kind in ('odds','payouts'):
    try: source_url(date(2025,9,1),kind)
    except ValueError: pass
    else: raise AssertionError('Forbidden market/settlement URL')
assert '20250901.json' in source_url(date(2025,9,1),'programs')

program={'boats':[{'racer_boat_number':i,'racer_number':100+i} for i in range(1,7)]}
result={'boats':[{'racer_boat_number':i,'racer_number':100+i,'racer_place_number':i} for i in range(1,7)],
        'payouts':{'trifecta':[{'combination':'6-5-4','amount':999999}]}}
assert tuple(COMBOS[finish_index(program,result)])==(0,1,2)
result['boats'][0]['racer_number']=222
try: finish_index(program,result)
except ValueError: pass
else: raise AssertionError('Mismatched racer identity accepted')

b=np.zeros((2,6,30),np.float32); b[:,:,15]=6.8; b[:,:,16]=.15; b[:,:,17]=np.arange(1,7)
q=baseline_prob({'current':b})
assert q.shape==(2,120) and np.allclose(q.sum(axis=1),1)
assert np.allclose(q[0],q[1]) and np.all(q>=0)
days=np.repeat([date(2025,9,i).toordinal() for i in range(1,31)],2)
labels=np.zeros(60,dtype=int); a=np.tile(q[0],(60,1)); z=np.tile(q[0],(60,1))
assert paired_bootstrap(days,a,z,labels,{'replicates':2000,'seed':16092025})['trifectaLogloss']['ci95']==[0.0,0.0]
with tempfile.TemporaryDirectory() as d:
    path=Path(d)/'sept.npz'
    np.savez(path,day_ordinal=np.asarray([date(2025,9,1).toordinal()]*2),month=np.asarray([9,9]),
             venue=np.asarray([1,1]),race_number=np.asarray([1,1]),actual_index=np.asarray([0,0]),
             usable=np.asarray([True,True]),current=b,global_features=np.zeros((2,22)),
             history=np.zeros((2,6,32)),reaction=np.zeros((2,6,20)),
             history_through=np.asarray([date(2025,8,31).toordinal()]*2),
             boat_names=np.asarray(['x']),history_names=np.asarray(['h']),reaction_names=np.asarray(['r']),
             combos=np.asarray(['-'.join(str(v+1) for v in x) for x in COMBOS]),year=np.asarray([2025]))
    try: load_features(path)
    except ValueError: pass
    else: raise AssertionError('Duplicate race keys accepted')
    with np.load(path,allow_pickle=False) as old: c={k:old[k] for k in old.files}
    c['race_number']=np.asarray([1,2]); c['day_ordinal'][1]=date(2025,10,1).toordinal()
    np.savez(path,**c)
    try: load_features(path)
    except ValueError: pass
    else: raise AssertionError('Q4 row accepted')
print('September preregistration, Q4, source isolation, finish-label and paired-bootstrap guards passed')
