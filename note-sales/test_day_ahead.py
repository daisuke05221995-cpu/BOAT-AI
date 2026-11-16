import copy,sys,unittest
from datetime import datetime,timedelta
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from day_ahead import make_article,score_program,JST,LearningProfile,tomorrow
from publish_guard import validate

NOW=datetime(2026,11,16,23,10,tzinfo=JST)
TARGET="2026-11-17"
def program():
    racers={}
    for lane in range(1,7):
        racers[str(lane)]={
            "national_win_rate":9.0 if lane==1 else 4.0,
            "local_win_rate":8.0 if lane==1 else 3.0,
            "motor_top_2_percent":48.0 if lane==1 else 35.0,
            "boat_top_2_percent":40.0,
            "average_start_timing":0.12 if lane==1 else 0.19
        }
    return {"programs":{"stadiums":{"01":{"races":{"01":{
        "date":TARGET,"closed_at":"2026-11-17 10:12:00",
        "racers":racers}}}}}}
def learn(): return LearningProfile({"starts":{},"wins":{},"windCourseStarts":{},"windCourseWins":{}})
def article(source=None):
    return make_article(source or program(),TARGET,NOW,learn(),
        {"month":"2026-05","hitRate":34.0,"purchaseHits":559,"purchaseRaces":1644},"approved-source")
class DayAheadTests(unittest.TestCase):
    def test_day_ahead_only(self):
        a=article()
        self.assertEqual(a["mode"],"DAY_AHEAD")
        self.assertEqual(a["status"],"READY")
        self.assertEqual(a["count"],1)
        self.assertEqual(a["data_policy"],{"weather":False,"exhibition":False,"same_day_odds":False})
        self.assertEqual(a["price_yen"],100)
        self.assertIsNone(validate(a,NOW))
        self.assertEqual(len([x for x in a["paid_paragraphs"] if "円" in x and "-" in x]),4)
        self.assertNotIn("1-2-3"," ".join(a["free_paragraphs"]))
    def test_weather_preview_odds_do_not_change_output(self):
        root=program()
        race=root["programs"]["stadiums"]["01"]["races"]["01"]
        race["preview"]={"wind_speed":15,"wave_height":9,"racers":{"1":{"exhibition_time":6.4}}}
        race["weather"]={"wind_speed":20}
        race["odds"]={"1-2-3":2}
        a=article(root)
        b=article()
        self.assertEqual(a["content_sha256"],b["content_sha256"])
    def test_reject_wrong_target_day(self):
        with self.assertRaises(ValueError):
            make_article(program(),"2026-11-16",NOW,learn(),{},"source")
    def test_reject_missing_roster_and_results(self):
        root=program();root["programs"]["stadiums"]["01"]["races"]["01"]["racers"].pop("6")
        self.assertEqual(article(root)["status"],"NO_ELIGIBLE_RACES")
        root=program();root["programs"]["stadiums"]["01"]["races"]["01"]["result"]={"finish":"1-2-3"}
        self.assertEqual(article(root)["status"],"NO_ELIGIBLE_RACES")
    def test_guard_prevents_today_date_on_night(self):
        a=article();a["date"]="2026-11-16"
        self.assertEqual(validate(a,NOW),"ARTICLE_NOT_TOMORROW")
if __name__=="__main__":unittest.main()
