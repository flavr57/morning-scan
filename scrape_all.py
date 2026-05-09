#!/usr/bin/env python3
"""
scrape_all.py — orchestrator for The Morning Pull.

Imports each scrape_<platform> module, calls its scrape() function, and merges
results into scan-data.json. One platform failing must not break the others.

Plugin contract: each plugin module exposes `scrape() -> list[dict]` returning
items in the shape produced by scrape_project_casting.to_scan_item().
"""

import importlib
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

DATA_PATH = Path(__file__).resolve().parent / "scan-data.json"
LOCATION = "Hermosa Beach, CA"

# (platform_label, module_name) — adding a new scraper is one line here.
PLUGINS = [
    ("Project Casting", "scrape_project_casting"),
    ("LinkedIn", "scrape_linkedin"),
    ("Central Casting", "scrape_central_casting"),
    ("Everyset", "scrape_everyset"),
    ("Aquent", "scrape_aquent"),
    ("Contra", "scrape_contra"),
    ("Indeed", "scrape_indeed"),
    ("Respondent", "scrape_respondent"),
    ("UserInterviews", "scrape_user_interviews"),
]

# Platforms that must never appear in scan-data.json. Stripped every run.
HARD_EXCLUSIONS = {"Gmail", "Casting Networks"}


def run_plugin(label, module_name):
    """Invoke one plugin. Return (items, error) — error is None on success."""
    try:
        mod = importlib.import_module(module_name)
        items = mod.scrape()
        if not isinstance(items, list):
            return [], f"plugin returned {type(items).__name__}, expected list"
        return items, None
    except Exception as e:
        traceback.print_exc()
        return [], f"{type(e).__name__}: {e}"


def load_existing():
    if not DATA_PATH.exists():
        return {
            "generated": "",
            "location": LOCATION,
            "items": [],
            "errors": {},
            "platforms": {},
        }
    return json.loads(DATA_PATH.read_text())


def main():
    data = load_existing()
    data["location"] = LOCATION
    data["generated"] = datetime.now(timezone.utc).isoformat()

    # Reset platforms we're about to run; strip hard exclusions; preserve
    # other entries (e.g., manually seeded items) untouched.
    active_platforms = {label for label, _ in PLUGINS}
    drop = active_platforms | HARD_EXCLUSIONS
    data["items"] = [
        it for it in data.get("items", []) if it.get("platform") not in drop
    ]
    errors = data.setdefault("errors", {})
    platforms = data.setdefault("platforms", {})
    for label in drop:
        errors.pop(label, None)
        platforms.pop(label, None)

    total = 0
    for label, module_name in PLUGINS:
        print(f"\n=== {label} ({module_name}) ===")
        items, err = run_plugin(label, module_name)
        if err:
            errors[label] = err
            platforms[label] = {"status": "error", "count": 0}
            print(f"{label}: ERROR — {err}")
            continue
        data["items"].extend(items)
        platforms[label] = {"status": "ok", "count": len(items)}
        print(f"{label}: {len(items)} item(s)")
        total += len(items)

    DATA_PATH.write_text(json.dumps(data, indent=2) + "\n")
    print(f"\nWrote {total} item(s) across {len(PLUGINS)} plugin(s) to {DATA_PATH.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
