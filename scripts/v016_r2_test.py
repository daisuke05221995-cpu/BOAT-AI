#!/usr/bin/env python3
"""Probability, prior-offset, outcome-isolation and date-fence tests."""
import unittest
from datetime import date
import numpy as np
from v016_r2_features import allowed, extract, FEATURES, GLOBALS
from v016_r2_model import COMBOS, context, rows, predict, objective, metric

class Data:
    def __init__(self,y): self.y=y
    def get_label(self): return self.y

def fixture(n=3):
    rng=np.random.default_rng(16); p=rng.uniform(.1,3,(n,120)); p/=p.sum(axis=1,keepdims=True)
    return dict(year=np.array([2024]),combos=np.array(['-'.join(map(str,r+1)) for r in COMBOS]),
                month=np.ones(n,int),boat=rng.normal(size=(n,6,len(FEATURES))).astype(np.float32),
                global_features=rng.normal(size=(n,len(GLOBALS))).astype(np.float32),
                venue=np.ones(n,int),race_number=np.arange(n)+1,market_p=p,
                actual_index=np.zeros(n,int),amount=np.ones(n)*100,usable=np.ones(n,bool))

class Tests(unittest.TestCase):
    def test_fence(self):
        for d in [date(2025,1,1),date(2025,10,1),date(2025,12,31),date(2023,4,30),date(2026,1,1)]:
            with self.assertRaises(ValueError): allowed(d)
        allowed(date(2024,12,31)); allowed(date(2023,5,1))

    def test_market_chain_and_outcome_isolation(self):
        c=fixture(); p=predict(c,'residual',{})
        np.testing.assert_allclose(p,c['market_p'],atol=1e-8)
        c['actual_index'][:]=119; c['amount'][:]=999999
        np.testing.assert_array_equal(p,predict(c,'residual',{}))
        c.pop('actual_index'); c.pop('amount')
        np.testing.assert_array_equal(p,predict(c,'residual',{}))
        np.testing.assert_allclose(predict(c,'fundamental',{}),1/120,atol=1e-8)

    def test_objective_gradient(self):
        rng=np.random.default_rng(19)
        for k in [4,5,6]:
            z=rng.normal(size=k*2); y=np.eye(k)[[1,2]].ravel(); data=Data(y)
            g,h=objective(k)(z,data)
            for i in range(len(z)):
                hi=z.copy(); lo=z.copy(); hi[i]+=1e-5; lo[i]-=1e-5
                numerical=(metric(k)(hi,data)[1]-metric(k)(lo,data)[1])*2/(2e-5)
                self.assertAlmostEqual(g[i],numerical,places=6)
            self.assertTrue((h>0).all())

    def test_fundamental_does_not_use_market(self):
        c=fixture(); prefix=COMBOS[c['actual_index']][:,:1]
        x,base,_=rows(context(c),np.arange(3),prefix,'fundamental')
        c['market_p']=c['market_p'][:,::-1]
        xx,bb,_=rows(context(c),np.arange(3),prefix,'fundamental')
        np.testing.assert_array_equal(x,xx); np.testing.assert_array_equal(base,bb)

    def test_lightgbm_offset(self):
        import lightgbm as lgb
        rng=np.random.default_rng(3); k=4; x=rng.normal(size=(800,3)); base=rng.normal(size=800)
        y=np.eye(k)[np.argmax(x[:,0].reshape(-1,k),axis=1)].ravel()
        ds=lgb.Dataset(x,label=y,init_score=base,free_raw_data=False)
        model=lgb.train(dict(objective=objective(k),metric='None',num_leaves=3,verbosity=-1,num_threads=2),
                        ds,num_boost_round=5,valid_sets=[ds],feval=metric(k))
        manual=metric(k)(model.predict(x,raw_score=True,num_threads=2)+base,Data(y))[1]
        self.assertAlmostEqual(manual,model.best_score['training']['conditional_logloss'],places=8)

    def test_missing_and_wrong_race(self):
        b,g,ok=extract(None,None,date(2024,1,1),1,1); self.assertFalse(ok)
        with self.assertRaises(ValueError): extract({'date':'2024-01-02'},{'date':'2024-01-01'},date(2024,1,1),1,1)

if __name__=='__main__': unittest.main()
