#!/usr/bin/env python3
"""
scrape_ebay.py — fetch eBay Seller Hub Sold activity and buyer Messages
using a session cookie supplied via the EBAY_SESSION_COOKIE env var.

Returns scan-data items with platform "eBay Sold" or "eBay Messages".
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import urljoin

SOLD_URL = "https://www.ebay.com/sh/sold"
MESSAGES_URL = "https://www.ebay.com/mesg/eBayMessageCenterEnter"
MESSAGES_URL_FALLBACK = "https://www.ebay.com/myb/Messages"
SIGNIN_HOST = "signin.ebay.com"

PLATFORM_SOLD = "eBay Sold"
PLATFORM_MESSAGES = "eBay Messages"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

PRICE_RE = re.compile(r"\$[\d,]+(?:\.\d{2})?")
SOLD_LIMIT = 20
MESSAGES_LIMIT = 10


def parse_cookie_string(s: str, domain: str) -> list[dict]:
    out = []
    for pair in s.split(";"):
        pair = pair.strip()
        if not pair or "=" not in pair:
            continue
        name, value = pair.split("=", 1)
        out.append({
            "name": name.strip(),
            "value": value.strip(),
            "domain": domain,
            "path": "/",
        })
    return out


def _abs_link(href: str, base: str) -> str:
    if not href:
        return base
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(base, href)


def _is_signin(url: str) -> bool:
    return SIGNIN_HOST in (url or "")


def scrape_sold(page) -> list[dict]:
    try:
        page.goto(SOLD_URL, wait_until="domcontentloaded", timeout=30000)
    except Exception as e:
        print(f"eBay Sold: navigation failed: {type(e).__name__}: {e}",
              file=sys.stderr)
        return []

    if _is_signin(page.url):
        print("eBay session cookie expired or invalid — refresh it in "
              "GitHub Secrets", file=sys.stderr)
        return []

    try:
        page.wait_for_timeout(2000)
    except Exception:
        pass

    selectors = [
        "[data-testid*='item']",
        "[class*='sold-item']",
        "tr[class*='sold']",
        "[class*='listing']",
        "tr",
    ]

    rows = []
    for sel in selectors:
        try:
            found = page.query_selector_all(sel)
        except Exception:
            found = []
        if found and len(found) >= 1:
            rows = found
            break

    items = []
    seen_links = set()
    for row in rows:
        if len(items) >= SOLD_LIMIT:
            break
        try:
            text = (row.inner_text() or "").strip()
        except Exception:
            text = ""
        if not text:
            continue

        anchor = None
        try:
            anchor = row.query_selector("a[href*='/itm/']") \
                or row.query_selector("a[href*='/sh/']") \
                or row.query_selector("a")
        except Exception:
            anchor = None
        if not anchor:
            continue

        try:
            href = anchor.get_attribute("href") or ""
            title = (anchor.inner_text() or "").strip()
        except Exception:
            continue

        if not title or not href:
            continue
        link = _abs_link(href, SOLD_URL)
        if link in seen_links:
            continue
        seen_links.add(link)

        item = {
            "platform": PLATFORM_SOLD,
            "title": title[:200],
            "link": link,
        }

        m = PRICE_RE.search(text)
        if m:
            item["pay"] = m.group(0)

        date_match = re.search(
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}"
            r"(?:,\s*\d{4})?\b",
            text,
        )
        if date_match:
            item["date"] = date_match.group(0)

        items.append(item)

    if not items:
        print("eBay Sold: no rows matched any selector", file=sys.stderr)
    return items


def scrape_messages(page) -> list[dict]:
    target = MESSAGES_URL
    try:
        resp = page.goto(target, wait_until="domcontentloaded", timeout=30000)
        status = resp.status if resp else 0
        url_now = page.url or ""
        looks_like_messages = "message" in url_now.lower() or "mesg" in url_now.lower()
        needs_fallback = status >= 400 or (
            not _is_signin(url_now) and not looks_like_messages
        )
        if needs_fallback:
            try:
                page.goto(MESSAGES_URL_FALLBACK,
                          wait_until="domcontentloaded", timeout=30000)
                target = MESSAGES_URL_FALLBACK
            except Exception:
                pass
    except Exception:
        try:
            page.goto(MESSAGES_URL_FALLBACK,
                      wait_until="domcontentloaded", timeout=30000)
            target = MESSAGES_URL_FALLBACK
        except Exception as e:
            print(f"eBay Messages: navigation failed: {type(e).__name__}: {e}",
                  file=sys.stderr)
            return []

    if _is_signin(page.url):
        print("eBay session cookie expired or invalid — refresh it in "
              "GitHub Secrets", file=sys.stderr)
        return []

    try:
        page.wait_for_timeout(2000)
    except Exception:
        pass

    selectors = [
        "tr[class*='unread']",
        "[class*='message-row']",
        "tr[class*='message']",
        "[data-testid*='message']",
        "[class*='msg-row']",
        "li[class*='message']",
    ]

    rows = []
    for sel in selectors:
        try:
            found = page.query_selector_all(sel)
        except Exception:
            found = []
        if found:
            rows = found
            break

    items = []
    seen = set()
    for row in rows:
        if len(items) >= MESSAGES_LIMIT:
            break
        try:
            text = (row.inner_text() or "").strip()
        except Exception:
            text = ""
        if not text:
            continue

        try:
            anchor = row.query_selector("a")
        except Exception:
            anchor = None

        href = ""
        if anchor:
            try:
                href = anchor.get_attribute("href") or ""
            except Exception:
                href = ""
        link = _abs_link(href, target) if href else target

        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        sender = ""
        subject = ""
        if lines:
            sender = lines[0][:80]
            subject = lines[1][:140] if len(lines) > 1 else lines[0][:140]

        title = f"from {sender}: {subject}" if sender and subject else (
            subject or sender or "eBay buyer message"
        )

        if title in seen:
            continue
        seen.add(title)

        items.append({
            "platform": PLATFORM_MESSAGES,
            "title": title[:200],
            "link": link,
            "alert": True,
        })

    if not items:
        print("eBay Messages: no rows matched any selector", file=sys.stderr)
    return items


def scrape() -> list[dict]:
    cookie = os.environ.get("EBAY_SESSION_COOKIE", "")
    if not cookie.strip():
        print("eBay: EBAY_SESSION_COOKIE not set — returning []",
              file=sys.stderr)
        return []

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        print(f"eBay: playwright not available: {e}", file=sys.stderr)
        return []

    cookie_list = parse_cookie_string(cookie, ".ebay.com")
    if not cookie_list:
        print("eBay: cookie string parsed to zero pairs — returning []",
              file=sys.stderr)
        return []

    items: list[dict] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            context = browser.new_context(
                user_agent=USER_AGENT,
                viewport={"width": 1280, "height": 800},
            )
            try:
                context.add_cookies(cookie_list)
            except Exception as e:
                print(f"eBay: failed to add cookies: {type(e).__name__}: {e}",
                      file=sys.stderr)
                return []

            page = context.new_page()

            try:
                items.extend(scrape_sold(page))
            except Exception as e:
                print(f"eBay Sold: unexpected failure: {type(e).__name__}: {e}",
                      file=sys.stderr)

            try:
                items.extend(scrape_messages(page))
            except Exception as e:
                print(
                    f"eBay Messages: unexpected failure: "
                    f"{type(e).__name__}: {e}",
                    file=sys.stderr,
                )
        finally:
            try:
                browser.close()
            except Exception:
                pass

    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print results without modifying scan-data.json")
    args = ap.parse_args()

    if not os.environ.get("EBAY_SESSION_COOKIE", "").strip():
        print("cookie not set")
        if args.dry_run:
            print(json.dumps([], indent=2))
        sys.exit(0)

    items = scrape()
    print(f"\n{len(items)} eBay item(s) returned.\n")
    for it in items:
        print("-" * 70)
        print(f"  Platform: {it.get('platform')}")
        print(f"  Title:    {it.get('title')}")
        print(f"  Link:     {it.get('link')}")
        if it.get("pay"):
            print(f"  Pay:      {it['pay']}")
        if it.get("date"):
            print(f"  Date:     {it['date']}")

    if args.dry_run:
        print("\n--dry-run: scan-data.json not modified.")
        print(json.dumps(items, indent=2))


if __name__ == "__main__":
    main()
