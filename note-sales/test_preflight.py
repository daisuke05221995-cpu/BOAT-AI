import unittest,sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from preflight import config_report,JST
NOW=datetime(2026,11,16,12,0,tzinfo=JST)
class TestPreflight(unittest.TestCase):
    def test_credentials_not_revealed(self):
        env={"BOAT_AI_FORECAST_URL":"https://example.com/v1/forecasts",
            "NOTE_SALES_ENABLED":"true","NOTE_AUTO_PUBLISH_ENABLED":"true",
            "NOTE_BROWSER_UI_VERIFIED":"true",
            "NOTE_SESSION_STATE_B64":"sensitive-session"}
        result=config_report(env,{"month":"2026-05","hitRate":34.0},NOW)
        self.assertNotIn("sensitive-session",str(result))
        self.assertEqual(result["configuration"],"READY_FOR_ACCOUNT_TEST_NOT_LIVE_VERIFIED")
        self.assertFalse(result["live_browser_account_tested"])
    def test_default_off(self):
        result=config_report({},{"month":"2026-05"},NOW)
        self.assertEqual(result["configuration"],"NOT_READY")
        self.assertIn("NOTE_ACCOUNT_NOT_CONNECTED",result["blockers"])
        self.assertIn("FORECAST_FEED_URL_NOT_CONFIGURED",result["blockers"])
if __name__=="__main__":unittest.main()
