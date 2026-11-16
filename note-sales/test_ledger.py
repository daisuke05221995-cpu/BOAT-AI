import sys,unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from pipeline import generate,JST
from ledger import claim,success
D="2026-11-16";N=datetime(2026,11,16,10,0,tzinfo=JST)
def sample():
    row={"race_id":"202611160112","status":"READY","decision":"BUY",
         "deadline_at":(N+timedelta(minutes=90)).isoformat(),
         "forecast_completed_at":(N-timedelta(minutes=2)).isoformat(),
         "odds_observed_at":(N-timedelta(minutes=2)).isoformat(),
         "model_version":"v1","odds_source":"official",
         "combinations":["1-2-3"],"stakes":[100]}
    return generate({"date":D,"races":[row]},D,N,{})
class TestLedger(unittest.TestCase):
    def test_claim_and_success(self):
        a=sample();c=claim(a,N)
        self.assertNotIn("1-2-3",str(c))
        result={"date":D,"status":"POSTED_VERIFIED","content_sha256":a["content_sha256"],
                "url":"https://note.com/example/n/n1234567890ab"}
        s=success(c,result)
        self.assertEqual(s["status"],"POSTED_VERIFIED")
        self.assertNotIn("1-2-3",str(s))
    def test_no_double_silent_success(self):
        a=sample();c=claim(a,N)
        with self.assertRaises(ValueError): success(c,{"status":"POSTED_VERIFIED","date":D,"content_sha256":"0"*64,"url":"https://note.com/x/n/n1234567890ab"})
        with self.assertRaises(ValueError): success({"status":"POSTED_VERIFIED"}, {})
    def test_claim_stale_fails(self):
        with self.assertRaises(ValueError): claim(sample(),N+timedelta(minutes=13))
if __name__=="__main__":unittest.main()
