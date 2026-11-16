import unittest
import sys
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from pipeline import qualify,generate,best_completed_month,JST
T="2026-11-16"
N=datetime(2026,11,16,10,0,tzinfo=JST)
def race(**kwargs):
    row={"race_id":"202611160112","status":"READY","decision":"BUY",
        "deadline_at":(N+timedelta(minutes=90)).isoformat(),
        "forecast_completed_at":(N-timedelta(minutes=1)).isoformat(),
        "odds_observed_at":(N-timedelta(minutes=1)).isoformat(),
        "model_version":"value-v1","odds_source":"official-pc",
        "quality_flags":[],"combinations":["1-2-3","1-3-2"],"stakes":[500,400]}
    row.update(kwargs)
    return row
class Test(unittest.TestCase):
    def test_paywall_and_no_leak(self):
        x=generate({"date":T,"races":[race()]},T,N,
                   {"month":"2026-05","hitRate":34.0,"purchaseHits":559,"purchaseRaces":1644})
        self.assertEqual(x["status"],"READY")
        self.assertEqual(x["price_yen"],100)
        self.assertIn("過去検証的中率34.0%",x["title"])
        free=" ".join(x["free_paragraphs"])
        self.assertIn("559",free)
        self.assertIn("1,644",free)
        self.assertIn("過去シミュレーション",free)
        self.assertNotIn("1-2-3",free)
        self.assertIn("1-2-3"," ".join(x["paid_paragraphs"]))
        self.assertIsNotNone(x["earliest_deadline_at"])
        self.assertEqual(x["generated_at"],N.isoformat())
    def test_missing_historical_stats_does_not_invent_hit_rate(self):
        x=generate({"date":T,"races":[race()]},T,N,{"month":"2026-05"})
        self.assertNotIn("34.0%",x["title"])
        self.assertNotIn("的中率："," ".join(x["free_paragraphs"]))
    def test_refuse_stale_invalid(self):
        for kw in ({"status":"PENDING"},{"decision":"SKIP"},{"odds_source":None},
                   {"deadline_at":(N+timedelta(minutes=1)).isoformat()},
                   {"deadline_at":(N+timedelta(minutes=20)).isoformat()},
                   {"race_id":"202611162512"},{"race_id":"202611160013"},
                   {"forecast_completed_at":(N-timedelta(minutes=30)).isoformat()},
                   {"odds_observed_at":(N-timedelta(minutes=30)).isoformat()},
                   {"combinations":["1-1-2","1-3-2"]},{"stakes":[500,-100]},
                   {"result":{"finish":"1-2-3"}},{"race_id":"202611150112"}):
            with self.subTest(kw=kw): self.assertIsNone(qualify(race(**kw),T,N))
    def test_no_buy_no_article(self):
        x=generate({"date":T,"races":[race(decision="SKIP")]},T,N,{})
        self.assertEqual(x["status"],"NO_ELIGIBLE_RACES")
    def test_best_historical_month(self):
        f=Path(__file__).resolve().parents[1]/"data/historical_backtest_2026.json"
        h=best_completed_month(f)
        self.assertEqual(h["month"],"2026-05")
        self.assertEqual(h["hitRate"],34.0)
        self.assertEqual(h["purchaseHits"],559)
        self.assertEqual(h["purchaseRaces"],1644)
        self.assertEqual(h["roi"],79.7)
if __name__=="__main__":unittest.main()
