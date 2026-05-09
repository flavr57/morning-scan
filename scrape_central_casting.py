#!/usr/bin/env python3
"""
scrape_central_casting.py — fetch centralcasting.com California jobs,
filter for Jason's profile (male, 54, white, longer hair, LA), and return
matches to the orchestrator under platform "Central Casting".

Run with --dry-run to scrape, filter, and print without writing.
"""

import argparse
import json
import re
import sys
from urllib.parse import urljoin

URL = "https://www.centralcasting.com/jobs/california/"
PLATFORM = "Central Casting"
BASE = "https://www.centralcasting.com"

CARD_SELECTORS = [
    "[class*='role']",
    "[class*='job']",
    "[class*='listing']",
    "article",
]

MIN_TEXT = 10
MAX_TEXT = 600
MAX_TITLE = 140
MIN_TITLE = 5


# ── Filter (copied from scrape_project_casting.py) ───────────────────────

def passes_filter(listing):
    """
    Profile: male, 54, white, longer hair, LA-based.
    Returns (ok: bool, reason: str). When in doubt, include.
    """
    text = (listing["body_text"] + " " + listing["title"]).lower()
    title = listing["title"].lower()
    req = (listing["requirements"] or "").lower()

    female_only_signals = [
        r"\bfor female\b", r"\bfemale models?\b", r"\bfemale talent\b",
        r"\bwomen only\b", r"\bfemale[-\s]identifying\b",
        r"\ball[-\s]female\b", r"\bfemale[-\s]presenting\b",
    ]
    has_female_only = any(re.search(p, title) or re.search(p, req)
                          for p in female_only_signals)
    male_invite_scope = req + " " + title
    has_male_invite = bool(re.search(
        r"\b(male|men|all genders|any gender|gender[s]?:?\s*(all|any|open)|"
        r"all ethnicities and genders|open to all genders)\b",
        male_invite_scope,
    ))
    if has_female_only and not has_male_invite:
        return False, "female-only listing"

    age_patterns = [
        r"ages?\s+(\d{1,2})\s*[-–to]+\s*(\d{1,2})",
        r"\b(\d{1,2})\s*[-–]\s*(\d{1,2})\s*(?:years?\s*old|y\.?o\.?)\b",
        r"between (?:the )?ages? of\s+(\d{1,2})\s*(?:and|to|[-–])\s*(\d{1,2})",
    ]
    for pat in age_patterns:
        for m in re.finditer(pat, text):
            lo, hi = int(m.group(1)), int(m.group(2))
            if 5 <= lo <= 90 and 5 <= hi <= 90 and hi < 50:
                return False, f"age range {lo}-{hi}"
            if 5 <= lo <= 90 and lo > 54:
                return False, f"age range {lo}+ (above 54)"

    if re.search(
        r"\bin (?:his|her|their) (?:20s|early 20s|mid 20s|late 20s|"
        r"30s|early 30s|mid 30s|late 30s|early 40s)\b", text,
    ):
        return False, "younger decade specified"

    if re.search(r"\b(?:children|kids?|toddlers?|babies|infants)\b", text) and \
       not re.search(r"\badults?\b", text):
        if re.search(r"\bages?\s+\d{1,2}\s*[-–to]+\s*(?:1[0-7]|[3-9])\b", text):
            return False, "kids only"

    ethnic_restrict = [
        r"\bafrican[\s-]american (?:talent|men|women|models?|male|female|only)\b",
        r"\bblack (?:talent|men|women|models?|male|female|only)\b",
        r"\basian (?:american )?(?:talent|men|women|models?|male|female|only)\b",
        r"\blatin[oa] (?:talent|men|women|male|female|models?|only)\b",
        r"\bhispanic (?:talent|men|women|models?|male|female|only)\b",
        r"\bbipoc (?:talent|only)\b",
        r"\bpeople of color only\b",
    ]
    has_ethnic_restrict = any(re.search(p, title) or re.search(p, req)
                              for p in ethnic_restrict)
    has_open_ethnicity = bool(re.search(
        r"\b(?:all ethnicities|open to all ethnic|any ethnicity|all races|"
        r"caucasian|\bwhite\b)\b", text,
    ))
    if has_ethnic_restrict and not has_open_ethnicity:
        return False, "ethnicity excludes white"

    if re.search(
        r"\b(?:short hair only|shaved heads? only|must be bald|"
        r"buzzed (?:hair )?only|no long hair)\b", text,
    ):
        return False, "hair restriction"

    soft_escape = bool(re.search(
        r"experience\s+(?:preferred|a plus|nice to have|not required)|"
        r"not required.*?experience", text,
    ))
    physical_blocks = [
        (r"\bmust be (?:6\'|6 ft|over 6|at least 6\'|6 feet|"
         r"6 feet (?:tall|or taller))\b", "height 6'+"),
        (r"\bprofessional (?:dancer|athlete|boxer|fighter|gymnast|model)s?\b",
         "professional athlete/dancer/model"),
        (r"\bolympic (?:boxers?|athletes?|level|wrestlers?|gymnasts?)\b",
         "olympic-level athlete"),
        (r"\bcompetitive (?:boxer|fighter|wrestler|gymnast)s?\b",
         "competitive athlete"),
        (r"\bfootball (?:player|experience required)s?\b", "football player"),
    ]
    for pat, label in physical_blocks:
        if re.search(pat, title) or re.search(pat, req):
            if soft_escape:
                continue
            return False, f"requires {label}"

    male_h = re.search(
        r"\bmale\s+(?:models?\s+)?(?:height\s*(?:range|requirement)?\s*:?\s*)"
        r"(\d{1,2})\s*['’′]",
        req,
    )
    if male_h and int(male_h.group(1)) >= 6 and not soft_escape:
        return False, f"male height min {male_h.group(1)}'+"

    return True, "match"


# ── Fetch + parse (Playwright) ───────────────────────────────────────────

def _detect_location(text):
    if re.search(r"\bLos Angeles\b", text, re.I):
        return "Los Angeles, CA"
    if re.search(r"\bCalifornia\b", text, re.I):
        return "California"
    return "California"


def _extract_cards(page):
    for sel in CARD_SELECTORS:
        cards = page.query_selector_all(sel)
        if cards:
            return cards, sel
    return [], None


def fetch_listings():
    """Render the page with Playwright and extract raw listing dicts."""
    from playwright.sync_api import sync_playwright

    listings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.goto(URL, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(4000)

            cards, sel_used = _extract_cards(page)
            if not cards:
                return [], None

            seen_links = set()
            for card in cards:
                try:
                    text = card.inner_text().strip()
                except Exception:
                    continue
                if len(text) < MIN_TEXT or len(text) > MAX_TEXT:
                    continue

                first_line = text.splitlines()[0].strip()
                title = first_line[:MAX_TITLE]
                if len(title) < MIN_TITLE:
                    continue

                anchor = card.query_selector("a[href]")
                href = anchor.get_attribute("href") if anchor else None
                link = urljoin(BASE, href) if href else URL

                if link in seen_links:
                    continue
                seen_links.add(link)

                listings.append({
                    "title": title,
                    "link": link,
                    "body_text": text,
                    "requirements": "",
                    "location": _detect_location(text),
                })
        finally:
            browser.close()

    return listings, None


# ── Output formatting ────────────────────────────────────────────────────

def to_scan_item(listing):
    item = {
        "platform": PLATFORM,
        "title": listing["title"],
        "link": listing["link"],
        "alert": True,
    }
    if listing.get("location"):
        item["location"] = listing["location"]
    return item


# ── Orchestrator entry point ─────────────────────────────────────────────

def scrape():
    """Fetch, parse, filter Central Casting listings.

    Returns a list of scan-data item dicts. Raises on fetch failure so the
    orchestrator can record the error.
    """
    listings, _ = fetch_listings()
    matched = [L for L in listings if passes_filter(L)[0]]
    return [to_scan_item(L) for L in matched]


# ── Main ─────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print results without modifying scan-data.json")
    args = ap.parse_args()

    print(f"Fetching {URL}")
    try:
        listings, _ = fetch_listings()
    except Exception as e:
        print(f"FETCH FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(listings)} card(s) from page\n")

    matched = []
    for L in listings:
        ok, reason = passes_filter(L)
        marker = "PASS" if ok else "skip"
        print(f"  [{marker}] {L['title'][:90]}")
        if not ok:
            print(f"           -> {reason}")
        else:
            matched.append(L)

    print(f"\n{len(matched)} match(es) after filter.\n")
    items = [to_scan_item(L) for L in matched]

    if args.dry_run:
        print("--dry-run: not writing anywhere.")
        print(json.dumps(items, indent=2))
    else:
        for it in items:
            print(json.dumps(it))


if __name__ == "__main__":
    main()
