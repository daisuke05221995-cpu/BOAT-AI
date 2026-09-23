import tempfile
import unittest
from pathlib import Path
import numpy as np
import v016_annual2024 as annual

class Tests(unittest.TestCase):
    def test_refuses_2025_before_outcomes(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.npz';np.savez(p,year=[2025])
            with self.assertRaisesRegex(ValueError,'Only 2024'):annual.load(p)
    def test_incomplete_calendar_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/'bad.npz';np.savez(p,year=[2024],month=[5,6,7,8,9])
            with self.assertRaisesRegex(ValueError,'Twelve months'):annual.load(p)
    def test_all_months_in_accounting(self):
        c={'month':np.arange(1,13),'odds':np.ones((12,120))*10,
           'p_power_0':np.zeros((12,120)), 'actual_index':np.zeros(12,dtype=int),
           'amount':np.ones(12,dtype=int)*1000}
        c['p_power_0'][:,0]=.2
        cfg={'family':'power','parameterIndex':0,'maxOdds':20,'minEv':1,
             'minProbability':.01,'maxPoints':3}
        r=annual.evaluate(c,cfg)
        self.assertEqual(len(r['months']),12)
        self.assertEqual(r['annual2024']['purchaseRaces'],12)
        self.assertEqual(r['annual2024']['stake'],14400)
        self.assertFalse(r['historicalNumericGatePassed']) # insufficient annual volume
        self.assertFalse(r['releaseQualified'])
if __name__=='__main__':unittest.main()
