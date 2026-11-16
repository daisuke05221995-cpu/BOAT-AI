#!/usr/bin/env python3
"""Independent final sales gate: do not sell expired or unverified content."""
import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")
URL = re.compile(r"^https://note\.com/[a-zA-Z0-9_-]+/n/n[0-9a-f]{12,64}(?:\?.*)?$")
def parse_time(s):
    if not isinstance(s,str):
        return None
    try:
        value=datetime.fromisoformat(s.replace("Z","+00:00"))
        return value if value.tzinfo else None
    except ValueError:
        return None

def validate(article, now=None):
    now=now or datetime.now(JST)
    if not isinstance(article,dict) or article.get("status")!="READY":
        return "ARTICLE_NOT_READY"
    if type(article.get("price_yen")) is not int or article["price_yen"]!=100:
        return "PRICE_MUST_BE_100"
    mode=article.get("mode","LIVE")
    if mode=="DAY_AHEAD":
        if article.get("date")!=(now.astimezone(JST).date()+timedelta(days=1)).isoformat():
            return "ARTICLE_NOT_TOMORROW"
        if article.get("data_policy")!={"weather":False,"exhibition":False,"same_day_odds":False}:
            return "DAY_AHEAD_USES_LIVE_FEATURES"
        if not article.get("source_id") or not article.get("model_version"):
            return "DAY_AHEAD_SOURCE_MISSING"
    elif mode=="LIVE":
        if article.get("date")!=now.astimezone(JST).date().isoformat():
            return "ARTICLE_NOT_TODAY"
    else:
        return "UNKNOWN_ARTICLE_MODE"
    if type(article.get("count")) is not int or not 1<=article["count"]<=5:
        return "INVALID_RACE_COUNT"
    free,paid=article.get("free_paragraphs"),article.get("paid_paragraphs")
    if not isinstance(free,list) or not all(isinstance(s,str) and s for s in free):
        return "INVALID_FREE_TEXT"
    if not isinstance(paid,list) or not all(isinstance(s,str) and s for s in paid):
        return "INVALID_PAID_TEXT"
    if len(paid)<2 or "厳選買い目" not in paid[0]:
        return "PAID_SECTION_MISSING"
    # No combination in the public paragraphs, even if the upstream schema changes.
    if re.search(r"(?<![0-9])[1-6]-[1-6]-[1-6](?![0-9])","\n".join(free)):
        return "PICKS_LEAK_IN_FREE_SECTION"
    earliest=parse_time(article.get("earliest_deadline_at"))
    created=parse_time(article.get("generated_at"))
    if earliest is None or created is None:
        return "INVALID_TIME_PROVENANCE"
    if earliest.astimezone(JST).date().isoformat()!=article["date"]:
        return "WRONG_RACE_DATE"
    if not timedelta(0)<=now-created<=timedelta(minutes=12):
        return "ARTICLE_STALE_OR_FUTURE"
    if earliest-now<=timedelta(minutes=30):
        return "NOT_ENOUGH_TIME_TO_SELL"
    if not isinstance(article.get("content_sha256"),str) or not re.fullmatch(r"[a-f0-9]{64}",article["content_sha256"]):
        return "INVALID_CONTENT_HASH"
    return None
