#!/usr/bin/env python3
"""
scrape_respondent.py - surface available research-study listings under
platform "Respondent".

Authentication: respondent.io added Google reCAPTCHA Enterprise (sitekey
6LeHiRUpAAAAAMJqgV0i) to its login form. From cloud IPs (GitHub Actions
runners) the reCAPTCHA token gets scored low and the server silently
rejects the email/password POST. Email/password is unrecoverable from
cloud IPs without a captcha-solving service.

Auth paths supported, in priority order:

  1. RESPONDENT_SESSION_COOKIE - the entire cookie header string from a
     browser tab that is signed into app.respondent.io. Skips login
     entirely. This is the path used in production and the one the
     orchestrator runs on every cron.
  2. RESPONDENT_EMAIL + RESPONDENT_PASS - tries the email/password flow.
     Useful locally when reCAPTCHA hasn't fired against your home IP.
     Will silently fail on the runner because of the reCAPTCHA Enterprise
     server-side token validation.

If neither is set, or if the cookie/login both fail to land on an
authenticated URL, scrape() returns [] rather than raising - the
orchestrator records "ok with 0 items" instead of an error state.

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


def _parse_cookie_header(s, domain):
    """Parse a "name=value; name2=value2" cookie header string into the
    list-of-dicts shape Playwright's context.add_cookies expects."""
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


def _collect_with_cookie(playwright, cookie_header):
    """Seed a Respondent session cookie and scrape studies. Returns []
    if the cookie is rejected or selectors find nothing."""
    cookies = _parse_cookie_header(cookie_header, ".respondent.io")
    if not cookies:
        print(
            "Respondent: cookie header parsed to zero pairs",
            file=sys.stderr,
        )
        return []

    browser = playwright.chromium.launch(headless=True)
    try:
        context = browser.new_context(user_agent=USER_AGENT)
        try:
            context.add_cookies(cookies)
        except Exception as e:
            print(
                f"Respondent: add_cookies failed: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            return []
        page = context.new_page()

        try:
            page.goto(STUDIES_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(
                f"Respondent studies page load failed: "
                f"{type(e).__name__}: {e}",
                file=sys.stderr,
            )
            return []
        # Give the SPA time to render after DOMContentLoaded fires.
        page.wait_for_timeout(6000)

        current_url = ""
        try:
            current_url = page.url or ""
        except Exception:
            pass
        if "/login" in current_url:
            print(
                "Respondent cookie was rejected - redirected to /login. "
                "The cookie has likely expired; refresh it.",
                file=sys.stderr,
            )
            return []

        return _harvest_cards(page)
    finally:
        browser.close()


def _harvest_cards(page):
    """Run the card selectors against an already-loaded page."""
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


def _login_and_collect(playwright, email, password):
    """Run the login flow and return scraped card dicts. May return []."""
    browser = playwright.chromium.launch(headless=True)
    try:
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()

        try:
            # Use domcontentloaded, not networkidle: the reCAPTCHA
            # Enterprise iframes keep network activity open indefinitely
            # and would otherwise time out before we can fill the form.
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=30000)
        except Exception as e:
            print(
                f"Respondent login page load failed: {type(e).__name__}: {e}",
                file=sys.stderr,
            )
            return []

        page.wait_for_timeout(3000)

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
    """Return Respondent study scan-data items, or [] on any auth failure.

    Cookie path is preferred (production). Email/password falls back when
    the cookie isn't set - only useful locally because reCAPTCHA Enterprise
    blocks the login form from cloud IPs.
    """
    cookie = os.environ.get("RESPONDENT_SESSION_COOKIE", "").strip()
    email = os.environ.get("RESPONDENT_EMAIL", "")
    password = os.environ.get("RESPONDENT_PASS", "")

    if not cookie and not (email and password):
        print(
            "Respondent: no auth available - set RESPONDENT_SESSION_COOKIE "
            "(preferred) or RESPONDENT_EMAIL + RESPONDENT_PASS",
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
            if cookie:
                cards = _collect_with_cookie(p, cookie)
            else:
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
