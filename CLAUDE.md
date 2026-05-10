# Morning Pull — Build Spec

This document is authoritative project context. Read it fully before starting any task in this repository.

## Mission

One bookmarked URL. One click in the morning. Fresh content from every platform every day.

Live URL: `https://flavr57.github.io/morning-scan`

The page is a daily scan across all of Jason's income streams and contract sources. It surfaces opportunities and updates so he can click through and act on them himself. **The system is about discovery, never about auto-application.**

## What This Is Not

- Not an acting/casting tracker. Acting is one column among many.
- Not a notification system. Telegram delivery is to be stripped, not preserved. Jason wants the bookmarked URL to be the only delivery channel.
- Not an auto-applier. Scrapers find listings and surface them. They never log in for the purpose of submitting screeners, applications, or messages. They only log in when login is required to *see* the listings.

## Hard Exclusions

These platforms are NOT part of this system. They appear in older versions of `generate.py` and `scan-data.json`. Strip them out when encountered. Do not add them back.

- **Gmail** — Never include. Not a platform in this system.
- **Casting Networks** — Never include. Jason does not use it.

## Authoritative Platform List

Eleven platforms across five columns. Every one is required. None is a higher priority than the others. The end state is all eleven scraping reliably and rendering on the page.

**Research**
- Respondent (`respondent.io`) — auth required (Playwright + login)
- UserInterviews (`userinterviews.com/studies`) — auth required (Playwright + login)

**Freelance**
- Aquent (`aquent.com/find-work`) — public, Playwright

**Acting**
- Central Casting (`centralcasting.com/jobs/california/`) — public, Playwright
- Everyset (`jobs.everyset.com/job-board`) — public, Playwright
- Project Casting (`projectcasting.com/casting-calls/los-angeles`) — public, requests + BeautifulSoup. Scraper already built (`scrape_project_casting.py`).

**Jobs**
- LinkedIn — public guest API, no login. Use the endpoint `linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search`. The existing `scrape_all.py` (broken indentation, but logic is sound) shows the approach: hit the endpoint with `keywords`, `location`, and `f_TPR=r86400` parameters, parse cards via BeautifulSoup. Preserve this approach in the rewrite. Default search queries: `creative director`, `art director freelance`, `brand designer contract`, all in Los Angeles, CA.
- Indeed — public listings via search URL pattern `indeed.com/q-{keywords}-l-los-angeles,-ca-jobs.html`. Likely needs Playwright with a realistic browser fingerprint due to bot detection. Default search queries: `art director`, `creative director`, `brand designer`, in Los Angeles.

**Marketplace**
- eBay sales activity — auth required, session cookie approach preferred over email/password (Jason will provide a fresh cookie when needed)
- eBay buyer messages — auth required, same session cookie
- FB Marketplace — auth required, session cookie approach preferred. Lowest priority of all platforms, acceptable to ship as a stub if reliable scraping is hard.

## Profile Filter (where applicable)

For listings that target talent (acting, modeling, casting):
- Male
- Age 54
- White
- Longer hair (shoulder length or longer)
- LA-based

Be loose with these. Jason can play men in their late 40s. Age ranges that end at 50-53 should still pass. The filter exists to remove obvious mismatches (female-only, age 18-30, professional dancers, height 6'+ requirements), not to enforce literal birth-year accuracy.

See `scrape_project_casting.py` for the canonical filter implementation. Reuse the same logic in any scraper that surfaces talent listings (Central Casting, Everyset).

## Architecture Target

```
.github/workflows/
  scrape-all.yml         daily cron, runs scrape_all.py
  generate-page.yml      triggered by scan-data.json change

scrape_all.py            orchestrator, calls each plugin scraper, merges results
scrape_project_casting.py   plugin (template)
scrape_<platform>.py     plugin per platform, same shape as Project Casting
generate.py              renders index.html from scan-data.json
scan-data.json           shared data file, written by orchestrator
index.html               output, served by GitHub Pages
```

**Orchestrator contract.** `scrape_all.py` imports each `scrape_<platform>.py` module, calls its `scrape()` function, collects returned items, merges all results into `scan-data.json` under `items[]` and `platforms{}`, captures errors per platform under `errors{}`. One platform failing must not break the others. Each plugin is responsible for its own fetch, parse, and filter; the orchestrator only orchestrates.

**Plugin contract.** Each `scrape_<platform>.py` exposes a `scrape() -> list[dict]` function that returns scan-data items in the shape used by `to_scan_item()` in `scrape_project_casting.py`. Plugins do not write `scan-data.json` themselves when called by the orchestrator. They may still support a standalone `__main__` block with `--dry-run` for local testing, mirroring the Project Casting pattern.

## Pipeline

1. Cron fires `scrape-all.yml` daily at 5am PT (13:00 UTC).
2. Workflow installs deps (`requests`, `beautifulsoup4`, `playwright` + chromium browser), runs `python scrape_all.py`.
3. Orchestrator runs every plugin, merges into `scan-data.json`, commits if changed.
4. Push of `scan-data.json` triggers `generate-page.yml`.
5. Generate workflow runs `python generate.py`, commits the new `index.html`, pushes.
6. GitHub Pages serves the new `index.html` at `https://flavr57.github.io/morning-scan`.
7. Jason clicks bookmark in the morning, sees fresh content.

No Telegram. Strip the Telegram notification step from `generate-page.yml` as part of Phase 1.

## Existing Code to Reference

The current repo has logic worth preserving even though files are corrupted:

- **`scrape_all.py`** — broken Python indentation, will not run as-is, will be rewritten from scratch. BUT it contains the proven LinkedIn guest-API approach, the public Playwright patterns for Central Casting / Everyset / Aquent, and the start of a Respondent login flow. Read this file as a reference for HOW each platform was being approached, then rewrite cleanly. Do not preserve its file structure or indentation. The file is also truncated mid-function, so the UserInterviews logic is not visible — rebuild from scratch.
- **`scrape_everyset.py`** — broken, replace.
- **`scrape_project_casting.py`** — clean, working, the template for all new plugins.

## Current Repository State (as of May 8, 2026)

- Local `main` is 37 commits ahead of `origin/main`. Nothing has been pushed in weeks. The live site is stuck on April 20, 2026.
- `scrape_all.py` is broken (indentation), will be rewritten.
- `scrape_everyset.py` is broken, will be replaced.
- `scrape-all.yml` has mangled YAML indentation, invalid. Rewrite from scratch.
- `scrape_project_casting.py` works (verified by dry run on May 8). Returned 0 matches today, with reasons that all check out.
- `generate.py` works. Already updated to include Project Casting in `PLATFORM_CATEGORY`, `PLATFORM_LINK_VERB`, `HIGH_SIGNAL_PLATFORMS`, and `col1_platforms`. Still has Gmail and Casting Networks references that need to be stripped. Indeed is not yet wired in.
- `generate-page.yml` looks valid. Strip the Telegram step from it.
- GitHub Pages is configured and serving from `main` branch. Don't touch its settings.
- `scan-data.json` is being updated locally on May 7 and May 8 but the updates are not pushed.

## Build Phases

Execute these in order. Each phase ends with clean commits that can stand on their own. Push at the end of each phase.

### Phase 1 — Pipeline Restoration

**Goal:** End-to-end pipeline working with Project Casting as the only plugged-in scraper. Live site updates fresh on tomorrow's cron.

1. Push the existing 37 commits ahead of origin to `main` so the live site stops being stale. This will trigger `generate-page.yml` on the latest `scan-data.json` and refresh `index.html`.
2. Strip Gmail and Casting Networks from `generate.py`:
   - Remove from `PLATFORM_CATEGORY`
   - Remove from `PLATFORM_LINK_VERB`
   - Remove from `HIGH_SIGNAL_PLATFORMS`
   - Remove from column assignments
   - Restructure column assignments so the page balances
   - Verify `is_urgent()` no longer references Gmail
3. Add Indeed to `generate.py` skeletons (PLATFORM_CATEGORY=Jobs, PLATFORM_LINK_VERB="View on", HIGH_SIGNAL_PLATFORMS, column assignment) so it's ready when the scraper is added in Phase 2.
4. Strip the Telegram notification step from `generate-page.yml`. Keep the rest of the workflow intact.
5. Rewrite `scrape-all.yml` from scratch with valid YAML. Daily cron at 13:00 UTC (5am PT). Install Python deps, install Playwright + chromium browser, run `python scrape_all.py`, commit `scan-data.json` if changed, push. Pull credentials from GitHub Secrets.
6. Rewrite `scrape_all.py` from scratch as a thin orchestrator. For Phase 1 it imports and calls only `scrape_project_casting.scrape()`. Build the orchestrator structure such that adding a new plugin is a one-line import and one-line call. Merge results, write `scan-data.json`, never crash if one plugin fails.
7. Refactor `scrape_project_casting.py` to expose a `scrape() -> list[dict]` function that the orchestrator can call. Keep its `__main__` block working for local `--dry-run` testing.
8. Delete `scrape_everyset.py` (it will be rewritten in Phase 2).
9. Verify locally: run `python scrape_all.py`, confirm `scan-data.json` updates correctly, run `python generate.py`, confirm `index.html` renders without Gmail or Casting Networks columns.
10. Commit, push, watch Actions tab to confirm both workflows run cleanly.

**Phase 1 is done when:** the bookmarked URL serves a page generated within the last 24 hours, with Project Casting visible as a column and no Gmail or Casting Networks columns visible.

### Phase 2 — Public Scrapers

**Goal:** Add every scraper that does not require login. Each new plugin makes the page richer.

Build these in any order, parallel work via sub-agents encouraged:

1. **LinkedIn** (`scrape_linkedin.py`) — public guest API. Reference the approach in the broken `scrape_all.py`. Preserve the three default search queries unless better ones emerge.
2. **Central Casting** (`scrape_central_casting.py`) — Playwright on `centralcasting.com/jobs/california/`. Reference the broken `scrape_all.py` for the selector approach. Apply the profile filter from `scrape_project_casting.py`.
3. **Everyset** (`scrape_everyset.py`) — Playwright on `jobs.everyset.com/job-board`. Reference the broken `scrape_all.py`. Apply the profile filter.
4. **Aquent** (`scrape_aquent.py`) — Playwright on `aquent.com/find-work?type=Creative+%26+Design&location=Los+Angeles%2C+CA`. Reference the broken `scrape_all.py`. No profile filter needed (this is freelance creative work, not talent casting).
5. **Indeed** (`scrape_indeed.py`) — Playwright on `indeed.com/q-{keywords}-l-los-angeles,-ca-jobs.html`. Use a realistic browser fingerprint. Default search queries: `art director`, `creative director`, `brand designer`. Indeed has bot detection but is generally scrapeable with Playwright; if it proves unreliable in a reasonable time budget, document the blocker and ship a stub. Do not let Indeed block Phase 2 completion.

For each new scraper, plug it into `scrape_all.py` and confirm `generate.py` already has the platform configured. Run `--dry-run` locally, then commit. One scraper per commit.

**Phase 2 is done when:** all five public scrapers are running daily, or have a documented stub explaining why they couldn't be made reliable.

### Phase 3 — Authenticated Scrapers

**Goal:** Add the remaining scrapers that require credentials.

Required GitHub Secrets:
- `RESPONDENT_EMAIL`, `RESPONDENT_PASS`
- `USERINTERVIEWS_EMAIL`, `USERINTERVIEWS_PASS`
- `EBAY_SESSION_COOKIE` (Jason will provide a fresh cookie when needed)
- `FB_SESSION_COOKIE` (same)

Build these:

1. **Respondent** (`scrape_respondent.py`) — Playwright + login. Reference the partial flow in broken `scrape_all.py`. Handle CAPTCHA gracefully — if login fails, log the error and return empty.
2. **UserInterviews** (`scrape_user_interviews.py`) — Playwright + login. The April 20 live site shows a `page.goto: Timeout 30000ms exceeded` error on this platform. Increase timeout, use `wait_until="domcontentloaded"` instead of `networkidle`, and add a fallback if the studies page times out.
3. **eBay** sales and messages (`scrape_ebay.py`) — Playwright with seeded session cookie. May produce two item types (sales activity, buyer messages) — use the existing `eBay Sold` and `eBay Messages` platform values if useful.
4. **FB Marketplace** (`scrape_fb_marketplace.py`) — Playwright with seeded session cookie. Lowest priority. If reliable scraping is hard, ship a stub.

For platforms requiring session cookies, document the one-time setup process for Jason at the end of Phase 3:
- How to extract the cookie from his browser
- Where to paste it (GitHub Actions Secrets)
- How often it needs refreshing (typically when scraping starts failing)

**Phase 3 is done when:** every platform on the authoritative list has a scraper, even if some are stubs documenting auth blockers or pending session cookies.

## What Requires Jason

Only two things require Jason's involvement once this spec is handed off:

1. **GitHub Secrets.** Before Phase 3 begins, Jason must add the credential pairs and session cookies listed above to the repo's Actions secrets. Provide him a single consolidated list when Phase 2 completes.
2. **Final review.** When Phase 1 is done and the live site has refreshed for the first time, surface the URL to Jason for visual review. Same after each subsequent phase.

Everything else — file edits, commits, pushes, workflow runs, debugging — happens without him.

## What Does Not Require Jason

- Greenlighting individual file changes
- Approving each commit
- Confirming each scraper's design
- Choosing which platform to build next within a phase
- Deciding scraper internals (parsing, error handling, structure)

Use sub-agents (`Task` tool) to parallelize where appropriate. Within Phase 2 and Phase 3, multiple scrapers can be built in parallel. The orchestrator integration is the serialization point.

## Conventions

- Python 3.12. Stdlib + `requests` + `beautifulsoup4` + `playwright` (chromium).
- Each scraper module is named `scrape_<platform_snake>.py`.
- Each scraper module exposes `scrape() -> list[dict]`.
- Each scraper module supports `__main__` with `--dry-run`.
- Profile filter logic lives in the scraper module that needs it (not centralized) until duplication justifies extraction.
- Listings dicts use the keys defined by `to_scan_item()` in `scrape_project_casting.py`.
- Commits are atomic per logical unit. Squash if necessary before pushing a phase.
- Never use m-dashes in any user-facing copy (Jason's preference). Hyphens or em-dashes only.
- No emoji in code, output, or commit messages.

## Reference Files

- `scrape_project_casting.py` — canonical scraper structure, fetch/parse/filter/output pattern, profile filter implementation
- `scrape_all.py` (broken but logic-bearing) — proven approaches for LinkedIn, Central Casting, Everyset, Aquent, Respondent
- `generate.py` — page renderer, source of truth for column layout and platform metadata
- `index.html` — current rendered output (will refresh after Phase 1)
- `scan-data.json` — shared data file, schema visible in current contents

## Done Definition

The system is done when:
- Cron runs at 5am PT daily without intervention
- All twelve platforms have working scrapers (or documented stubs with clear blockers)
- The bookmarked URL serves a fresh page every morning
- No platform failure cascades into other platform failures
- Jason has not been asked to click "yes" on any individual file change since this spec was handed off
