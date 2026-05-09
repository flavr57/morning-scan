#!/usr/bin/env python3
"""
scrape_respondent.py - log into Respondent and surface available research-study
listings under platform "Respondent".

Requires RESPONDENT_EMAIL and RESPONDENT_PASS environment variables. If they
are missing, scrape() returns []. If login fails (CAPTCHA, redirect, etc.),
scrape() logs a warning and returns [] rather than raising.

Run with --dry-run: scrapes, prints results; does not modify scan-data.json.
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import urljoin

LOGIN_URL = "https://app.respondent.io/login"
STUDIES_URL = "https://app.respondent.io/respondents/v2/projects"
BASE_URL = "https://app.respondent.io"
PLATFORM = "Respondent"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

CARD_SELECTORS = [
    "[class*='ProjectCard']",
    "[class*='project-card']",
    "[class*='StudyCard']",
    "[class*='study-card']",
    "[class*='card']",
    "article",
]

TITLE_SELECTORS = ["h2", "h3", "[class*='title']", "[class*='Title']", "a"]

PAY_RE = re.compile(r"\$\d+(?:\.\d+)?")
DURATION_RE = re.compile(
    r"\d+\s*(?:min|mins|minute|minutes|hour|hours|hr|hrs)\b",
    re.IGNORECASE,
)


def _absolute_link(href):
    if not href:
        return ""
    href = href.strip()
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(BASE_URL, href)


def _extract_card_data(card):
    """Pull title, link, pay, duration from a Playwright Locator card."""
    title = ""
    link = ""

    for sel in TITLE_SELECTORS:
        try:
            el = card.locator(sel).first
            if el.count() == 0:
                continue
            text = (el.inner_text(timeout=1500) or "").strip()
            if text:
                title = text.splitlines()[0].strip()
                break
        except Exception:
            continue

    try:
        link_el = card.locator("a[href]").first
        if link_el.count() > 0:
            href = link_el.get_attribute("href", timeout=1500) or ""
            link = _absolute_link(href)
    except Exception:
        link = ""

    try:
        body = card.inner_text(timeout=2000) or ""
    except Exception:
        body = ""

    pay = ""
    m = PAY_RE.search(body)
    if m:
        pay = m.group(0)

    duration = ""
    m = DURATION_RE.search(body)
    if m:
        duration = m.group(0).strip()

    if not title and body:
        title = body.splitlines()[0].strip()

    return {
        "title": title,
        "link": link,
        "pay": pay,
        "duration": duration,
    }


def _looks_like_study(card_data):
    if not card_data["title"] or not card_data["link"]:
        return False
    if len(card_data["title"]) < 3:
        return False
    return True


def _is_high_signal(pay, duration):
    """Mark cards with strong pay-per-minute as alerts. Loose, optional."""
    if not pay:
        return False
    try:
        amt = float(pay.lstrip("$"))
    except ValueError:
        return False
    if amt >= 100:
        return True
    if amt >= 50 and duration:
        m = re.search(r"(\d+)\s*(min|hour|hr)", duration, re.IGNORECASE)
        if m:
            n = int(m.group(1))
            unit = m.group(2).lower()
            minutes = n * 60 if unit.startswith("h") else n
            if minutes <= 30:
                return True
    return False


def to_scan_item(card_data):
    item = {
        "platform": PLATFORM,
        "title": card_data["title"],
        "link": card_data["link"],
        "alert": _is_high_signal(card_data["pay"], card_data["duration"]),
    }
    if card_data["pay"]:
        item["pay"] = card_data["pay"]
    if card_data["duration"]:
        item["duration"] = card_data["duration"]
    return item


def _login_and_collect(playwright, email, password):
    """Run the login flow and return scraped card dicts. May return []."""
    browser = playwright.chromium.launch(headless=True)
    try:
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        try:
            page.goto(LOGIN_URL, wait_until="networkidle", timeout=20000)
        except Exception as e:
            print(
                f"Respondent login page load failed: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            return []

        page.wait_for_timeout(2000)

        try:
            page.fill("input[type='email'], input[name='email']", email)
            page.fill("input[type='password'], input[name='password']", password)
            page.click("button[type='submit']")
        except Exception as e:
            print(
                f"Respondent login form interaction failed: "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )
            return []

        page.wait_for_timeout(4000)

        current_url = page.url
        if "dashboard" not in current_url and "projects" not in current_url:
            print(
                "Respondent login blocked - likely CAPTCHA "
                f"(still at {current_url})",
                file=sys.stderr,
            )
            return []

        try:
            page.goto(STUDIES_URL, wait_until="networkidle", timeout=30000)
        except Exception as e:
            print(
                f"Respondent studies page load failed: "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )
            return []

        page.wait_for_timeout(3000)

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
                    data = _extract_card_data(card)
                except Exception:
                    continue
                if _looks_like_study(data):
                    cards_data.append(data)

            if cards_data:
                break

        if not cards_data:
            print(
                "Respondent studies page returned no recognizable cards; "
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
    finally:
        browser.close()


def scrape():
    """Log into Respondent and return scan-data items.

    Returns [] when credentials are unset or login fails. Never raises on
    auth/CAPTCHA - the orchestrator should record 0 items, not an error.
    """
    email = os.environ.get("RESPONDENT_EMAIL", "")
    password = os.environ.get("RESPONDENT_PASS", "")

    if not email or not password:
        print(
            "Respondent creds not set (RESPONDENT_EMAIL / RESPONDENT_PASS); "
            "skipping",
            file=sys.stderr,
        )
        return []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "Respondent: playwright not installed; skipping",
            file=sys.stderr,
        )
        return []

    try:
        with sync_playwright() as p:
            cards = _login_and_collect(p, email, password)
    except Exception as e:
        print(
            f"Respondent scrape failed: {type(e).__name__}: {e}",
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

    print("Running Respondent scraper...")
    items = scrape()
    print(f"\n{len(items)} listing(s) returned.\n")

    for it in items:
        print("-" * 70)
        print(f"  Title:    {it['title']}")
        if it.get("pay"):
            print(f"  Pay:      {it['pay']}")
        if it.get("duration"):
            print(f"  Duration: {it['duration']}")
        print(f"  Link:     {it['link']}")
        print(f"  Alert:    {it['alert']}")

    if args.dry_run:
        print("\n--dry-run: scan-data.json not modified.")
        print("\nItem dicts:")
        print(json.dumps(items, indent=2))
    else:
        print("\nNote: this plugin does not write scan-data.json directly.")
        print("Run via scrape_all.py orchestrator to persist results.")


if __name__ == "__main__":
    main()
