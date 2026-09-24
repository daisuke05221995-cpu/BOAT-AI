#!/usr/bin/env python3
"""Meaningful date, key, accounting and source boundaries for the integrity audit."""
import tempfile
from datetime import date
from pathlib import Path
import numpy as np
from v016_integrity_audit import allowed, checked_npz, payout_metrics, refund_markers, COMBO_TEXT

def rejects(fn):
    try: fn()
    except ValueError: return
    raise AssertionError('Guard failed open')

for day in (date(2025,9,1),date(2025,10,1),date(2024,7,1)):
    rejects(lambda d=day:allowed(d))
allowed(date(2025,7,1)); allowed(date(2025,8,31))

with tempfile.TemporaryDirectory() as tmp:
    path=Path(tmp)/'cache.npz'
    def write(day,races=(1,)):
        np.savez(path,day_ordinal=np.full(len(races),day.toordinal()),
                 month=np.full(len(races),day.month),venue=np.ones(len(races),int),
                 race_number=np.asarray(races),combos=COMBO_TEXT,
                 actual_index=np.zeros(len(races),int),amount=np.full(len(races),1230),
                 odds=np.full((len(races),120),12.3))
    write(date(2025,9,1)); rejects(lambda:checked_npz(path))
    write(date(2025,12,31)); rejects(lambda:checked_npz(path))
    write(date(2025,7,1),(1,1)); rejects(lambda:checked_npz(path))
    write(date(2025,7,1)); c=checked_npz(path)
    m=payout_metrics(c,np.ones(1,bool)); assert m['races']==m['exactStoredValue']==1
    c['odds'][0,0]=12.5; m=payout_metrics(c,np.ones(1,bool))
    assert m['exactStoredValue']==0 and m['withinAbsolute0_5']==1
    c['odds'][0,0]=np.nan; rejects(lambda:payout_metrics(c,np.ones(1,bool)))

assert refund_markers({'refund_boats':[2], 'payouts':{'trifecta':[]}})==['refund_boats']
assert refund_markers({'payouts':{'trifecta':[]}})==[]
print('Integrity date/key/settlement guards passed')
