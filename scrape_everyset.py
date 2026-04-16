#!/usr/bin/env python3
"""
Scrape jobs.everyset.com/job-board and merge results into scan-data.json.
Triggered by scrape-everyset.yml -- runs daily, pushes updated scan-data.json
which then triggers generate-page.yml to rebuild index.html.
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

DATA_PATH = Path("scan-data.json")


def scrape_everyset():
      items = []
      with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.goto(
                    "https://jobs.everyset.com/job-board",
                    wait_until="networkidle",
                    timeout=30000,
                )
                page.wait_for_timeout(4000)

          selectors = [
              "[class*='JobCard']",
                        "[class*='job-card']",
                        "[class*='listing-card']",
                        "[class*='PostingCard']",
                        "[data-testid*='job']",
                        "article",
          ]

        cards = []
        for sel in selectors:
                      cards = page.query_selector_all(sel)
                      if cards:
                                        break

                  for card in cards:
                                title = card.inner_text().strip().split("\n")[0][:140]
                                if not title or len(title) < 4:
                                                  continue

                                link = "https://jobs.everyset.com/job-board"
                                a = card.query_selector("a[href]")
                                if a:
                                                  href = a.get_attribute("href") or ""
                                                  link = href if href.startswith("http") else f"https://jobs.everyset.com{href}"

                                items.append({
                                    "platform": "Everyset",
                                    "title": title,
                                    "link": link,
                                    "alert": True,
                                })

        browser.close()
    return items


def main():
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

    data["items"] = [i for i in data.get("items", []) if i.get("platform") != "Everyset"]

    try:
              items = scrape_everyset()
              data["items"].extend(items)
              data["platforms"]["Everyset"] = {"status": "ok", "count": len(items)}
              print(f"Everyset: {len(items)} listing(s) found")
except Exception as e:
        data["errors"]["Everyset"] = str(e)
        data["platforms"]["Everyset"] = {"status": "error", "count": 0}
        print(f"Everyset error: {e}")

    data["generated"] = datetime.now(timezone.utc).isoformat()
    DATA_PATH.write_text(json.dumps(data, indent=2))


if __name__ == "__main__":
      main()
