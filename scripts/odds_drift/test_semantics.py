import itertools
import unittest
from copy import deepcopy
from datetime import datetime
from analyze import COMBOS, parse_snapshot
from full_panel import parse_final

class OddsSemanticsTest(unittest.TestCase):
    def snapshot(self):
        row={'レースコード':'202610141401','レース日':'2026-10-14','締切時刻':'08:35','取得日時':'2026-10-13T23:30:00+00:00'}
        row.update({'3連単_'+c:str(i+2) for i,c in enumerate(COMBOS)})
        return row

    def final_body(self):
        lines=['data=','1']
        for first in range(6):
            lines.append('\t'.join(['選手名']+[str(first*20+i+2) for i in range(20)]+['0']*5))
        return ('\n'.join(lines)+'\n').encode()

    def test_timezone_and_payout_scale(self):
        _,odds,_,minutes=parse_snapshot(self.snapshot())
        self.assertEqual(minutes,5.)
        # Official payouts are JPY per 100 JPY, not an already scaled odds number.
        self.assertEqual(7730/100,77.3)
        self.assertNotEqual(7730,77.3)

    def test_all_120_distinct_canonical_combinations(self):
        self.assertEqual(set(COMBOS),{'-'.join(map(str,p)) for p in itertools.permutations(range(1,7),3)})
        self.assertEqual(len(COMBOS),120)

    def test_reject_incomplete_and_nonfinite_snapshot(self):
        for value in ['', '0', '-1', 'nan', 'inf']:
            row=self.snapshot()
            row['3連単_1-2-3']=value
            with self.assertRaises(ValueError):parse_snapshot(row)

    def test_timestamp_requires_timezone(self):
        row=self.snapshot()
        row['取得日時']='2026-10-14T08:30:00'
        with self.assertRaises(ValueError):parse_snapshot(row)

    def test_ties_use_android_lexical_rule(self):
        row=self.snapshot()
        row['3連単_1-2-4']=row['3連単_1-2-3']
        _,_,ranks,_=parse_snapshot(row)
        self.assertEqual(ranks['1-2-3'],1)
        self.assertEqual(ranks['1-2-4'],2)

    def test_final_mapping_ignores_padding(self):
        odds=parse_final(self.final_body())
        self.assertEqual(odds['1-2-3'],2.)
        self.assertEqual(odds['2-1-3'],22.)
        self.assertEqual(odds['6-5-4'],121.)
        self.assertEqual(len(odds),120)

    def test_final_rejects_invalid_status(self):
        with self.assertRaises(ValueError):parse_final(self.final_body().replace(b'data=\n1\n',b'data=\n0\n'))

    def test_final_rejects_zero_real_odds(self):
        with self.assertRaises(ValueError):parse_final(self.final_body().replace(b'\t2\t',b'\t0\t',1))

if __name__=='__main__':unittest.main()
