"""Safety/accounting checks for research; no production dependencies."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
import v016_core_research as core

class ResearchTests(unittest.TestCase):
    def test_budget_and_settlement(self):
        p=np.zeros((3,120)); p[0,:3]=.2; p[1,:4]=.15
        odds=np.ones_like(p)*10
        cfg={'maxOdds':20,'minEv':1.,'minProbability':.01,'maxPoints':4}
        chosen,units,count=core.tickets(p,odds,cfg)
        self.assertEqual(units.sum(axis=1).tolist(),[12,12,0])
        self.assertEqual(count.tolist(),[3,4,0])
        self.assertEqual(units[0].tolist(),[4,4,4,0])
        self.assertEqual(int((units[0]*(chosen[0]==1)).sum()*1000),4000)

    def test_does_not_force_monthly_profits(self):
        self.assertTrue(core.screen_pass({'purchaseRaces':150,'roi':105.,
            'largestHitShare':10.,'roiWithoutLargestHit':100.}))
        self.assertFalse(core.screen_pass({'purchaseRaces':150,'roi':104.999,
            'largestHitShare':10.,'roiWithoutLargestHit':100.}))

    def test_initial_drawdown_and_no_buys(self):
        stats=core.summarize(np.array([1200,1200]),np.array([0,3000]),np.array([3,3]))
        self.assertEqual(stats['maxDrawdown'],1200)
        self.assertEqual(stats['roi'],125.)
        self.assertEqual(core.summarize(np.zeros(1),np.zeros(1),np.zeros(1))['roi'],0.)

    def test_q4_rejected_before_outcomes(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'bad.npz'
            # No outcome fields at all: rejection must happen on dates alone.
            np.savez(p,year=[2025],month=[10],day_ordinal=[core.date(2025,10,1).toordinal()])
            with self.assertRaisesRegex(ValueError,'February-September'):
                core.load_cache(p,2025)
            with self.assertRaisesRegex(ValueError,'Forbidden months'):
                core.load_prepared(p,2025)

    def test_selection_rejects_incomplete_matrix(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError,'matrix'):
                core.select(Namespace(input=Path(tmp)))

    def test_manifest_tamper_rejected(self):
        from argparse import Namespace
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'manifest.json'
            core.dump(p,{'selectedConfig':None,'manifestHash':'bad'})
            with self.assertRaisesRegex(ValueError,'modified'):
                core.confirm(Namespace(manifest=p))

if __name__=='__main__': unittest.main()
