#!/usr/bin/env python3
from datetime import date
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/'scripts'))
import v016_q4_forecast_holdout as q

p=q.preregistration()
assert p['scope']['forecastOnly'] is True
assert p['scope']['marketInputs'] is False and p['scope']['oddsAcquisition'] is False
assert p['scope']['retraining'] is False and p['scope']['postHoldoutRescue'] is False
assert p['releaseGate']['autoBuyMustRemainOff'] is True
assert q.START==date(2025,10,1) and q.END==date(2025,12,31)
assert (q.END-q.START).days+1==92
assert q.SEPT_START==date(2025,9,1) and q.SEPT_END==date(2025,9,30)
for kind in ('programs','previews','results'):
    u=q.source_url(date(2025,10,1),kind)
    assert '/2025/20251001.json' in u
try:
    q.source_url(date(2026,1,1),'programs')
    raise AssertionError('Q4 fence failed')
except ValueError: pass
try:
    q.source_url(date(2025,10,1),'odds')
    raise AssertionError('odds fence failed')
except ValueError: pass
u=q.source_url(date(2025,9,1),'programs',True)
assert '/2025/20250901.json' in u
print('Q4 final forecast guards PASS; no network access performed')
