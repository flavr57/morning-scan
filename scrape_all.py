#!/usr/bin/env python3
"""
scrape_all.py — The Morning Pull master scraper.
Handles: Central Casting, Everyset, Aquent, LinkedIn, Respondent, UserInterviews
Writes results to scan-data.json which triggers generate-page.yml.
Credentials for login-required sites read from environment variables (GitHub Secrets).
"""

import json
import os
import time
import requests
from pathlib import Path
from datetime import datetime, timezone
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

DATA_PATH = Path("scan-data.json")

HEADERS = {
      "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
      )
}


# ─── LinkedIn (public guest API — no login) ───────────────────────────────────

def scrape_linkedin():
      items = []
      searches = [
          ("creative director", "Los Angeles, CA"),
          ("art director freelance", "Los Angeles, CA"),
          ("brand designer contract", "Los Angeles, CA"),
      ]
      seen = set()

    for keywords, location in searches:
              try:
                            url = (
                                              "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                                              f"?keywords={keywords.replace(' ', '+')}"
                                              f"&location={location.replace(', ', '%2C+').replace(' ', '+')}"
                                              "&f_TPR=r86400"
                                              "&start=0"
                            )
                            resp = requests.get(url, headers=HEADERS, timeout=15)
                            soup = BeautifulSoup(resp.text, "html.parser")

                  for card in soup.find_all("li"):
                                    title_el = card.find("h3", class_="base-search-card__title")
                                    company_el = card.find("h4", class_="base-search-card__subtitle")
                                    link_el = card.find("a", class_="base-card__full-link")

                if not title_el:
                                      continue

                title = title_el.get_text(strip=True)
                if title in seen:
                                      continue
                                  seen.add(title)

                company = company_el.get_text(strip=True) if company_el else ""
                link = (
                                      link_el.get("href", "https://www.linkedin.com/jobs")
                                      if link_el
                                      else "https://www.linkedin.com/jobs"
                )
                full_title = f"{title} — {company}" if company else title

                items.append({
                                      "platform": "LinkedIn",
                                      "title": full_title,
                                      "link": link,
                                      "alert": False,
                })

            time.sleep(2)
except Exception as e:
            print(f"LinkedIn '{keywords}' error: {e}")

    return items


# ─── Playwright scrapers (browser required) ───────────────────────────────────

def scrape_with_playwright():
      results = {}

    with sync_playwright() as p:
              browser = p.chromium.launch()

        # ── Central Casting (public) ─────────────────────────────────
        try:
                      page = browser.new_page()
                      page.goto(
                          "https://www.centralcasting.com/jobs/california/",
                          wait_until="networkidle",
                          timeout=30000,
                      )
                      page.wait_for_timeout(4000)

            items = []
            for sel in ["[class*='role']", "[class*='job']", "[class*='listing']", "article"]:
                              cards = page.query_selector_all(sel)
                              for card in cards:
                                                    text = card.inner_text().strip()
                                                    if len(text) < 10 or len(text) > 600:
                                                                              continue
                                                                          title = text.split("\n")[0][:140]
                                                    if len(title) < 5:
                                                                              continue
                                                                          a = card.query_selector("a[href]")
                                                    link = "https://www.centralcasting.com/jobs/california/"
                                                    if a:
                                                                              href = a.get_attribute("href") or ""
                                                                              link = href if href.startswith("http") else f"https://www.centralcasting.com{href}"
                                                                          items.append({
                                                        "platform": "Central Casting",
                                                        "title": title,
                                                        "link": link,
                                                        "alert": True,
                                                    })
                                                if items:
                                  break

                                                              results["Central Casting"] = items
            print(f"Central Casting: {len(items)} listing(s)")
            page.close()
except Exception as e:
            results["Central Casting"] = []
            results["Central Casting_err"] = str(e)
            print(f"Central Casting error: {e}")

        # ── Everyset (public) ────────────────────────────────────────
        try:
                      page = browser.new_page()
            page.goto(
                              "https://jobs.everyset.com/job-board",
                              wait_until="networkidle",
                              timeout=30000,
            )
            page.wait_for_timeout(4000)

            items = []
            for sel in [
                              "[class*='JobCard']", "[class*='job-card']",
                              "[class*='listing-card']", "[class*='PostingCard']",
                              "[data-testid*='job']", "article",
            ]:
                              cards = page.query_selector_all(sel)
                for card in cards:
                                      title = card.inner_text().strip().split("\n")[0][:140]
                                      if not title or len(title) < 4:
                                                                continue
                                                            a = card.query_selector("a[href]")
                    link = "https://jobs.everyset.com/job-board"
                    if a:
                                              href = a.get_attribute("href") or ""
                                              link = href if href.startswith("http") else f"https://jobs.everyset.com{href}"
                                          items.append({
                                                                    "platform": "Everyset",
                                                                    "title": title,
                                                                    "link": link,
                                                                    "alert": True,
                                          })
                if items:
                                      break

            results["Everyset"] = items
            print(f"Everyset: {len(items)} listing(s)")
            page.close()
except Exception as e:
            results["Everyset"] = []
            results["Everyset_err"] = str(e)
            print(f"Everyset error: {e}")

        # ── Aquent (public) ──────────────────────────────────────────
        try:
                      page = browser.new_page()
            page.goto(
                              "https://aquent.com/find-work?type=Creative+%26+Design&location=Los+Angeles%2C+CA",
                              wait_until="networkidle",
                              timeout=30000,
            )
            page.wait_for_timeout(4000)

            items = []
            for sel in [
                              "[class*='job-card']", "[class*='JobCard']",
                              "[class*='listing']", "[class*='result']", "article",
            ]:
                              cards = page.query_selector_all(sel)
                for card in cards:
                                      title_el = card.query_selector("h2, h3, h4, [class*='title']")
                    title = (
                                              title_el.inner_text().strip()
                                              if title_el
                                              else card.inner_text().strip().split("\n")[0]
                    )[:140]
                    if not title or len(title) < 4:
                                              continue
                                          a = card.query_selector("a[href]")
                    link = "https://aquent.com/find-work"
                    if a:
                                              href = a.get_attribute("href") or ""
                                              link = href if href.startswith("http") else f"https://aquent.com{href}"
                                          items.append({
                                                                    "platform": "Aquent",
                                                                    "title": title,
                                                                    "link": link,
                                                                    "alert": False,
                                          })
                if items:
                                      break

            results["Aquent"] = items
            print(f"Aquent: {len(items)} listing(s)")
            page.close()
except Exception as e:
            results["Aquent"] = []
            results["Aquent_err"] = str(e)
            print(f"Aquent error: {e}")

        # ── Respondent (login required) ──────────────────────────────
        r_email = os.environ.get("RESPONDENT_EMAIL", "")
        r_pass = os.environ.get("RESPONDENT_PASS", "")
        if r_email and r_pass:
                      try:
                                        page = browser.new_page()
                                        page.goto("https://app.respondent.io/login", wait_until="networkidle", timeout=20000)
                                        page.wait_for_timeout(2000)

                page.fill("input[type='email'], input[name='email']", r_email)
                page.fill("input[type='password'], input[name='password']", r_pass)
                page.click("button[type='submit']")
                page.wait_for_timeout(4000)

                items = []
                # If CAPTCHA blocked login, page won't reach the dashboard
                if "dashboard" in page.url or "projects" in page.url:
                                      page.goto(
                                          "https://app.respondent.io/respondents/v2/projects",
                                          wait_until="networkidle",
                                          timeout=2
