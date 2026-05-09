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
    "?type=Creative+%26+Design&location=Los+Angeles%2C+CA"
)
PLATFORM = "Aquent"
BASE = "https://aquent.com"

CARD_SELECTORS = [
    "[class*='job-card']",
    "[class*='JobCard']",
    "[class*='listing']",
    "[class*='result']",
    "article",
]

TITLE_SELECTOR = "h2, h3, h4, [class*='title']"


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


def scrape():
    """Fetch and parse Aquent LA Creative & Design listings.

    Returns a list of scan-data item dicts. Raises on Playwright/import or
    navigation failures so the orchestrator can record the error.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print results without modifying scan-data.json")
    args = ap.parse_args()

    print(f"Fetching {URL}")
    try:
        items = scrape()
    except Exception as e:
        print(f"FETCH FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(items)} listing(s)\n")
    for it in items:
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
        print(json.dumps(items, indent=2))
    else:
        print("\nscrape_aquent.py is a plugin; orchestrator writes scan-data.json.")
        print("Items returned:")
        print(json.dumps(items, indent=2))


if __name__ == "__main__":
    main()
