#!/usr/bin/env python3
"""
scrape_contra.py — STUB. Deferred to Phase 3 (authenticated scrapers).

Contra opportunity listings are not publicly accessible without login.
Investigated on 2026-05-08:

  - https://contra.com/jobs
      HTTP 302 -> https://contra.com/log-in?redirectTo=%2Fjobs
      Hard login wall.

  - https://contra.com/opportunities
      HTTP 200, but the response is a SPA shell containing only
      <div id="root"></div>. Listings are rendered client-side via
      authenticated GraphQL. The embedded vike_pageContext JSON shows
      feature flag "membersOnly": true with "isAuthenticated": false,
      i.e. a guest cannot retrieve the feed.

  - https://contra.com/opportunities/los-angeles
  - https://contra.com/opportunities/design
  - https://contra.com/explore
      All return HTTP 404. No public filtered/category listing pages exist.

  - https://contra.com/sitemap.xml
      Exposes only user profiles and "hire-pages" (company landings).
      No opportunity URLs are sitemapped.

Conclusion: Contra requires a logged-in session to view opportunities.
This stub satisfies the plugin contract (scrape() returns []) so the
orchestrator records Contra as ok-with-zero-items rather than erroring.
A real implementation belongs in Phase 3 alongside Respondent and
UserInterviews, using stored credentials or a session cookie.
"""

import argparse

URL = "https://contra.com/opportunities"
PLATFORM = "Contra"

DEFERRAL_MESSAGE = (
    "Contra listings require login. Deferred to Phase 3 "
    "(authenticated scrapers). See module docstring for evidence."
)


def scrape() -> list[dict]:
    """Stub. Returns an empty list; does not raise."""
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="no-op for the stub; kept for interface parity")
    ap.parse_args()
    print(DEFERRAL_MESSAGE)
    print(f"Platform: {PLATFORM}")
    print(f"URL:      {URL}")
    print("scrape() returns: []")


if __name__ == "__main__":
    main()
