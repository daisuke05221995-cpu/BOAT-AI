#!/usr/bin/env python3
"""Generate note sales articles from current, verified BOAT AI BUYs only."""
import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
COMBO = re.compile(r"^[1-6]-[1-6]-[1-6]$")

def moment(s):
    try:
        d = datetime.fromisoformat(s.replace("Z","+00:00"))
        return d if d.tzinfo else None
    except (TypeError, ValueError, AttributeError):
        return None

def best_completed_month(report):
    data=json.loads(Path(report).read_text(encoding="utf-8"))
    through=data["dataThrough"][:7]
    months=[m for m in data["months"] if f'{m["year"]:04d}-{m["month"]:02d}' < through and m["purchaseRaces"] >= 100]
    if not months: raise ValueError("NO_HISTORICAL_MONTH")
    # Select by race hit rate, NOT stake-weighted ROI. Current live policy may differ.
    # Use raw counts (rather than 1-decimal published hitRate) for ranking.
    m=max(months,key=lambda x:(x["purchaseHits"]/x["purchaseRaces"],x["purchaseRaces"]))
    return {"month":f'{m["year"]:04d}-{m["month"]:02d}',
            "hitRate":round(100*m["purchaseHits"]/m["purchaseRaces"],1),
            "purchaseHits":m["purchaseHits"],"purchaseRaces":m["purchaseRaces"],
            "roi":m["roi"],"status":"historical_backtest_only_not_live"}

def load_feed(url, date):
    if not url.startswith("https://"): raise ValueError("FORECAST_URL_REQUIRES_HTTPS")
    u=urllib.parse.urlsplit(url)
    if u.username or u.password or not u.hostname or u.fragment:
        raise ValueError("INVALID_FORECAST_URL")
    q=urllib.parse.parse_qsl(u.query)
    q.append(("date",date))
    final=urllib.parse.urlunsplit((u.scheme,u.netloc,u.path,urllib.parse.urlencode(q),""))
    req=urllib.request.Request(final,headers={"Accept":"application/json","User-Agent":"BOAT-AI-Note-Sales/1"})
    with urllib.request.urlopen(req,timeout=15) as response: raw=response.read(2000001)
    if len(raw)>2000000: raise ValueError("FEED_TOO_LARGE")
    return json.loads(raw.decode("utf-8"))

def qualify(r,date,now):
    if not isinstance(r,dict) or r.get("status")!="READY" or r.get("decision")!="BUY" or r.get("quality_flags") or r.get("result"):
        return None
    rid=str(r.get("race_id",""))
    if not re.fullmatch(r"[0-9]{12}",rid) or not rid.startswith(date.replace("-","")) or r.get("race_date",date)!=date:
        return None
    deadline=moment(r.get("deadline_at"))
    forecast=moment(r.get("forecast_completed_at"))
    odds=moment(r.get("odds_observed_at")) or moment(r.get("odds_fetched_at"))
    if not all((deadline,forecast,odds,r.get("model_version"),r.get("odds_source"))): return None
    if not (now+timedelta(minutes=3)<deadline<=now+timedelta(hours=16)): return None
    if not (timedelta(0)<=now-forecast<=timedelta(minutes=20)): return None
    if not (timedelta(0)<=now-odds<=timedelta(minutes=20)): return None
    combos,stakes=r.get("combinations"),r.get("stakes")
    if not isinstance(combos,list) or not isinstance(stakes,list) or len(combos)!=len(stakes) or not 1<=len(combos)<=8: return None
    picks=[]
    for c,s in zip(combos,stakes):
        if not isinstance(c,str) or not COMBO.fullmatch(c) or len(set(c.split("-")))!=3 or type(s)!=int or s<100 or s%100: return None
        picks.append({"combination":c,"yen":s})
    if len({p["combination"] for p in picks})!=len(picks) or not 100<=sum(p["yen"] for p in picks)<=5000: return None
    conf=r.get("confidence")
    conf=float(conf) if type(conf) in (int,float) and 0<=conf<=100 else None
    return {"id":rid,"stadium":int(rid[8:10]),"race":int(rid[10:12]),
            "deadline":deadline.isoformat(),"odds_at":odds.isoformat(),
            "model":r["model_version"],"odds_source":r["odds_source"],
            "confidence":conf,"picks":picks,"amount":sum(p["yen"] for p in picks)}

def generate(feed,date,now,history):
    if feed.get("date")!=date or not isinstance(feed.get("races"),list): raise ValueError("INVALID_FEED")
    unique={}
    for row in feed["races"]:
        q=qualify(row,date,now)
        if q: unique[q["id"]]=q
    picks=sorted(unique.values(),key=lambda x:(-(x["confidence"] if x["confidence"] is not None else -1),x["deadline"],x["id"]))[:5]
    if not picks: return {"status":"NO_ELIGIBLE_RACES","date":date,"count":0}
    first=min(moment(x["deadline"]) for x in picks).astimezone(JST).strftime("%H:%M")
    has_historical_hit_rate = (
        isinstance(history,dict) and
        type(history.get("purchaseRaces")) is int and history["purchaseRaces"] > 0 and
        type(history.get("purchaseHits")) is int and 0 <= history["purchaseHits"] <= history["purchaseRaces"] and
        isinstance(history.get("month"),str) and
        type(history.get("hitRate")) in (int,float) and 0 <= history["hitRate"] <= 100
    )
    if has_historical_hit_rate:
        title=f'【{date}】BOAT AI｜過去検証的中率{history["hitRate"]:.1f}%｜厳選{len(picks)}R'
    else:
        title=f'【{date}】BOAT AI｜本日の厳選{len(picks)}レース'
    free=[
        f'BOAT AI｜{date} 厳選予想',
        '全国から締切前のAI購入推奨だけを抽出しました。',
    ]
    if has_historical_hit_rate:
        free += [
            f'【過去検証の的中率：{history["hitRate"]:.1f}%】',
            f'過去検証 {history["month"]}：購入推奨{history["purchaseRaces"]:,}レース中{history["purchaseHits"]:,}レース的中。',
            '上記は旧条件の過去シミュレーションによる参考値です。現在販売する買い目の的中率・利益を示すものではありません。',
            '参考：賭け金の配分は収支に影響しますが、的中レース数そのものは変えません。',
        ]
    free += [
        f'厳選{len(picks)}レース、販売価格100円。最も早い締切は{first}（JST）です。',
        '有料部分に買い目・配分金額・取得時刻を掲載します。',
        'オッズや開催状況は変化します。的中・利益を保証するものではありません。'
    ]
    paid=['【厳選買い目一覧】']
    for i,r in enumerate(picks,1):
        paid += [f'◆厳選{i}　{r["stadium"]:02d}場 {r["race"]}R　締切 {moment(r["deadline"]).astimezone(JST).strftime("%H:%M")}',
                 f'モデル：{r["model"]}／オッズ源：{r["odds_source"]}',
                 f'情報取得：{moment(r["odds_at"]).astimezone(JST).strftime("%H:%M:%S")} JST']
        if r["confidence"] is not None: paid.append(f'元データ信頼度：{r["confidence"]:g}')
        paid += [f'{p["combination"]}　{p["yen"]:,}円' for p in r["picks"]]
        paid.append(f'参考合計：{r["amount"]:,}円')
    paid.append('締切と最新オッズはご自身でご確認ください。')
    digest=hashlib.sha256(json.dumps(picks,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {"status":"READY","date":date,"title":title,"price_yen":100,
            "free_paragraphs":free,"paid_paragraphs":paid,"content_sha256":digest,
            "count":len(picks),"historical_reference":history,"earliest_deadline":first}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--date",default=datetime.now(JST).date().isoformat())
    p.add_argument("--input")
    p.add_argument("--feed-url",default=os.getenv("BOAT_AI_FORECAST_URL",""))
    p.add_argument("--output",default="note-sales/article.json")
    p.add_argument("--history",default="data/historical_backtest_2026.json")
    a=p.parse_args()
    now=datetime.now(JST)
    if not a.input and a.date!=now.date().isoformat(): raise ValueError("LIVE_DATE_MISMATCH")
    feed=json.loads(Path(a.input).read_text(encoding="utf-8")) if a.input else load_feed(a.feed_url,a.date)
    history=best_completed_month(a.history)
    out=generate(feed,a.date,now,history)
    path=Path(a.output);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    path.chmod(0o600)
    print(json.dumps({"status":out["status"],"count":out["count"],"date":a.date,
                      "best_historical_hit_month":history["month"],
                      "historical_hit_rate":history["hitRate"]},ensure_ascii=False))
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"],"a") as f:
            f.write("eligible="+("true" if out["status"]=="READY" else "false")+"\n")

if __name__=="__main__":main()
