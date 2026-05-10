#!/usr/bin/env python3
"""
scrape_surfline.py - fetch a one-line surf snapshot for Manhattan Beach Pier
from Surfline's public forecast endpoints. Header chrome only - NOT a
scan-data platform. Not registered in scrape_all.py.

Public API, no auth, no key. Two endpoints:

- wave   - surf.min / surf.max (feet)
- rating - rating.key (e.g., FAIR, FAIR_TO_GOOD)

fetch_snapshot() returns {"height": "1-2", "rating": "fair to good"} or
None on any failure. Failures are silent by design - generate.py omits
the surf line when None.
"""

import argparse
import time

import requests

SPOT_ID = "5842041f4e65fad6a7708907"  # Manhattan Beach Pier
WAVE_URL = "https://services.surfline.com/kbyg/spots/forecasts/wave"
RATING_URL = "https://services.surfline.com/kbyg/spots/forecasts/rating"
TIMEOUT = 8


def _format_height(mn, mx):
    try:
        mn_i = int(round(float(mn)))
        mx_i = int(round(float(mx)))
    except (TypeError, ValueError):
        return ""
    if mn_i == mx_i:
        return str(mn_i)
    return f"{mn_i}-{mx_i}"


def _format_rating(key):
    if not key or not isinstance(key, str):
        return ""
    return key.lower().replace("_", " ")


def _pick_current(entries):
    """Pick the bin at or after now; fall back to the first entry."""
    if not entries:
        return None
    now = int(time.time())
    for e in entries:
        if e.get("timestamp", 0) >= now:
            return e
    return entries[0]


def fetch_snapshot():
    """Return {'height', 'rating'} for Manhattan Beach Pier or None."""
    try:
        params = {"spotId": SPOT_ID, "days": 1, "intervalHours": 3}
        wave = requests.get(WAVE_URL, params=params, timeout=TIMEOUT)
        rating = requests.get(RATING_URL, params=params, timeout=TIMEOUT)
        if wave.status_code != 200 or rating.status_code != 200:
            return None
        wave_list = wave.json().get("data", {}).get("wave", [])
        rating_list = rating.json().get("data", {}).get("rating", [])
        wp = _pick_current(wave_list)
        rp = _pick_current(rating_list)
        if not wp or not rp:
            return None
        surf = wp.get("surf", {}) or {}
        height = _format_height(surf.get("min"), surf.get("max"))
        rating_str = _format_rating((rp.get("rating") or {}).get("key"))
        if not height or not rating_str:
            return None
        return {"height": height, "rating": rating_str}
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="kept for interface parity; prints snapshot")
    ap.parse_args()
    snap = fetch_snapshot()
    if snap is None:
        print("(no snapshot)")
        return
    print(f"{snap['height']}, {snap['rating']}")


if __name__ == "__main__":
    main()
