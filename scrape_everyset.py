#!/usr/bin/env python3
"""
scrape_everyset.py — fetch jobs.everyset.com/job-board listings via Playwright,
filter for Jason's profile (male, 54, white, longer hair, LA), and return
matched items for the orchestrator to merge into scan-data.json.

Run with no args: scrapes, filters, prints; orchestrator handles writes.
Run with --dry-run: scrapes, filters, prints; does not modify scan-data.json.
"""

import argparse
import json
import re
import sys
from urllib.parse import urljoin

URL = "https://jobs.everyset.com/job-board"
PLATFORM = "Everyset"
BASE_URL = "https://jobs.everyset.com"

CARD_SELECTORS = [
    "div:has(> div > .post-title)",
]
TITLE_SELECTOR = ".post-title-text"


# ── Fetch + parse ────────────────────────────────────────────────────────

def fetch_listings():
    """Launch chromium, load the job board, return a list of raw listing dicts."""
    from playwright.sync_api import sync_playwright

    listings = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        try:
            page.goto(URL, wait_until="networkidle", timeout=30000)
        except Exception:
            page.goto(URL, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(4000)

        cards = []
        for sel in CARD_SELECTORS:
            found = page.query_selector_all(sel)
            if found:
                cards = found
                break

        for card in cards:
            try:
                text = (card.inner_text() or "").strip()
            except Exception:
                continue
            if not text:
                continue

            title = ""
            try:
                title_el = card.query_selector(TITLE_SELECTOR)
                if title_el:
                    title = (title_el.inner_text() or "").strip()
            except Exception:
                title = ""
            if not title:
                title = text.splitlines()[0].strip()
            title = title[:140]
            if len(title) < 4:
                continue

            # Cards on jobs.everyset.com are JS click-targets with no
            # per-listing href. Fall back to the job-board URL so the user
            # can still navigate to the listing.
            link = ""
            try:
                anchor = card.query_selector("a[href]")
                if anchor:
                    href = anchor.get_attribute("href") or ""
                    if href:
                        link = urljoin(BASE_URL, href)
            except Exception:
                link = ""
            if not link:
                link = URL

            listings.append({
                "title": title,
                "link": link,
                "body_text": text,
                "requirements": "",
            })

        context.close()
        browser.close()
    return listings


# ── Filter (verbatim from scrape_project_casting.py) ─────────────────────

def passes_filter(listing):
    """
    Profile: male, 54, white, longer hair, LA-based.
    Returns (ok: bool, reason: str). When in doubt, include.
    """
    text = (listing["body_text"] + " " + listing["title"]).lower()
    title = listing["title"].lower()
    req = (listing["requirements"] or "").lower()

    # 1. Gender — the requirements section is authoritative.
    # If req says "female model" or similar with no "male" mention in req or title,
    # exclude. Description-level "male and female models" doesn't override.
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

    # 2. Age — explicit numeric ranges with max < 50
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

    # "in their 20s/30s/early 40s" decade-only signals
    if re.search(
        r"\bin (?:his|her|their) (?:20s|early 20s|mid 20s|late 20s|"
        r"30s|early 30s|mid 30s|late 30s|early 40s)\b", text,
    ):
        return False, "younger decade specified"

    # Kids/teens only
    if re.search(r"\b(?:children|kids?|toddlers?|babies|infants)\b", text) and \
       not re.search(r"\badults?\b", text):
        if re.search(r"\bages?\s+\d{1,2}\s*[-–to]+\s*(?:1[0-7]|[3-9])\b", text):
            return False, "kids only"

    # 3. Ethnicity — exclude only if specifically restricts to non-white
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

    # 4. Hair — exclude only on hard requirements
    if re.search(
        r"\b(?:short hair only|shaved heads? only|must be bald|"
        r"buzzed (?:hair )?only|no long hair)\b", text,
    ):
        return False, "hair restriction"

    # 5. Specific physical attributes Jason doesn't have
    # Only exclude on hard requirements; allow if "experience preferred not required"
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

    # Male height range with min >= 6 feet — covers the
    # "Male models height range: 6'0"–6'3"" pattern. Includes curly quotes
    # because the source page uses U+2019/U+201D, not ASCII '/".
    male_h = re.search(
        r"\bmale\s+(?:models?\s+)?(?:height\s*(?:range|requirement)?\s*:?\s*)"
        r"(\d{1,2})\s*['’′]",
        req,
    )
    if male_h and int(male_h.group(1)) >= 6 and not soft_escape:
        return False, f"male height min {male_h.group(1)}'+"

    return True, "match"


# ── Output formatting ────────────────────────────────────────────────────

LA_RE = re.compile(r"\b(los angeles|l\.?a\.?|hollywood|burbank|santa monica|culver city|pasadena)\b", re.I)
TIME_AGO_RE = re.compile(
    r"\b(\d+\s*(?:minute|minutes|min|hour|hours|hr|hrs|day|days|week|weeks|month|months)\s*ago|today|yesterday)\b",
    re.I,
)
DATE_RE = re.compile(
    r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+\d{1,2}(?:,\s*\d{4})?\b",
    re.I,
)


def to_scan_item(listing):
    item = {
        "platform": PLATFORM,
        "title": listing["title"],
        "link": listing["link"],
        "alert": True,
    }
    body = listing.get("body_text", "")
    if LA_RE.search(body) or LA_RE.search(listing["title"]):
        item["location"] = "Los Angeles, CA"
    m_time = TIME_AGO_RE.search(body)
    if m_time:
        item["time_ago"] = m_time.group(0).strip()
    m_date = DATE_RE.search(body)
    if m_date:
        item["date"] = m_date.group(0).strip()
    return item


# ── Orchestrator entry point ─────────────────────────────────────────────

def scrape():
    """Fetch, parse, filter Everyset listings.

    Returns a list of scan-data item dicts. Raises on fetch failure so the
    orchestrator can record the error.
    """
    listings = fetch_listings()
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
        listings = fetch_listings()
    except Exception as e:
        print(f"FETCH FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(listings)} card(s)\n")

    matched = []
    for L in listings:
        ok, reason = passes_filter(L)
        marker = "PASS" if ok else "skip"
        print(f"  [{marker}] {L['title'][:90]}")
        if not ok:
            print(f"           reason: {reason}")
        else:
            matched.append(L)

    print(f"\n{len(matched)} match(es) after filter.\n")
    items = [to_scan_item(L) for L in matched]

    if args.dry_run:
        print("--dry-run: scan-data.json not modified.")
        print("\nWould return these item dicts to the orchestrator:")
        print(json.dumps(items, indent=2))
    else:
        print("Standalone run. The orchestrator normally handles writes.")
        print(json.dumps(items, indent=2))


if __name__ == "__main__":
    main()
