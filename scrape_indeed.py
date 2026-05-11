#!/usr/bin/env python3
"""
scrape_indeed.py - STUB.

Indeed cannot be made reliable from a GitHub Actions runner with
reasonable effort. Investigation summary (2026-05-11):

  - Local Mac (home IP) with Playwright + Chrome 120 UA returns a real
    results page (1.6 MB HTML, <title>Art Director Jobs...</title>) with
    10 cards bearing the stable `data-jk` attribute. Parser works.
  - GH Actions runner with the exact same code returns "empty (no job
    cards found)" across every query, every selector strategy.
  - Confirmed not a CAPTCHA wall (no captcha markers detected and
    looks_like_captcha() never trips).
  - Confirmed not selector drift: swapping to the stable `data-jk`
    selector and canonical viewjob URLs (commit 5aa33cc) didn't change
    the runner outcome.
  - Mobile UA + mobile viewport (commit babb4f0) didn't change the
    runner outcome either. m.indeed.com no longer resolves (DNS dropped),
    so Indeed serves layout based on UA against www.indeed.com - and
    blocks both variants from cloud IP ranges.
  - Brief disallowed proxy rotation / paid services.

Conclusion: Indeed performs differential serving based on source IP.
GitHub Actions runner IPs are on Microsoft Azure ranges that are widely
known and actively rate-limited / silently stripped by Indeed.

The original Phase 2 spec (CLAUDE.md) explicitly authorizes a stub for
this case: "if it proves unreliable in a reasonable time budget,
document the blocker and ship a stub. Do not let Indeed block Phase 2
completion."

scrape() returns [] cleanly so the orchestrator records "ok with 0
items" rather than an error - the page then renders the Indeed section
as a normal "Nothing new today (<date>)." empty state.

To revive: roll back to commit babb4f0^ and figure out a non-cloud-IP
fetch path (residential proxy, self-hosted runner, etc.).
"""

import argparse


PLATFORM = "Indeed"
URL = "https://www.indeed.com/jobs"


def scrape():
    """Stub. Returns []; never raises."""
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--dry-run", action="store_true",
        help="no-op for the stub; kept for interface parity",
    )
    ap.parse_args()
    print(
        "scrape_indeed.py is a stub; Indeed blocks GitHub Actions IPs. "
        "See module docstring for evidence."
    )
    print(f"Platform: {PLATFORM}")
    print(f"URL:      {URL}")
    print("scrape() returns: []")


if __name__ == "__main__":
    main()
