#!/usr/bin/env python3
"""Print missing go-live settings without disclosing credentials or paid picks."""
import argparse
import json
import os
from datetime import datetime
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo
from pipeline import best_completed_month

JST=ZoneInfo("Asia/Tokyo")
def config_report(env, history, now):
    u=urlsplit(env.get("BOAT_AI_DAY_AHEAD_PROGRAM_URL",""))
    url_ok=u.scheme=="https" and bool(u.hostname) and bool(u.path)
    status=[
      ("historical_data",bool(history and history.get("month")),"HISTORICAL_REPORT_NOT_AVAILABLE"),
      ("day_ahead_program_url",url_ok,"DAY_AHEAD_PROGRAM_SOURCE_NOT_CONFIGURED"),
      ("commercial_data_approved",env.get("BOAT_AI_COMMERCIAL_SOURCE_APPROVED")=="true","COMMERCIAL_DATA_APPROVAL_REQUIRED"),
      ("day_ahead_source_id",bool(env.get("BOAT_AI_DAY_AHEAD_SOURCE_ID")),"DAY_AHEAD_SOURCE_ID_MISSING"),
      ("day_ahead_schedule",env.get("NOTE_DAY_AHEAD_ENABLED")=="true","DAY_AHEAD_SCHEDULE_DISABLED"),
      ("note_account_session",bool(env.get("NOTE_SESSION_STATE_B64")),"NOTE_ACCOUNT_NOT_CONNECTED"),
      ("paid_editor_verified",env.get("NOTE_BROWSER_UI_VERIFIED")=="true","PAID_EDITOR_NOT_VERIFIED"),
      ("auto_publish_switch",env.get("NOTE_AUTO_PUBLISH_ENABLED")=="true","AUTO_PUBLISH_DISABLED")
    ]
    missing=[reason for _,ok,reason in status if not ok]
    return {"date_jst":now.astimezone(JST).date().isoformat(),
        "historical_reference_month":history.get("month") if history else None,
        "historical_hit_rate":history.get("hitRate") if history else None,
        "note_price_yen":100,
        "mode":"DAY_AHEAD",
        "configuration":"READY_FOR_ACCOUNT_TEST_NOT_LIVE_VERIFIED" if not missing else "NOT_READY",
        "checks":{name:bool(ok) for name,ok,_ in status},
        "blockers":missing,
        "live_browser_account_tested":False,"live_forecast_verified":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--history",default="data/historical_backtest_2026.json")
    args=parser.parse_args()
    try: h=best_completed_month(args.history)
    except (OSError,ValueError,KeyError,TypeError): h={}
    print(json.dumps(config_report(os.environ,h,datetime.now(JST)),ensure_ascii=False,indent=2))
if __name__=="__main__": main()
