#!/usr/bin/env python3
"""
scrape_aquent.py — fetch aquent.com/find-work for Los Angeles Creative & Design
listings via Playwright (chromium). No profile filter; freelance creative work.

Run with no args: scrapes and prints. (Orchestrator calls scrape() directly.)
Run with --dry-run: scrapes and prints; never writes scan-data.json.
"""

import argparse
import json
import sys
from urllib.parse import urljoin

URL = (
    "https://aquent.com/find-work"
    "?size=n_12_n"
    "&filters%5B0%5D%5Bfield%5D=offsite_preference.keyword"
    "&filters%5B0%5D%5Bvalues%5D%5B0%5D=Remote"
    "&filters%5B0%5D%5Btype%5D=any"
    "&sort%5B0%5D%5Bfield%5D=posted_date"
    "&sort%5B0%5D%5Bdirection%5D=desc"
)
PLATFORM = "Aquent"
BASE = "https://aquent.com"

CARD_SELECTORS = [
    "a.job-card",
    "a[href*='/find-work/']",
    "[class*='JobCard']",
    "article",
]

TITLE_SELECTOR = "h2, h3, h4, [class*='title']"

INCLUDE_KEYWORDS = [
    "senior designer",
    "graphic designer",
    "art director",
    "associate creative director",
    "creative director",
    "brand designer",
]

EXCLUDE_KEYWORDS = [
    "price analyst",
    "privacy analyst",
    "data analyst",
    "digital marketing",
    "visual analyst",
    "search performance manager",
    "accounting support",
    "product manager",
    "technical motion designer",
    "adobe experience manager",
    "developer",
    "pharmaceutical",
]


def _filter_decision(title):
    """Return (keep: bool, reason: str) for a candidate title.

    Rules: exclude wins over include; titles with no include match are dropped.
    """
    t = (title or "").lower()
    for kw in EXCLUDE_KEYWORDS:
        if kw in t:
            return False, f"excluded by '{kw}'"
    for kw in INCLUDE_KEYWORDS:
        if kw in t:
            return True, f"matched '{kw}'"
    return False, "no include keyword matched"


def _clean(text):
    return " ".join((text or "").split()).strip()


def _extract_card(card):
    title = ""
    title_el = card.query_selector(TITLE_SELECTOR)
    if title_el:
        title = _clean(title_el.inner_text())
    if not title:
        full = _clean(card.inner_text())
        title = full.splitlines()[0] if full else ""
        title = title.split("\n", 1)[0]
    title = title[:140].strip()
    if len(title) < 4:
        return None

    link = ""
    href = card.get_attribute("href") or ""
    if not href:
        anchor = card.query_selector("a[href]")
        if anchor:
            href = anchor.get_attribute("href") or ""
    if href:
        link = urljoin(BASE, href)
    if not link:
        return None

    body = _clean(card.inner_text())
    item = {
        "platform": PLATFORM,
        "title": title,
        "link": link,
        "alert": False,
    }

    if "Los Angeles" in body:
        item["location"] = "Los Angeles, CA"

    time_el = card.query_selector("time")
    if time_el:
        time_text = _clean(time_el.inner_text())
        if time_text:
            item["date"] = time_text
    else:
        for token in ["minute", "hour", "day", "week", "month", "year"]:
            idx = body.lower().find(token + " ago")
            if idx == -1:
                continue
            start = max(0, idx - 12)
            snippet = body[start:idx + len(token) + 4]
            words = snippet.split()
            if len(words) >= 2:
                item["time_ago"] = " ".join(words[-3:]) if len(words) >= 3 else " ".join(words[-2:])
            break

    return item


def _collect(page):
    for selector in CARD_SELECTORS:
        cards = page.query_selector_all(selector)
        if cards:
            return cards, selector
    return [], None


def _scrape_raw():
    """Fetch and parse all Aquent listings before filtering.

    Returns the unfiltered list of scan-data item dicts (deduped by link).
    Raises on Playwright/import or navigation failures.
    """
    from playwright.sync_api import sync_playwright

    items = []
    seen_links = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(4000)
            cards, _ = _collect(page)
            for card in cards:
                try:
                    item = _extract_card(card)
                except Exception:
                    continue
                if not item:
                    continue
                if item["link"] in seen_links:
                    continue
                seen_links.add(item["link"])
                items.append(item)
        finally:
            context.close()
            browser.close()

    return items


def scrape():
    """Fetch, parse, and filter Aquent Remote Creative & Design listings.

    Applies the title include/exclude filter. Returns kept items only.
    """
    raw = _scrape_raw()
    return [it for it in raw if _filter_decision(it["title"])[0]][:10]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print results without modifying scan-data.json")
    args = ap.parse_args()

    print(f"Fetching {URL}")
    try:
        raw = _scrape_raw()
    except Exception as e:
        print(f"FETCH FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(raw)} raw listing(s) before filter\n")
    kept = []
    for it in raw:
        keep, reason = _filter_decision(it["title"])
        marker = "KEEP" if keep else "skip"
        print(f"  [{marker}] {it['title']}  ({reason})")
        if keep:
            kept.append(it)

    print(f"\n{len(kept)} kept after filter:\n")
    for it in kept:
        print("-" * 70)
        print(f"  Title:    {it['title']}")
        print(f"  Link:     {it['link']}")
        if "location" in it:
            print(f"  Where:    {it['location']}")
        if "date" in it:
            print(f"  Date:     {it['date']}")
        if "time_ago" in it:
            print(f"  Posted:   {it['time_ago']}")

    if args.dry_run:
        print("\n--dry-run: scan-data.json not modified.")
        print("\nWould return these item dicts:")
        print(json.dumps(kept, indent=2))
    else:
        print("\nscrape_aquent.py is a plugin; orchestrator writes scan-data.json.")
        print("Items returned:")
        print(json.dumps(kept, indent=2))


if __name__ == "__main__":
    main()
