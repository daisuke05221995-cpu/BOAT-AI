import unittest, sys
from pathlib import Path
from datetime import datetime,timedelta
sys.path.insert(0,str(Path(__file__).parent))
from pipeline import JST,generate
from publish_guard import validate
N=datetime(2026,11,16,10,0,tzinfo=JST)
D=N.date().isoformat()
def article():
    race={"race_id":"202611160112","status":"READY","decision":"BUY",
      "deadline_at":(N+timedelta(minutes=90)).isoformat(),
      "forecast_completed_at":(N-timedelta(minutes=1)).isoformat(),
      "odds_observed_at":(N-timedelta(minutes=1)).isoformat(),
      "model_version":"model","odds_source":"official",
      "combinations":["1-2-3"],"stakes":[100]}
    return generate({"date":D,"races":[race]},D,N,{"month":"2026-05","hitRate":34,"purchaseHits":559,"purchaseRaces":1644})
class Gate(unittest.TestCase):
    def test_all_good(self): self.assertIsNone(validate(article(),N))
    def test_stale(self): self.assertEqual(validate(article(),N+timedelta(minutes=13)),"ARTICLE_STALE_OR_FUTURE")
    def test_sale_expired(self):
        a=article();a["earliest_deadline_at"]=(N+timedelta(minutes=5)).isoformat()
        self.assertEqual(validate(a,N),"NOT_ENOUGH_TIME_TO_SELL")
    def test_free_leak(self):
        a=article();a["free_paragraphs"].append("本命 1-2-3")
        self.assertEqual(validate(a,N),"PICKS_LEAK_IN_FREE_SECTION")
    def test_price(self):
        a=article();a["price_yen"]=0
        self.assertEqual(validate(a,N),"PRICE_MUST_BE_100")
    def test_missing_evidence(self):
        a=article();del a["generated_at"]
        self.assertEqual(validate(a,N),"INVALID_TIME_PROVENANCE")
if __name__=="__main__":unittest.main()
