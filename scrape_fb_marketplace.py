#!/usr/bin/env python3
"""
scrape_fb_marketplace.py — FB Marketplace plugin (deferred stub).

FB Marketplace scraping is deferred. Facebook's Marketplace UI uses heavily
obfuscated React with rotating class names and GraphQL endpoints behind
anti-bot tokens; reliable scraping requires either an undocumented internal
API token or a brittle UI walk that breaks on every Facebook deploy. Per the
build spec ("lowest priority, acceptable to ship as a stub"), this plugin
returns [].

To revisit: use the FB_SESSION_COOKIE env var to seed a Playwright context
against https://www.facebook.com/marketplace/inbox/, walk the conversation
list, and extract counterparty + last-message snippet. Investigated
2026-05-08.
"""

import argparse
import json
import sys

URL = "https://www.facebook.com/marketplace/inbox/"
PLATFORM = "FB Marketplace"


def scrape():
    """Return an empty list. See module docstring for rationale."""
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print results without modifying scan-data.json")
    args = ap.parse_args()

    items = scrape()
    print(f"{PLATFORM}: deferred stub, returning {len(items)} item(s).")

    if args.dry_run:
        print("--dry-run: scan-data.json not modified.")
        print("Would merge these item dicts:")
        print(json.dumps(items, indent=2))
    else:
        print("Stub plugin does not write scan-data.json.")
        sys.exit(0)


if __name__ == "__main__":
    main()
