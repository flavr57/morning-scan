#!/usr/bin/env python3
"""
scrape_central_casting.py — fetch the public Central Casting LA jobs blog and
return the top 3 most recent listings under platform "Central Casting".

Different model from the other plugins:

- Hits blog.centralcasting.com/jobs-la/ (the actual public listings feed; the
  centralcasting.com/jobs/california/ page only embeds this blog as an iframe
  and exposes nothing useful directly).
- Always returns the top 3 most recent listings on the page, regardless of
  how old they are. Central Casting posts infrequently (sometimes weeks
  between posts), so a "last 24 hours" filter would almost always be empty
  and miss real signal.
- Does NOT apply the profile filter. We want visibility into what's
  currently posted, not curation.
"""

import argparse
import json
import sys
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

URL = "https://blog.centralcasting.com/jobs-la/"
PLATFORM = "Central Casting"
BASE = "https://blog.centralcasting.com"
TOP_N = 3

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
)


def _extract_post(article):
    """Return a dict for one Squarespace blog post, or None if malformed."""
    heading = article.find(["h1", "h2", "h3"])
    if not heading:
        return None
    title = heading.get_text(strip=True)
    if not title:
        return None

    link_el = heading.find("a", href=True)
    href = link_el["href"] if link_el else ""
    link = urljoin(BASE, href) if href else URL

    # Squarespace renders the post date in <time> and/or [class*="date"].
    date_text = ""
    time_el = article.find("time")
    if time_el:
        date_text = time_el.get_text(strip=True)
    if not date_text:
        date_el = article.select_one("[class*='date']")
        if date_el:
            date_text = date_el.get_text(strip=True)

    return {"title": title, "link": link, "date": date_text}


def to_scan_item(post):
    item = {
        "platform": PLATFORM,
        "title": post["title"],
        "link": post["link"],
        "alert": False,
    }
    if post.get("date"):
        item["date"] = post["date"]
    return item


def scrape():
    """Fetch top N recent Central Casting LA posts. Return list of scan items.

    Raises on network/HTTP failure so the orchestrator records the error.
    Returns [] only when the page parsed cleanly but contained zero posts.
    """
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }
    r = requests.get(URL, headers=headers, timeout=20)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    articles = soup.find_all("article")

    posts = []
    for art in articles:
        post = _extract_post(art)
        if post:
            posts.append(post)
        if len(posts) >= TOP_N:
            break

    return [to_scan_item(p) for p in posts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run", action="store_true",
        help="print results without modifying scan-data.json",
    )
    args = ap.parse_args()

    print(f"Fetching {URL}")
    try:
        items = scrape()
    except Exception as e:
        print(f"FETCH FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"\n{len(items)} item(s) returned (top {TOP_N} most recent).\n")
    for it in items:
        print("-" * 70)
        print(f"  Title: {it['title']}")
        if it.get("date"):
            print(f"  Date:  {it['date']}")
        print(f"  Link:  {it['link']}")

    if args.dry_run:
        print("\n--dry-run: scan-data.json not modified.")
        print("\nItem dicts:")
        print(json.dumps(items, indent=2))
    else:
        print("\nNote: this plugin does not write scan-data.json directly.")
        print("Run via scrape_all.py orchestrator to persist results.")


if __name__ == "__main__":
    main()
