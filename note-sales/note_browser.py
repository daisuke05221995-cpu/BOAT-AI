#!/usr/bin/env python3
"""note's public web-editor workflow, experimental and fail-closed.

Uses the account owner's Playwright storage state. Never uses private note API
endpoints and never bypasses login challenges. Requires explicit opt-in and
live-editor paywall verification before clicking the final publish button.
"""
import asyncio
import base64
import json
import os
import re
import sys
from pathlib import Path

def check(ok,why):
    if not ok: raise RuntimeError(why)

async def publish(path):
    from playwright.async_api import async_playwright
    article=json.loads(Path(path).read_text(encoding="utf-8"))
    if article["status"]!="READY":
        print("NO_ELIGIBLE_RACES")
        return
    check(article["price_yen"]==100,"PRICE_NOT_100")
    check(os.getenv("NOTE_AUTO_PUBLISH_ENABLED")=="true","PUBLISH_DISABLED")
    check(os.getenv("NOTE_BROWSER_UI_VERIFIED")=="true","UI_NOT_VERIFIED_NO_PUBLISH")
    auth=os.getenv("NOTE_SESSION_STATE_B64","")
    check(bool(auth),"AUTH_SESSION_MISSING")
    try: state=json.loads(base64.b64decode(auth,validate=True))
    except Exception as e: raise RuntimeError("INVALID_AUTH_STATE") from e
    check(isinstance(state,dict) and isinstance(state.get("cookies"),list),"INVALID_AUTH_STATE")
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        context=await browser.new_context(storage_state=state,locale="ja-JP",timezone_id="Asia/Tokyo")
        page=await context.new_page()
        page.set_default_timeout(12000)
        try:
            await page.goto("https://note.com/new",wait_until="domcontentloaded")
            check("/login" not in page.url.lower(),"NOTE_LOGIN_REQUIRED")
            title=page.locator("textarea[placeholder*='タイトル'],input[placeholder*='タイトル'],[contenteditable='true'][data-placeholder*='タイトル']").first
            await title.wait_for(state="visible")
            await title.fill(article["title"])
            editor=page.locator(".ProseMirror[contenteditable='true'],[role='textbox'][contenteditable='true']").first
            await editor.wait_for(state="visible")
            await editor.click()
            for paragraph in article["free_paragraphs"]+article["paid_paragraphs"]:
                await page.keyboard.insert_text(paragraph)
                await page.keyboard.press("Enter")
            await page.get_by_role("button",name=re.compile("公開に進む")).click()
            await page.get_by_text("有料",exact=True).first.click()
            price=page.locator("input[inputmode='numeric'],input[type='number'],input[placeholder*='価格']").first
            await price.wait_for(state="visible")
            await price.fill("100")
            check(await price.input_value()=="100","PRICE_NOT_CONFIRMED")
            await page.get_by_role("button",name=re.compile("有料エリア設定")).click()
            # The public UI help describes a boundary selection per paragraph.
            free_count=len(article["free_paragraphs"])
            options=page.get_by_text("ラインをこの場所に変更",exact=True)
            check(await options.count()>=free_count,"PAYWALL_LINES_UNAVAILABLE")
            await options.nth(free_count-1).click()
            marker=page.get_by_text(re.compile("ここから先は有料部分です|このラインより上を有料にする")).first
            check(await marker.is_visible(),"PAYWALL_NOT_CONFIRMED")
            # Explicit DOM check must show the marker strictly between the
            # last public paragraph and first premium paragraph. A changed UI
            # must cause failure, not a free leak of paid picks.
            public=page.get_by_text(article["free_paragraphs"][-1],exact=True).first
            premium=page.get_by_text(article["paid_paragraphs"][0],exact=True).first
            a,b,c=await public.bounding_box(),await marker.bounding_box(),await premium.bounding_box()
            check(bool(a and b and c) and a["y"]<b["y"]<c["y"],"PAYWALL_POSITION_UNVERIFIED")
            await page.get_by_role("button",name=re.compile("投稿する|公開する")).click()
            await page.wait_for_url(re.compile(r"^https://note\.com/[^/]+/n/n[0-9a-f]+"),timeout=20000)
            result={"date":article["date"],"url":page.url,"content_sha256":article["content_sha256"]}
            path=os.getenv("NOTE_PUBLISH_RESULT_FILE")
            check(bool(path),"RESULT_LEDGER_PATH_MISSING")
            Path(path).write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8")
            print(json.dumps({"status":"POSTED","date":article["date"],"url":page.url},ensure_ascii=False))
        finally:
            await context.close()
            await browser.close()

if __name__=="__main__":
    asyncio.run(publish(sys.argv[1] if len(sys.argv)>1 else "note-sales/article.json"))
