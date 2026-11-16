#!/usr/bin/env python3
"""One-way fail-closed note publication ledger. Never store paid selections."""
import argparse
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from publish_guard import validate
JST=ZoneInfo("Asia/Tokyo")

def claim(article,now):
    err=validate(article,now)
    if err: raise ValueError("SALES_GUARD_"+err)
    return {"date":article["date"],"content_sha256":article["content_sha256"],
            "status":"PUBLISHING_REQUIRES_MANUAL_RECOVERY_IF_INTERRUPTED",
            "claimed_at":now.isoformat()}

def success(original,result):
    if original.get("status")!="PUBLISHING_REQUIRES_MANUAL_RECOVERY_IF_INTERRUPTED":
        raise ValueError("MISSING_PUBLISH_CLAIM")
    if result.get("status")!="POSTED_VERIFIED":
        raise ValueError("UNVERIFIED_PUBLICATION")
    if original["date"]!=result.get("date") or original["content_sha256"]!=result.get("content_sha256"):
        raise ValueError("PUBLICATION_LEDGER_MISMATCH")
    if not str(result.get("url","")).startswith("https://note.com/"):
        raise ValueError("INVALID_NOTE_PUBLICATION_URL")
    return {"date":original["date"],"content_sha256":original["content_sha256"],
            "status":"POSTED_VERIFIED","url":result["url"],
            "checked_at":result.get("checked_at")}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["claim","complete"])
    p.add_argument("article_or_claim")
    p.add_argument("output")
    p.add_argument("--result")
    a=p.parse_args()
    src=json.loads(Path(a.article_or_claim).read_text(encoding="utf-8"))
    if a.action=="claim":
        payload=claim(src,datetime.now(JST))
    else:
        if not a.result: raise SystemExit("--result REQUIRED")
        payload=success(src,json.loads(Path(a.result).read_text(encoding="utf-8")))
    dst=Path(a.output)
    dst.parent.mkdir(parents=True,exist_ok=True)
    if a.action=="claim" and dst.exists(): raise SystemExit("LEDGER_EXISTS_REFUSE_DUPLICATE")
    dst.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"date":payload["date"],"status":payload["status"]},ensure_ascii=False))

if __name__=="__main__": main()
