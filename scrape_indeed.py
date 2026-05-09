#!/usr/bin/env python3
"""
scrape_indeed.py — fetch Indeed Los Angeles job listings via Playwright with
a realistic browser fingerprint, merge into scan-data.json under platform
"Indeed".

Run with no args: scrapes, prints, and writes to scan-data.json.
Run with --dry-run: scrapes, prints; does not modify scan-data.json.
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse


PLATFORM = "Indeed"
BASE_URL_TEMPLATE = (
    "https://www.indeed.com/q-{keywords}-l-Los-Angeles,-CA-jobs.html"
)
SEARCHES = [
    "art director",
    "creative director",
    "brand designer",
]
DATA_PATH = Path(__file__).resolve().parent / "scan-data.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CARD_SELECTORS = [
    "[data-testid='job-card']",
    "[class*='job_seen_beacon']",
    ".cardOutline",
    "[class*='jobsearch-SerpJobCard']",
    ".tapItem",
]

TITLE_SELECTORS = [
    "h2 a",
    "[class*='jobTitle'] a",
    "[class*='jobTitle']",
    "a",
]

COMPANY_SELECTORS = [
    "[data-testid='company-name']",
    "[class*='companyName']",
]

LOCATION_SELECTORS = [
    "[data-testid='text-location']",
    "[class*='companyLocation']",
]

TIME_SELECTORS = [
    "[data-testid='myJobsStateDate']",
    "[class*='date']",
]

CAPTCHA_MARKERS = [
    "verifying you are human",
    "verify you are a human",
    "are you a robot",
    "px-captcha",
    "cf-challenge",
    "hcaptcha",
    "/blocked",
]


def slugify_keywords(keywords):
    s = keywords.strip().lower()
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^a-z0-9-]", "", s)
    return s


def build_url(keywords):
    return BASE_URL_TEMPLATE.format(keywords=slugify_keywords(keywords))


def canonical_link(link):
    if not link:
        return ""
    try:
        p = urlparse(link)
    except Exception:
        return link
    netloc = p.netloc.lower()
    path = p.path or "/"
    return urlunparse((p.scheme.lower() or "https", netloc, path, "", "", ""))


def looks_like_captcha(html_lower, url_lower):
    for marker in CAPTCHA_MARKERS:
        if marker in html_lower or marker in url_lower:
            return True
    return False


def first_text(card, selectors):
    for sel in selectors:
        try:
            el = card.query_selector(sel)
        except Exception:
            el = None
        if el is None:
            continue
        try:
            text = el.inner_text().strip()
        except Exception:
            text = ""
        if text:
            return text
    return ""


def first_link(card, selectors, page_url):
    for sel in selectors:
        try:
            el = card.query_selector(sel)
        except Exception:
            el = None
        if el is None:
            continue
        href = ""
        try:
            href = el.get_attribute("href") or ""
        except Exception:
            href = ""
        if href:
            return urljoin(page_url, href)
    return ""


def find_cards(page):
    for sel in CARD_SELECTORS:
        try:
            cards = page.query_selector_all(sel)
        except Exception:
            cards = []
        if cards:
            return sel, cards
    return "", []


def extract_card(card, page_url):
    title = first_text(card, TITLE_SELECTORS)
    link = first_link(card, TITLE_SELECTORS, page_url)
    company = first_text(card, COMPANY_SELECTORS)
    location = first_text(card, LOCATION_SELECTORS)
    time_ago = first_text(card, TIME_SELECTORS)
    return {
        "title": title,
        "link": link,
        "company": company,
        "location": location,
        "time_ago": time_ago,
    }


def to_scan_item(raw):
    title = raw["title"]
    company = raw["company"]
    if title and company:
        display = f"{title} - {company}"
    else:
        display = title or company
    item = {
        "platform": PLATFORM,
        "title": display,
        "link": raw["link"],
        "alert": False,
    }
    if raw.get("location"):
        item["location"] = raw["location"]
    if raw.get("time_ago"):
        item["time_ago"] = raw["time_ago"]
    if company:
        item["source"] = company
    return item


def fetch_query(context, keywords):
    """Fetch one Indeed search result page. Returns (items, status, note)."""
    url = build_url(keywords)
    page = context.new_page()
    items = []
    note = ""
    status = "ok"
    try:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            return [], "error", f"goto failed: {type(e).__name__}: {e}"

        page.wait_for_timeout(3000)

        try:
            html = page.content()
        except Exception:
            html = ""
        current_url = ""
        try:
            current_url = page.url or ""
        except Exception:
            current_url = ""

        if looks_like_captcha(html.lower(), current_url.lower()):
            return [], "captcha", "captcha or human-verification page"

        sel_used, cards = find_cards(page)
        if not cards:
            return [], "empty", "no job cards found"

        seen_local = set()
        for card in cards:
            try:
                raw = extract_card(card, current_url or url)
            except Exception:
                continue
            if not raw["title"] or not raw["link"]:
                continue
            key = canonical_link(raw["link"])
            if key in seen_local:
                continue
            seen_local.add(key)
            items.append(raw)

        note = f"selector={sel_used} cards={len(cards)}"
    finally:
        try:
            page.close()
        except Exception:
            pass
    return items, status, note


def scrape():
    """Fetch and parse Indeed listings for each default search query.

    Returns a list of scan-data item dicts. Raises if every query fails or
    every query returns zero cards, so the orchestrator can record the error.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        raise RuntimeError(
            f"playwright not available: {type(e).__name__}: {e}"
        )

    aggregated = []
    seen = set()
    statuses = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            try:
                for i, query in enumerate(SEARCHES):
                    if i > 0:
                        time.sleep(2)
                    try:
                        items, status, note = fetch_query(context, query)
                    except Exception as e:
                        statuses.append((query, "error", f"{type(e).__name__}: {e}"))
                        continue
                    statuses.append((query, status, note))
                    for raw in items:
                        key = canonical_link(raw["link"])
                        if key in seen:
                            continue
                        seen.add(key)
                        aggregated.append(raw)
            finally:
                try:
                    context.close()
                except Exception:
                    pass
        finally:
            try:
                browser.close()
            except Exception:
                pass

    ok_count = sum(1 for _, s, _ in statuses if s == "ok")
    if ok_count == 0:
        details = "; ".join(f"{q}: {s} ({n})" for q, s, n in statuses)
        raise RuntimeError(f"all Indeed queries failed: {details}")

    return [to_scan_item(r) for r in aggregated]


def merge_into_scan_data(items, error_msg=None):
    if DATA_PATH.exists():
        data = json.loads(DATA_PATH.read_text())
    else:
        data = {
            "generated": datetime.now(timezone.utc).isoformat(),
            "location": "Hermosa Beach, CA",
            "items": [],
            "errors": {},
            "platforms": {},
        }

    kept = [it for it in data.get("items", []) if it.get("platform") != PLATFORM]
    kept.extend(items)
    data["items"] = kept

    errors = data.setdefault("errors", {})
    if error_msg:
        errors[PLATFORM] = error_msg
    else:
        errors.pop(PLATFORM, None)

    platforms = data.setdefault("platforms", {})
    platforms[PLATFORM] = {
        "status": "error" if error_msg else "ok",
        "count": len(items),
    }

    DATA_PATH.write_text(json.dumps(data, indent=2) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run", action="store_true",
        help="print results without modifying scan-data.json",
    )
    args = ap.parse_args()

    print(f"Indeed search queries: {SEARCHES}")
    for q in SEARCHES:
        print(f"  {q!r} -> {build_url(q)}")

    try:
        items = scrape()
    except Exception as e:
        print(f"SCRAPE FAILED: {e}", file=sys.stderr)
        if not args.dry_run:
            merge_into_scan_data([], error_msg=str(e))
        sys.exit(1)

    print(f"\n{len(items)} item(s) after de-duplication.\n")
    for it in items:
        print("-" * 70)
        print(f"  Title:    {it['title']}")
        print(f"  Link:     {it['link']}")
        if it.get("location"):
            print(f"  Where:    {it['location']}")
        if it.get("time_ago"):
            print(f"  Posted:   {it['time_ago']}")

    if args.dry_run:
        print("\n--dry-run: scan-data.json not modified.")
        print("\nWould merge these item dicts:")
        print(json.dumps(items, indent=2))
    else:
        merge_into_scan_data(items)
        print(f"\nWrote {len(items)} Indeed item(s) to {DATA_PATH.name}")


if __name__ == "__main__":
    main()
