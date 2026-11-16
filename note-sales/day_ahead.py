#!/usr/bin/env python3
"""Previous-night BOAT AI notes from tomorrow's verified six-boat program.

Reuses the historic lane/racer scorer, but intentionally excludes SAME-DAY
weather, preview, start exhibition, tilt, course, odds and race results.
No probabilistic win-rate or positive ROI is claimed for this new policy.
Commercial program source must be configured/approved separately.
"""
import argparse
import hashlib
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
from build_2026_backtest import LearningProfile, race_racers, raw_confidence, top_picks  # noqa: E402
from pipeline import best_completed_month  # noqa: E402

JST=ZoneInfo("Asia/Tokyo")
STAKE=(500,400,200,100)
MODEL="pre-day-racer-lane-v1"
MIN_SCORE=80

def tomorrow(now):
    return (now.astimezone(JST).date()+timedelta(days=1)).isoformat()

def score_program(program, target, now, learning):
    if target!=tomorrow(now):
        raise ValueError("TARGET_MUST_BE_NEXT_JST_DAY")
    stadiums=((program.get("programs") or {}).get("stadiums") or {})
    if not isinstance(stadiums,dict):
        raise ValueError("PROGRAM_SCHEMA_INVALID")
    ranked=[]
    for venue_key,venue in stadiums.items():
        if not isinstance(venue,dict): continue
        try: stadium=int(venue_key)
        except (ValueError,TypeError): continue
        if not 1<=stadium<=24: continue
        for n,raw in (venue.get("races") or {}).items():
            if not isinstance(raw,dict): continue
            try: number=int(n)
            except (ValueError,TypeError): continue
            if not 1<=number<=12 or raw.get("date")!=target: continue
            if raw.get("result") is not None: continue
            deadline_text=raw.get("closed_at")
            if not isinstance(deadline_text,str): continue
            try:
                deadline=datetime.fromisoformat(deadline_text.replace(" ","T"))
            except ValueError: continue
            if deadline.tzinfo is None: deadline=deadline.replace(tzinfo=JST)
            if deadline.astimezone(JST).date().isoformat()!=target or deadline<=now: continue
            # Only a completed six-boat PRE-DAY roster may be scored.
            # Do not fill missing entrants with post-race/preview values.
            racers=raw.get("racers")
            if not isinstance(racers,dict) or len(racers)!=6: continue
            valid=True
            for lane in range(1,7):
                x=racers.get(str(lane),racers.get(lane))
                if not isinstance(x,dict):
                    valid=False; break
                for field in ("national_win_rate","motor_top_2_percent","average_start_timing"):
                    value=x.get(field)
                    try: value=float(value)
                    except (TypeError,ValueError): valid=False; break
                    if not (0<=value<=100): valid=False; break
                if not valid: break
            if not valid: continue
            race={"date":target,"stadium_number":stadium,
                  "race_number":number,"racers":racers,
                  # EXPLICIT removal: no wind, exhibition or live course.
                  "preview":None}
            if len(race_racers(race))!=6: continue
            metric,first_lane,score_map=raw_confidence(race,learning)
            if metric<MIN_SCORE or len(score_map)!=6: continue
            picks=top_picks(score_map)
            if len(picks)!=4: continue
            ranked.append({"id":target.replace("-","")+f"{stadium:02d}{number:02d}",
                "stadium":stadium,"race":number,
                "deadline":deadline.isoformat(),"selection_index":metric,
                "first_lane":first_lane,"picks":picks})
    # One fixed prediction per race, never more than five per article.
    return sorted(ranked,key=lambda r:(-r["selection_index"],r["deadline"],r["id"]))[:5]

def make_article(program,target,now,learning,history,source):
    if target!=tomorrow(now): raise ValueError("TARGET_MUST_BE_NEXT_JST_DAY")
    picks=score_program(program,target,now,learning)
    if not picks: return {"status":"NO_ELIGIBLE_RACES","date":target,"count":0}
    earliest=min(datetime.fromisoformat(x["deadline"]) for x in picks)
    h=(history if isinstance(history,dict) else {})
    free=[
        f"BOAT AI｜{target} 前日予想",
        f"前日{now.astimezone(JST).strftime('%H:%M')}時点の翌日出走表と選手・モーター情報だけで選定しました。",
        "当日の風・波・展示・直前オッズは使用していません。",
        f"本日は{len(picks)}レースを厳選。100円で4点ずつの買い目と参考配分を掲載します。",
    ]
    if all(k in h for k in ("month","hitRate","purchaseHits","purchaseRaces")):
        free += [
            f"参考：旧方式の過去検証では{h['month']}に{h['purchaseRaces']:,}R中{h['purchaseHits']:,}R的中（{h['hitRate']:.1f}%）。",
            "この実績には当日展示等を使う旧方式が含まれており、本記事の前日予想方式の的中率ではありません。"
        ]
    free += [
        "出走変更・欠場・オッズ変動があり得ます。的中や利益を保証するものではありません。",
    ]
    paid=["【厳選買い目一覧】"]
    for index,entry in enumerate(picks,1):
        deadline=datetime.fromisoformat(entry["deadline"]).astimezone(JST).strftime("%H:%M")
        paid += [f"◆厳選{index}｜{entry['stadium']:02d}場 {entry['race']}R｜締切予定{deadline}",
                 f"選定指標 {entry['selection_index']}（的中確率ではありません）"]
        paid += [f"{combo}　{STAKE[i]:,}円" for i,combo in enumerate(entry["picks"])]
        paid.append(f"参考合計 {sum(STAKE):,}円")
    paid.append("前日時点の予想です。開催変更・欠場・発売状況を必ず確認してください。")
    digest=hashlib.sha256(json.dumps(
        {"target":target,"picks":picks,"model":MODEL},sort_keys=True,ensure_ascii=False
    ).encode("utf-8")).hexdigest()
    return {
        "status":"READY","mode":"DAY_AHEAD","date":target,
        "title":f"【{target}】BOAT AI 前日予想｜厳選{len(picks)}R｜4点勝負",
        "count":len(picks),"price_yen":100,"free_paragraphs":free,"paid_paragraphs":paid,
        "content_sha256":digest,"generated_at":now.isoformat(),
        "earliest_deadline_at":earliest.isoformat(),
        "data_policy":{"weather":False,"exhibition":False,"same_day_odds":False},
        "model_version":MODEL,
        "source_id":source,
        "historical_reference":h
    }

def fetch_program(url,target):
    if not isinstance(url,str) or not url.startswith("https://"):
        raise ValueError("PROGRAM_URL_REQUIRES_HTTPS")
    url=url.replace("{date}",target).replace("{compact_date}",target.replace("-",""))
    parsed=urllib.parse.urlsplit(url)
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("PROGRAM_URL_INVALID")
    query=urllib.parse.parse_qsl(parsed.query,keep_blank_values=True)
    if "{date}" not in os.environ.get("BOAT_AI_DAY_AHEAD_PROGRAM_URL","") and "date" not in dict(query):
        query.append(("date",target))
    actual=urllib.parse.urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urllib.parse.urlencode(query),""))
    req=urllib.request.Request(actual,headers={"Accept":"application/json","User-Agent":"BOAT-AI-day-ahead/1"})
    with urllib.request.urlopen(req,timeout=20) as response:
        data=response.read(3_000_001)
    if len(data)>3_000_000: raise ValueError("PROGRAM_TOO_LARGE")
    return json.loads(data.decode("utf-8"))

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--target")
    p.add_argument("--input",help="local JSON for isolated testing")
    p.add_argument("--program-url",default=os.environ.get("BOAT_AI_DAY_AHEAD_PROGRAM_URL",""))
    p.add_argument("--learning",default="data/historical_learning_pre2026.json")
    p.add_argument("--historical",default="data/historical_backtest_2026.json")
    p.add_argument("--output",default="note-sales/article.json")
    args=p.parse_args()
    now=datetime.now(JST)
    target=args.target or tomorrow(now)
    if target!=tomorrow(now): raise SystemExit("TARGET_MUST_BE_NEXT_JST_DAY")
    if not args.input:
        if os.environ.get("BOAT_AI_COMMERCIAL_SOURCE_APPROVED")!="true":
            raise SystemExit("COMMERCIAL_PROGRAM_SOURCE_NOT_APPROVED")
        program=fetch_program(args.program_url,target)
    else:
        program=json.loads(Path(args.input).read_text(encoding="utf-8"))
    learning_json=json.loads(Path(args.learning).read_text(encoding="utf-8"))
    if learning_json.get("trainedThrough","")>=target:
        raise SystemExit("HISTORY_NOT_PREVIOUS_TO_TARGET")
    learning=LearningProfile(learning_json)
    history=best_completed_month(args.historical)
    source=os.environ.get("BOAT_AI_DAY_AHEAD_SOURCE_ID","")
    if not source and not args.input:
        raise SystemExit("MISSING_APPROVED_SOURCE_ID")
    article=make_article(program,target,now,learning,history,source or "local-fixture")
    out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(article,ensure_ascii=False,indent=2),encoding="utf-8")
    out.chmod(0o600)
    # Never print confidential premium combinations into Actions logs.
    print(json.dumps({"date":target,"status":article["status"],"count":article["count"],
                      "mode":"DAY_AHEAD"},ensure_ascii=False))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as f:
            f.write("eligible="+("true" if article["status"]=="READY" else "false")+"\n")
if __name__=="__main__":
    main()
