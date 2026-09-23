#!/usr/bin/env python3
from pathlib import Path
p=Path('scripts/v016_r3_walkforward.py')
t=p.read_text()
old="""    total = summarize(stake, payout, counts)\n    months = {\n"""
new="""    total = summarize(stake, payout, counts)\n    total['largestHitPayout'] = int(payout.max(initial=0))\n    months = {\n"""
if t.count(old)!=1: raise SystemExit(f'expected one summarize block, found {t.count(old)}')
t=t.replace(old,new,1)
p.write_text(t)
print('r3 largest-hit accounting fixed')
