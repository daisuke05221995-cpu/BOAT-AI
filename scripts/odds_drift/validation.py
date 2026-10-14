"""Independent official HTML mapping check and semantic data checks."""
from __future__ import annotations
import argparse
import hashlib
import json
from html.parser import HTMLParser
from pathlib import Path

from analyze import COMBOS, ROOT
from full_panel import parse_final

class Tables(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tables=[]
        self.table=None
        self.row=None
        self.cell=None
    def handle_starttag(self,tag,attrs):
        if tag=='table':
            self.table=[]
        elif tag=='tr' and self.table is not None:
            self.row=[]
        elif tag in ('td','th') and self.row is not None:
            attrs=dict(attrs)
            self.cell={'text':'','rowspan':int(attrs.get('rowspan','1')),'colspan':int(attrs.get('colspan','1')),'class':attrs.get('class','')}
    def handle_data(self,data):
        if self.cell is not None:
            self.cell['text']+=data
    def handle_endtag(self,tag):
        if tag in ('td','th') and self.cell is not None:
            self.row.append(self.cell)
            self.cell=None
        elif tag=='tr' and self.row is not None:
            self.table.append(self.row)
            self.row=None
        elif tag=='table' and self.table is not None:
            self.tables.append(self.table)
            self.table=None

def parse_official_html(html):
    parser=Tables()
    parser.feed(html)
    table=next(t for t in parser.tables if sum('oddsPoint' in c['class'] for row in t for c in row)==120)
    values={}
    spans={}
    for row in table:
        # The HTML table declares the six first-place lanes left-to-right.
        if not any('oddsPoint' in c['class'] for c in row):
            continue
        expanded=[]
        column=0
        for cell in row:
            while column in spans:
                value,left=spans[column]
                expanded.append(value)
                if left==1:
                    del spans[column]
                else:
                    spans[column]=(value,left-1)
                column+=1
            value=cell['text'].strip()
            expanded.append(value)
            if cell['rowspan']>1:
                spans[column]=(value,cell['rowspan']-1)
            column+=1
        for first in range(1,7):
            offset=(first-1)*3
            second,third,odds=expanded[offset:offset+3]
            combo=f'{first}-{int(second)}-{int(third)}'
            assert combo in COMBOS
            values[combo]=float(odds)
    if set(values)!=set(COMBOS):
        raise ValueError('Incomplete independently labeled HTML table')
    return values

def main():
    args=argparse.ArgumentParser()
    args.add_argument('--root',type=Path,default=ROOT)
    root=args.parse_args().root
    (root/'output').mkdir(parents=True,exist_ok=True)
    checks=[]
    for html in sorted((root/'cache').glob('official_odds3t_*.html')):
        code=html.stem.split('_')[-1]
        final=root/f'cache/final_{code}.txt'
        if not final.exists():
            final=root/f'cache/final_probe_{code}.txt'
        if not final.exists():
            continue
        a=parse_official_html(html.read_text())
        b=parse_final(final.read_bytes())
        mismatches={c:[a[c],b[c]] for c in COMBOS if abs(a[c]-b[c])>.051}
        checks.append({'race_code':code,'htmlUrl':f'https://www.boatrace.jp/owpc/pc/race/odds3t?hd={code[:8]}&jcd={code[8:10]}&rno={int(code[10:12])}',
                       'htmlSha256':hashlib.sha256(html.read_bytes()).hexdigest(),
                       'finalSha256':hashlib.sha256(final.read_bytes()).hexdigest(),
                       'comparedCombinations':len(a),'mismatchCount':len(mismatches),'mismatches':mismatches})
    if not checks:
        raise SystemExit('No independent validation files')
    payload={'checks':checks,'allMatched':all(c['mismatchCount']==0 for c in checks),
             'limitation':'Small independent HTML mapping check; not a guarantee for missing/refund/dead-heat states.'}
    (root/'output/odds_drift_validation_20261014.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__':
    main()
