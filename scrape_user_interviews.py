#!/usr/bin/env python3
"""
scrape_user_interviews.py — fetch userinterviews.com studies listings for an
authenticated account and return them as scan-data items.

Login is required to see studies. Credentials come from env vars:
    USERINTERVIEWS_EMAIL, USERINTERVIEWS_PASS

Run with --dry-run for local testing; the orchestrator calls scrape() directly.
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import urljoin

LOGIN_URL = "https://www.userinterviews.com/accounts/signin"
STUDIES_URL = "https://www.userinterviews.com/studies"
FALLBACK_URLS = [
    "https://www.userinterviews.com/dashboard",
    "https://www.userinterviews.com/explore",
    "https://www.userinterviews.com/participants/dashboard",
]
PLATFORM = "UserInterviews"
BASE = "https://www.userinterviews.com"

CARD_SELECTORS = [
    "[class*='StudyCard']",
    "[class*='study-card']",
    "[class*='ProjectCard']",
    "[data-testid*='study']",
    "article",
]

TITLE_SELECTORS = ["h2", "h3", "[class*='title']", "[class*='Title']"]

PAY_RE = re.compile(r"\$\d+(?:\.\d+)?")
DURATION_RE = re.compile(r"\d+\s*(?:min|minute|minutes|hour|hours)", re.IGNORECASE)
TIME_AGO_RE = re.compile(
    r"\d+\s*(?:min|mins|minute|minutes|hour|hours|day|days|week|weeks)\s*ago",
    re.IGNORECASE,
)


def _log(msg):
    print(f"[{PLATFORM}] {msg}", file=sys.stderr)


def _absolute(href):
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return urljoin(BASE, href)


def _extract_first_text(card, selectors):
    for sel in selectors:
        try:
            el = card.query_selector(sel)
        except Exception:
            el = None
        if el:
            try:
                txt = (el.inner_text() or "").strip()
            except Exception:
                txt = ""
            if txt:
                return txt
    return ""


def _extract_title_and_link(card):
    title = _extract_first_text(card, TITLE_SELECTORS)
    link = ""

    try:
        anchors = card.query_selector_all("a[href]")
    except Exception:
        anchors = []

    if title:
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                txt = (a.inner_text() or "").strip()
            except Exception:
                continue
            if href and txt and txt[:40].lower() in title.lower():
                link = href
                break

    if not link:
        for a in anchors:
            try:
                href = a.get_attribute("href") or ""
                txt = (a.inner_text() or "").strip()
            except Exception:
                continue
            if href and txt:
                if not title:
                    title = txt
                link = href
                break

    if not link and anchors:
        try:
            link = anchors[0].get_attribute("href") or ""
        except Exception:
            link = ""

    return title.strip(), _absolute(link)


def _extract_optional_fields(card):
    try:
        text = (card.inner_text() or "").strip()
    except Exception:
        text = ""

    pay = ""
    duration = ""
    time_ago = ""

    if text:
        m = PAY_RE.search(text)
        if m:
            pay = m.group(0)
        m = DURATION_RE.search(text)
        if m:
            duration = m.group(0)
        m = TIME_AGO_RE.search(text)
        if m:
            time_ago = m.group(0)

    return pay, duration, time_ago


def _pay_value(pay_str):
    if not pay_str:
        return 0.0
    try:
        return float(pay_str.lstrip("$"))
    except ValueError:
        return 0.0


def _collect_cards(page):
    seen = set()
    cards = []
    for sel in CARD_SELECTORS:
        try:
            found = page.query_selector_all(sel)
        except Exception:
            found = []
        for c in found:
            key = id(c)
            if key in seen:
                continue
            seen.add(key)
            cards.append(c)
        if cards:
            break
    return cards


def _login(page, email, password):
    # UserInterviews moved their participant login flow in 2026:
    # /sign_in is now 404. /signin shows a role-picker. /accounts/signin
    # is the actual form page. That page has TWO forms stacked - the
    # first is Google SSO (form action=/auth/google), the second is
    # the password form (form action=/accounts/signin). A generic
    # button[type='submit'] click hits the Google form and bounces the
    # user to accounts.google.com, so the submit selector must be
    # scoped to the password form.
    page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(2500)

    email_sel = (
        "input[name='account_session[email]'], "
        "input[id='email'], "
        "input[name='user[email]'], "
        "input[type='email']"
    )
    pass_sel = (
        "input[name='account_session[password]'], "
        "input[id='password'], "
        "input[name='user[password]'], "
        "input[type='password']"
    )
    submit_sel = (
        "form[action='/accounts/signin'] button[type='submit'], "
        "form.Form:not(.AuthenticateWithGoogle) button[type='submit']"
    )

    try:
        page.fill(email_sel, email)
        page.fill(pass_sel, password)
        page.click(submit_sel)
    except Exception as e:
        _log(f"login form interaction failed: {type(e).__name__}: {e}")
        return False

    page.wait_for_timeout(5000)

    current_url = ""
    try:
        current_url = page.url or ""
    except Exception:
        pass

    # Landing on Google OAuth means we clicked the Google form (shouldn't
    # happen now that the selector is scoped), or the password form
    # itself redirected. Either way, we don't have a session.
    if "accounts.google.com" in current_url:
        _log(
            "UserInterviews login bounced to Google OAuth. The account "
            "may be Google-SSO-only; consider switching to a session "
            "cookie via USERINTERVIEWS_SESSION_COOKIE."
        )
        return False
    if "signin" in current_url or "sign_in" in current_url:
        _log(f"UserInterviews login appears to have failed (still at {current_url})")
        return False
    return True


def _open_studies(page):
    try:
        from playwright.sync_api import TimeoutError as PWTimeout
    except Exception:
        PWTimeout = Exception

    try:
        page.goto(STUDIES_URL, wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(5000)
        return STUDIES_URL
    except PWTimeout as e:
        _log(f"studies page timed out: {e}; trying fallbacks")
    except Exception as e:
        _log(f"studies page failed: {type(e).__name__}: {e}; trying fallbacks")

    for url in FALLBACK_URLS:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(4000)
            _log(f"using fallback URL: {url}")
            return url
        except Exception as e:
            _log(f"fallback {url} failed: {type(e).__name__}: {e}")
            continue

    return None


def _parse_cookie_header(s, domain):
    """Parse 'name=value; name2=value2' into Playwright's cookie shape."""
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


def scrape():
    """Authenticate and scrape UserInterviews studies. Returns list[dict].

    Auth priority: USERINTERVIEWS_SESSION_COOKIE first (preferred when
    the account is Google-SSO-only or when password login keeps bouncing
    to OAuth). USERINTERVIEWS_EMAIL + USERINTERVIEWS_PASS as a fallback.
    """
    cookie = os.environ.get("USERINTERVIEWS_SESSION_COOKIE", "").strip()
    email = os.environ.get("USERINTERVIEWS_EMAIL", "")
    password = os.environ.get("USERINTERVIEWS_PASS", "")

    if not cookie and not (email and password):
        _log("no auth available; skipping")
        return []

    try:
        from playwright.sync_api import sync_playwright
    except Exception as e:
        _log(f"playwright import failed: {type(e).__name__}: {e}")
        return []

    items = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            if cookie:
                cookies = _parse_cookie_header(cookie, ".userinterviews.com")
                if not cookies:
                    _log("cookie header parsed to zero pairs")
                    return []
                try:
                    context.add_cookies(cookies)
                except Exception as e:
                    _log(f"add_cookies failed: {type(e).__name__}: {e}")
                    return []
            elif not _login(page, email, password):
                return []

            landed = _open_studies(page)
            if landed is None:
                _log("could not load studies or any fallback page")
                return []

            cards = _collect_cards(page)
            if not cards:
                _log("no study cards found on page; selectors may be stale")
                return []

            for card in cards:
                title, link = _extract_title_and_link(card)
                if not title or not link:
                    continue
                pay, duration, time_ago = _extract_optional_fields(card)

                item = {
                    "platform": PLATFORM,
                    "title": title,
                    "link": link,
                }
                if pay:
                    item["pay"] = pay
                if duration:
                    item["duration"] = duration
                if time_ago:
                    item["time_ago"] = time_ago
                item["source"] = PLATFORM
                item["alert"] = _pay_value(pay) > 100
                items.append(item)
        finally:
            try:
                context.close()
            except Exception:
                pass
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

    if not os.environ.get("USERINTERVIEWS_EMAIL") or not os.environ.get("USERINTERVIEWS_PASS"):
        print("creds not set")
        return 0

    items = scrape()
    print(f"Got {len(items)} item(s) from {PLATFORM}.")
    if args.dry_run:
        print(json.dumps(items, indent=2))
    else:
        print(json.dumps(items, indent=2))
        print("(plugin does not write scan-data.json; orchestrator handles merging)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
