#!/usr/bin/env python3
"""
scrape_project_casting.py — fetch projectcasting.com Los Angeles listings,
filter for Jason's profile (male, 54, white, longer hair, LA), and merge
matches into scan-data.json under platform "Project Casting".

Run with no args: scrapes, filters, prints, and writes to scan-data.json.
Run with --dry-run: scrapes, filters, prints; does not modify scan-data.json.
"""

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString

URL = "https://projectcasting.com/casting-calls/los-angeles"
PLATFORM = "Project Casting"
DATA_PATH = Path(__file__).resolve().parent / "scan-data.json"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


# ── Fetch ────────────────────────────────────────────────────────────────

def fetch(url):
    try:
        import requests
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        r.raise_for_status()
        return r.text
    except Exception as e:
        # Local LibreSSL can fail TLS to projectcasting.com; curl works.
        print(f"requests failed ({type(e).__name__}); falling back to curl", file=sys.stderr)
        out = subprocess.run(
            ["curl", "-sS", "-L", "-A", USER_AGENT, url],
            check=True, capture_output=True, text=True,
        )
        return out.stdout


# ── Parse ────────────────────────────────────────────────────────────────

DOLLAR_AMT_RE = re.compile(r"\$[\d,]+")
JOB_LINK_RE = re.compile(r"/job/[a-z0-9][a-z0-9-]+$")


def parse_listings(html):
    """Return a list of dicts, one per listing on the page."""
    soup = BeautifulSoup(html, "html.parser")

    title_anchors = []
    for h3 in soup.find_all("h3"):
        a = h3.find("a", href=JOB_LINK_RE, title=True)
        if not a:
            continue
        text = a.get_text(strip=True)
        if not text or text.lower().startswith("view details"):
            continue
        title_anchors.append(a)

    listings = []
    for i, a in enumerate(title_anchors):
        next_a = title_anchors[i + 1] if i + 1 < len(title_anchors) else None
        listings.append(_extract_listing(a, next_a))
    return listings


def _extract_listing(title_a, next_title_a):
    company_a = title_a.find_previous("a", class_="tdb-sacff-post")
    time_el = title_a.find_previous("time")
    tier_el = title_a.find_previous("div", class_="tdb-sacff-txt")
    prod_a = title_a.find_previous(
        "a", attrs={"data-taxonomy": "production-type"}
    )

    title = unescape(title_a.get_text(strip=True))
    link = title_a["href"]
    if link.startswith("/"):
        link = "https://projectcasting.com" + link

    casting_company = company_a.get_text(strip=True) if company_a else ""
    date_posted = time_el.get_text(strip=True) if time_el else ""
    production_type = prod_a.get_text(strip=True) if prod_a else ""

    pay_tier = ""
    m = DOLLAR_AMT_RE.search(title)
    if m:
        pay_tier = m.group(0)
    elif tier_el:
        t = tier_el.get_text(strip=True)
        if re.fullmatch(r"\$+", t):
            pay_tier = t

    body_text = _body_text_between(title_a, next_title_a)
    location = _extract_location(body_text)
    job_type = _extract_job_type(body_text)
    description = _extract_description(body_text)

    requirements = _extract_requirements(body_text)

    return {
        "title": title,
        "link": link,
        "production_type": production_type,
        "casting_company": casting_company,
        "date_posted": date_posted,
        "pay_tier": pay_tier,
        "location": location,
        "job_type": job_type,
        "description": description,
        "requirements": requirements,
        "body_text": body_text,
    }


def _body_text_between(title_a, next_title_a):
    """Concatenate text from elements following title_a, up to (but not including)
    the next listing's metadata start. The next listing begins with its
    company-anchor (class tdb-sacff-post), so we stop there."""
    boundary = None
    if next_title_a is not None:
        boundary = next_title_a.find_previous("a", class_="tdb-sacff-post")

    parts = []
    node = title_a
    while True:
        node = node.next_element
        if node is None or node is boundary:
            break
        if isinstance(node, NavigableString):
            s = str(node)
            if s.strip():
                parts.append(s)
    text = " ".join(parts)
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _extract_location(body):
    if re.search(r"\bLos Angeles\b", body):
        return "Los Angeles, CA"
    if re.search(r"\bCalifornia\b", body):
        return "California"
    return ""


def _extract_job_type(body):
    m = re.search(r"Job Type:\s*([A-Za-z][A-Za-z /,&-]{1,40})", body)
    return m.group(1).strip() if m else ""


def _extract_description(body):
    m = re.search(
        r"Job Description\s+(.+?)(?:Job Responsibilities|Requirements|Compensation|$)",
        body,
    )
    if not m:
        return ""
    desc = m.group(1).strip()
    sentences = re.split(r"(?<=[.!?])\s+", desc)
    short = sentences[0]
    if len(short) < 120 and len(sentences) > 1:
        short = short + " " + sentences[1]
    if len(short) > 200:
        short = short[:197].rstrip() + "..."
    return short


def _extract_requirements(body):
    m = re.search(
        r"Requirements\b(.+?)(?:Compensation|How to Apply|About |$)",
        body, flags=re.S,
    )
    return m.group(1).strip() if m else ""


# ── Filter ───────────────────────────────────────────────────────────────

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

def to_scan_item(listing):
    item = {
        "platform": PLATFORM,
        "title": listing["title"],
        "link": listing["link"],
        "alert": True,  # passed the filter — profile match
    }
    if listing["pay_tier"]:
        item["pay"] = listing["pay_tier"]
    if listing["location"]:
        item["location"] = listing["location"]
    if listing["date_posted"]:
        item["date"] = listing["date_posted"]
    if listing["casting_company"]:
        item["source"] = listing["casting_company"]
    if listing["description"]:
        item["short_description"] = listing["description"]
    if listing["production_type"]:
        item["production_type"] = listing["production_type"]
    return item


# ── Merge into scan-data.json ────────────────────────────────────────────

def merge_into_scan_data(matched_items, error_msg=None):
    if DATA_PATH.exists():
        data = json.loads(DATA_PATH.read_text())
    else:
        data = {
            "generated": datetime.now(timezone.utc).isoformat(),
            "location": "Hermosa Beach, CA",
            "items": [],
            "errors": {},
            "platforms": {},
        }

    items = [it for it in data.get("items", []) if it.get("platform") != PLATFORM]
    items.extend(matched_items)
    data["items"] = items

    errors = data.setdefault("errors", {})
    if error_msg:
        errors[PLATFORM] = error_msg
    else:
        errors.pop(PLATFORM, None)

    platforms = data.setdefault("platforms", {})
    platforms[PLATFORM] = {
        "status": "error" if error_msg else "ok",
        "count": len(matched_items),
    }

    DATA_PATH.write_text(json.dumps(data, indent=2) + "\n")


# ── Orchestrator entry point ─────────────────────────────────────────────

def scrape():
    """Fetch, parse, filter Project Casting listings.

    Returns a list of scan-data item dicts. Raises on fetch failure so the
    orchestrator can record the error.
    """
    html = fetch(URL)
    listings = parse_listings(html)
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
        html = fetch(URL)
    except Exception as e:
        print(f"FETCH FAILED: {e}", file=sys.stderr)
        if not args.dry_run:
            merge_into_scan_data([], error_msg=f"fetch: {e}")
        sys.exit(1)

    listings = parse_listings(html)
    print(f"Parsed {len(listings)} listing(s) from page 1\n")

    matched = []
    for L in listings:
        ok, reason = passes_filter(L)
        marker = "PASS" if ok else "skip"
        pay = L["pay_tier"] or "-"
        print(f"  [{marker}] {pay:>6}  {L['title'][:75]}")
        if not ok:
            print(f"           ↳ {reason}")
        else:
            matched.append(L)

    print(f"\n{len(matched)} match(es) after filter.\n")
    for L in matched:
        print("─" * 70)
        print(f"  Title:   {L['title']}")
        print(f"  Company: {L['casting_company']}")
        print(f"  Type:    {L['production_type']}")
        print(f"  Date:    {L['date_posted']}")
        print(f"  Pay:     {L['pay_tier']}")
        print(f"  Where:   {L['location']}")
        print(f"  Link:    {L['link']}")
        if L["description"]:
            print(f"  Desc:    {L['description']}")

    items = [to_scan_item(L) for L in matched]

    if args.dry_run:
        print("\n--dry-run: scan-data.json not modified.")
        print("\nWould merge these item dicts:")
        print(json.dumps(items, indent=2))
    else:
        merge_into_scan_data(items)
        print(f"\nWrote {len(items)} Project Casting item(s) to {DATA_PATH.name}")


if __name__ == "__main__":
    main()
