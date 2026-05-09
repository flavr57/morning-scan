#!/usr/bin/env python3
"""
scrape_linkedin.py - fetch LinkedIn public guest job postings for Jason's
default LA-based search queries and surface them under platform "LinkedIn".

Run with --dry-run: scrapes, prints results; does not modify scan-data.json.
"""

import argparse
import json
import sys
import time
from urllib.parse import urlencode, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
PLATFORM = "LinkedIn"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

SEARCHES = [
    {"keywords": "creative director", "location": "Los Angeles, CA"},
    {"keywords": "art director freelance", "location": "Los Angeles, CA"},
    {"keywords": "brand designer contract", "location": "Los Angeles, CA"},
]

REQUEST_TIMEOUT = 20
SLEEP_BETWEEN_QUERIES = 2.0


def fetch(keywords, location):
    params = {
        "keywords": keywords,
        "location": location,
        "f_TPR": "r86400",
        "start": 0,
    }
    full_url = f"{URL}?{urlencode(params)}"
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(full_url, headers=headers, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    return r.text


def _canonical_link(href):
    if not href:
        return ""
    try:
        parts = urlsplit(href)
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        return href


def parse_cards(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.find_all("li"):
        title_el = li.select_one("h3.base-search-card__title")
        company_el = li.select_one("h4.base-search-card__subtitle")
        link_el = li.select_one("a.base-card__full-link")
        if not (title_el and company_el and link_el):
            continue
        title = title_el.get_text(strip=True)
        company = company_el.get_text(strip=True)
        href = link_el.get("href", "").strip()
        if not (title and company and href):
            continue

        location_el = li.select_one("span.job-search-card__location")
        time_el = li.select_one("time")

        out.append({
            "title": title,
            "company": company,
            "link": _canonical_link(href),
            "location": location_el.get_text(strip=True) if location_el else "",
            "time_ago": time_el.get_text(strip=True) if time_el else "",
        })
    return out


def to_scan_item(card):
    item = {
        "platform": PLATFORM,
        "title": f"{card['title']} - {card['company']}",
        "link": card["link"],
        "alert": False,
    }
    if card.get("location"):
        item["location"] = card["location"]
    if card.get("time_ago"):
        item["date"] = card["time_ago"]
    if card.get("company"):
        item["source"] = card["company"]
    return item


def scrape():
    """Run all configured LinkedIn searches, dedupe, return scan-data items.

    Each search is wrapped in try/except. If every search fails, the last
    error is raised so the orchestrator can record it.
    """
    seen_titles = set()
    seen_links = set()
    items = []
    errors = []

    for i, search in enumerate(SEARCHES):
        if i > 0:
            time.sleep(SLEEP_BETWEEN_QUERIES)
        try:
            html = fetch(search["keywords"], search["location"])
            cards = parse_cards(html)
        except Exception as e:
            print(
                f"LinkedIn search {search['keywords']!r} failed: "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )
            errors.append(e)
            continue

        for card in cards:
            title_key = f"{card['title'].lower()}|{card['company'].lower()}"
            link_key = card["link"]
            if title_key in seen_titles or link_key in seen_links:
                continue
            seen_titles.add(title_key)
            seen_links.add(link_key)
            items.append(to_scan_item(card))

    if not items and len(errors) == len(SEARCHES) and errors:
        raise errors[-1]

    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print results without modifying scan-data.json")
    args = ap.parse_args()

    print(f"Running {len(SEARCHES)} LinkedIn search(es)...")
    try:
        items = scrape()
    except Exception as e:
        print(f"SCRAPE FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{len(items)} unique listing(s) after dedupe.\n")
    for it in items:
        print("-" * 70)
        print(f"  Title:    {it['title']}")
        if it.get("location"):
            print(f"  Location: {it['location']}")
        if it.get("date"):
            print(f"  Posted:   {it['date']}")
        print(f"  Link:     {it['link']}")

    if args.dry_run:
        print("\n--dry-run: scan-data.json not modified.")
        print("\nItem dicts:")
        print(json.dumps(items, indent=2))
    else:
        print("\nNote: this plugin does not write scan-data.json directly.")
        print("Run via scrape_all.py orchestrator to persist results.")


if __name__ == "__main__":
    main()
