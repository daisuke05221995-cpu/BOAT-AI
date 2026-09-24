#!/usr/bin/env python3
import copy
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch
import numpy as np
from v016_r4_features import guard_day, source_url, read_cache, COMBO_TEXT, CURRENT_NAMES, GLOBALS, result_label
from v016_r4_player_history import PlayerHistory, enrich
from v016_r4_model import inputs
from v016_r2_model import predict

def fixture():
    days=np.array([date(2024,1,1).toordinal()]*2+[date(2024,1,2).toordinal()])
    b=np.ones((3,6,len(CURRENT_NAMES)),np.float32)
    b[:,:,15]=np.linspace(6.7,6.9,6); b[:,:,16]=np.linspace(.1,.2,6); b[:,:,17]=np.arange(1,7); b[:,:,24]=0
    return dict(year=np.array([2024]),combos=COMBO_TEXT,day_ordinal=days,month=np.ones(3,int),venue=np.ones(3,int),
        race_number=np.array([1,2,1]),actual_index=np.array([0,20,0]),amount=np.array([1000]*3),
        current=b,global_features=np.ones((3,len(GLOBALS)),np.float32),racer_id=np.tile(np.arange(4001,4007),(3,1)),
        racer_class=np.ones((3,6),int),usable=np.ones(3,bool),odds_usable=np.ones(3,bool),odds=np.ones((3,120))*20)

class Tests(unittest.TestCase):
    def test_q4_before_network_and_september_lock(self):
        with patch('urllib.request.urlopen') as network:
            for d in [date(2025,10,1),date(2025,12,31),date(2026,1,1)]:
                with self.assertRaisesRegex(ValueError,'date fence'):
                    source_url('results',d,{'repo':'x','commit':'x'},True)
            with self.assertRaises(ValueError): guard_day(date(2025,9,1))
            guard_day(date(2025,9,30),True); guard_day(date(2025,8,31))
            network.assert_not_called()

    def test_cache_fence_before_outcome_decoding(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'sealed.npz'
            np.savez(path,day_ordinal=[date(2025,10,1).toordinal()],month=[10],actual_index=np.array([{}],object))
            with self.assertRaisesRegex(ValueError,'date fence'): read_cache(path,True)

    def test_same_day_label_mutation_and_future_effect(self):
        c=fixture(); first=enrich(c,PlayerHistory())
        changed=copy.deepcopy(c); changed['actual_index'][:2]=119; changed['amount'][:]=999999
        second=enrich(changed,PlayerHistory())
        for key in ['history','reaction']:
            np.testing.assert_allclose(first[key][:2],second[key][:2])
        self.assertFalse(np.allclose(first['history'][2],second['history'][2]))
        self.assertTrue(np.all(first['history_through']<first['day_ordinal']))

    def test_future_label_never_changes_past(self):
        c=fixture(); baseline=enrich(c,PlayerHistory()); c['actual_index'][2]=119
        changed=enrich(c,PlayerHistory())
        np.testing.assert_allclose(baseline['history'],changed['history'])
        np.testing.assert_allclose(baseline['reaction'],changed['reaction'])

    def test_same_day_order_invariance(self):
        c=fixture(); first=enrich(c,PlayerHistory()); swap=np.array([1,0,2])
        reordered={k:v if k in ('year','combos') else v[swap] for k,v in c.items()}
        second=enrich(reordered,PlayerHistory())
        np.testing.assert_allclose(first['history'],second['history'][swap],atol=1e-6)
        np.testing.assert_allclose(first['reaction'],second['reaction'][swap],atol=1e-5)

    def test_id_odds_labels_absent_from_model_inputs(self):
        c=enrich(fixture(),PlayerHistory()); changed=copy.deepcopy(c)
        changed['racer_id'][:]=9999; changed['odds'][:]=999999; changed['actual_index'][:]=119; changed['amount'][:]=999999
        for variant in ['current','history','reaction']:
            a=inputs(c,variant); b=inputs(changed,variant)
            for key in a: np.testing.assert_array_equal(a[key],b[key])
            self.assertNotIn('racer_id',a); self.assertNotIn('actual_index',a)
        np.testing.assert_allclose(predict(inputs(c,'reaction'),'fundamental',{}),1/120,atol=1e-8)

    def test_shrink_and_signed_self_delta(self):
        h=PlayerHistory(); a,r,f=h.snapshot(4001,1,1,6.6,.1,False,1)
        self.assertEqual(a[0],0); self.assertLess(r[0],0); self.assertLess(r[2],0)
        h.commit_day(1,[(4001,1,1,6.6,.1,np.array([1,1,1]),f)])
        a,r,_=h.snapshot(4001,1,1,6.5,.09,False,2)
        self.assertEqual(a[0],1); self.assertLess(a[1],1); self.assertGreater(a[1],0)
        with self.assertRaises(ValueError): h.snapshot(4001,1,1,6.5,.09,False,1)

    def test_actual_st_and_course_not_read(self):
        program={'boats':[{'racer_boat_number':i,'racer_number':4000+i} for i in range(1,7)]}
        result={'boats':[{'racer_boat_number':i,'racer_number':4000+i,'racer_place_number':i,
                         'racer_start_timing':999,'racer_course_number':99} for i in range(1,7)],
                'payouts':{'trifecta':[{'combination':'1-2-3','amount':1000}]}}
        self.assertEqual(result_label(result,program),(0,1000))
        for row in result['boats']: row['racer_start_timing']=-999; row['racer_course_number']=-99
        self.assertEqual(result_label(result,program),(0,1000))
        result['boats'][0]['racer_number']=9999
        with self.assertRaisesRegex(ValueError,'racer-ID mismatch'): result_label(result,program)
        result['boats'][0]['racer_place_number']=None
        self.assertIsNone(result_label(result,program))

if __name__=='__main__': unittest.main()
