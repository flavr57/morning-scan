#!/usr/bin/env python3
"""
scrape_contra.py - log into contra.com and surface freelance opportunities
under platform "Contra".

Requires CONTRA_EMAIL and CONTRA_PASS environment variables. If they are
missing, scrape() returns []. If login fails (CAPTCHA, redirect loop, etc.)
scrape() logs a warning and returns [] rather than raising - the
orchestrator should record 0 items, not a hard error.

Contra uses a two-step login: email + Continue, then password + Log in.

Run with --dry-run: scrapes, prints results; does not modify scan-data.json.
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import urljoin

LOGIN_URL = "https://contra.com/log-in"
OPPS_URL = "https://contra.com/opportunities"
BASE_URL = "https://contra.com"
PLATFORM = "Contra"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CARD_SELECTORS = [
    "[data-testid*='opportunity']",
    "[data-testid*='OpportunityCard']",
    "[class*='OpportunityCard']",
    "[class*='opportunity-card']",
    "[class*='JobCard']",
    "[class*='job-card']",
    "a[href*='/opportunities/']",
    "article",
    "[class*='card']",
]

TITLE_SELECTORS = [
    "h2", "h3", "h4",
    "[class*='title' i]",
    "[data-testid*='title']",
    "a",
]

PAY_RE = re.compile(r"\$\s?\d[\d,]*(?:\.\d+)?(?:\s*(?:-|to)\s*\$?\d[\d,]*(?:\.\d+)?)?")
RATE_HINT_RE = re.compile(r"\b(?:hourly|hr|/h|fixed|fixed price|month|monthly|year)\b", re.I)


def _absolute_link(href):
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(BASE_URL, href)


def _extract_card(card):
    title = ""
    for sel in TITLE_SELECTORS:
        try:
            el = card.locator(sel).first
            if el.count() == 0:
                continue
            text = (el.inner_text(timeout=1500) or "").strip()
            if text:
                title = text.splitlines()[0].strip()[:140]
                break
        except Exception:
            continue

    link = ""
    try:
        link_el = card.locator("a[href]").first
        if link_el.count() > 0:
            href = link_el.get_attribute("href", timeout=1500) or ""
            link = _absolute_link(href)
    except Exception:
        link = ""
    # If the card itself is an anchor
    if not link:
        try:
            href = card.get_attribute("href", timeout=1500) or ""
            if href:
                link = _absolute_link(href)
        except Exception:
            pass

    try:
        body = card.inner_text(timeout=2000) or ""
    except Exception:
        body = ""

    pay = ""
    m = PAY_RE.search(body)
    if m:
        pay = m.group(0).strip()

    if not title and body:
        title = body.splitlines()[0].strip()[:140]

    return {"title": title, "link": link, "pay": pay, "body": body}


def _looks_like_opportunity(card_data):
    if not card_data["title"] or len(card_data["title"]) < 4:
        return False
    if not card_data["link"]:
        return False
    if "/opportunities/" not in card_data["link"] and "/jobs/" not in card_data["link"]:
        # Some Contra cards may link to project briefs without the
        # /opportunities/ prefix; accept anything not pointing back to login.
        if "/log-in" in card_data["link"]:
            return False
    return True


def to_scan_item(card_data):
    item = {
        "platform": PLATFORM,
        "title": card_data["title"],
        "link": card_data["link"],
        "alert": False,
    }
    if card_data["pay"]:
        item["pay"] = card_data["pay"]
    return item


def _login(page, email, password):
    """Two-step login. Return True on success, False otherwise."""
    try:
        page.goto(LOGIN_URL, wait_until="networkidle", timeout=25000)
    except Exception as e:
        print(
            f"Contra login page load failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return False

    page.wait_for_timeout(2000)

    # Step 1: email
    try:
        page.fill("input[type='email'], input[name='email']", email)
    except Exception as e:
        print(
            f"Contra: could not find email input: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return False
    try:
        page.click("button[type='submit'], button:has-text('Continue')")
    except Exception as e:
        print(
            f"Contra: could not click Continue: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return False

    # Wait for password field to appear
    try:
        page.wait_for_selector(
            "input[type='password'], input[name='password']",
            timeout=10000,
        )
    except Exception as e:
        # Possible reasons: captcha, magic-link prompt, account-not-found.
        print(
            f"Contra: password field never appeared "
            f"({type(e).__name__}); url={page.url}",
            file=sys.stderr,
        )
        return False

    # Step 2: password
    try:
        page.fill(
            "input[type='password'], input[name='password']", password,
        )
    except Exception as e:
        print(
            f"Contra: could not fill password: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return False
    try:
        page.click(
            "button[type='submit'], button:has-text('Log in'), "
            "button:has-text('Sign in')"
        )
    except Exception as e:
        print(
            f"Contra: could not submit password form: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return False

    page.wait_for_timeout(4000)

    if "/log-in" in page.url:
        print(
            f"Contra login appears to have failed - still at {page.url}",
            file=sys.stderr,
        )
        return False

    return True


def _collect_opportunities(page):
    try:
        page.goto(OPPS_URL, wait_until="networkidle", timeout=30000)
    except Exception as e:
        print(
            f"Contra opportunities page load failed: "
            f"{type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return []

    page.wait_for_timeout(3000)

    if "/log-in" in page.url:
        print(
            f"Contra opportunities redirected to login ({page.url}); "
            "session not authenticated",
            file=sys.stderr,
        )
        return []

    cards_data = []
    for selector in CARD_SELECTORS:
        try:
            locator = page.locator(selector)
            count = locator.count()
        except Exception:
            continue
        if count == 0:
            continue

        for i in range(count):
            try:
                card = locator.nth(i)
                data = _extract_card(card)
            except Exception:
                continue
            if _looks_like_opportunity(data):
                cards_data.append(data)

        if cards_data:
            break

    if not cards_data:
        print(
            "Contra opportunities page returned no recognizable cards; "
            "selectors may have changed",
            file=sys.stderr,
        )

    seen = set()
    unique = []
    for d in cards_data:
        key = d["link"] or d["title"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(d)
    return unique


def scrape():
    """Log into Contra and return scan-data items.

    Returns [] when credentials are unset or login fails. Never raises.
    """
    email = os.environ.get("CONTRA_EMAIL", "")
    password = os.environ.get("CONTRA_PASS", "")

    if not email or not password:
        print(
            "Contra creds not set (CONTRA_EMAIL / CONTRA_PASS); skipping",
            file=sys.stderr,
        )
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Contra: playwright not installed; skipping", file=sys.stderr)
        return []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=USER_AGENT)
                page = context.new_page()
                if not _login(page, email, password):
                    return []
                cards = _collect_opportunities(page)
            finally:
                browser.close()
    except Exception as e:
        print(
            f"Contra scrape failed: {type(e).__name__}: {e}",
            file=sys.stderr,
        )
        return []

    return [to_scan_item(c) for c in cards]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="print results without modifying scan-data.json",
    )
    args = ap.parse_args()

    print("Running Contra scraper...")
    items = scrape()
    print(f"\n{len(items)} listing(s) returned.\n")

    for it in items:
        print("-" * 70)
        print(f"  Title: {it['title']}")
        if it.get("pay"):
            print(f"  Pay:   {it['pay']}")
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
