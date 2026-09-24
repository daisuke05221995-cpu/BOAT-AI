#!/usr/bin/env python3
"""Date fence, forward split, probability and market failure tests."""
import tempfile
from datetime import date
from pathlib import Path
import numpy as np
from v016_oof_study import rules, checked, keys, audit_p, market, candidate_probability

def fail(call):
    try: call()
    except ValueError: return
    raise AssertionError('Expected strict rejection')

proto,manifest=rules()
assert len(manifest['folds'])==4 and proto['selector']['maxCandidates']==3
with tempfile.TemporaryDirectory() as td:
    file=Path(td)/'cache.npz'
    def write(day,through,venues=(1,)):
        n=len(venues)
        np.savez(file,year=np.full(n,2025),month=np.full(n,day.month),
            day_ordinal=np.full(n,day.toordinal()),history_through=np.full(n,through.toordinal()),
            venue=np.asarray(venues),race_number=np.ones(n,dtype=int))
    write(date(2025,9,1),date(2025,8,31))
    fail(lambda:checked(file,'development'))
    write(date(2025,10,1),date(2025,9,30))
    fail(lambda:checked(file,'development'))
    write(date(2025,7,1),date(2025,7,1))
    fail(lambda:checked(file,'development'))
    write(date(2025,7,1),date(2025,6,30),(1,1))
    fail(lambda:keys(checked(file,'development')))
    write(date(2025,7,1),date(2025,6,30))
    assert len(keys(checked(file,'development')))==1

p=np.full((2,120),1/120.)
assert audit_p(p).shape==(2,6)
bad=p.copy(); bad[0,0]=np.nan
fail(lambda:audit_p(bad))
bad=p.copy(); bad[0,0]=0
fail(lambda:audit_p(bad))
c={'usable':np.ones(2,bool),'odds_usable':np.ones(2,bool),'odds':np.ones((2,120))*20}
c['odds'][1,0]=np.nan
m,g=market(c)
assert g.tolist()==[True,False] and np.isclose(m[0].sum(),1) and m[1].sum()==0
assert np.allclose(candidate_probability('log_residual_half',p,m.copy()+1/120,{}).sum(axis=1),1)
print('OOF guard and probability tests passed')
