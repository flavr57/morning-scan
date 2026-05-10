# Morning Scan Fixes — Priority Brief

**Date:** 2026-05-09
**For:** Claude Code in `~/Documents/GitHub/morning-scan`

## Context

This brief covers fixes to the modular Python scrapers (`scrape_linkedin.py`, `scrape_indeed.py`, `scrape_aquent.py`, `scrape_everyset.py`) and to `generate.py`. Six items in priority order.

Do **NOT** touch `scrape_all.py` or `.github/workflows/scrape-all.yml`. They are broken and dead, orthogonal to this work, and a separate cleanup task.

After each fix, run the scraper individually with `--dry-run` first to verify before letting it write to `scan-data.json`.

---

## Priority 1: Fix LinkedIn scraper

**File:** `scrape_linkedin.py`

**Symptom:** Returns 0 listings. Yesterday this scraper was finding 15. Something changed.

**Diagnose first, then fix.**

### Diagnostic steps

1. Run `python3 scrape_linkedin.py --dry-run` and capture the output.
2. Make a single curl request to the search URL with the exact User-Agent the scraper uses, save the HTML to a temp file, and count `<li>` tags containing `base-search-card__title`.
3. If the HTML has zero matching cards, LinkedIn has either changed selectors or is rate-limiting based on the request signature.
4. Inspect the returned HTML for clues: login wall, empty body, captcha, redirect, or different class names.

### Likely fixes (try in order)

1. Update the User-Agent string to current Chrome (132+).
2. Add the following request headers: `Sec-Fetch-Dest`, `Sec-Fetch-Mode`, `Sec-Fetch-Site`, `Referer: https://www.linkedin.com/`.
3. If still empty after both, switch from `requests` to Playwright (chromium, headless, realistic viewport and locale, same as `scrape_indeed.py`).
4. If LinkedIn changed their class names, update selectors. Show diff before pushing.

**Acceptance:** At least one of the three search queries returns at least one listing.

---

## Priority 2: Fix Indeed scraper

**File:** `scrape_indeed.py`

**Symptom:** `RuntimeError: all Indeed queries failed: art director: empty (no job cards found); creative director: empty; brand designer: empty`

### Likely cause

The URL format `https://www.indeed.com/q-{keywords}-l-Los-Angeles,-CA-jobs.html` is non-standard. Indeed serves different content depending on URL format and may not return job cards on this URL anymore.

### Fix

1. Replace `BASE_URL_TEMPLATE` with the standard search URL format:
   ```
   https://www.indeed.com/jobs?q={keywords}&l=Los+Angeles%2C+CA&fromage=1
   ```
   Where `keywords` is URL-encoded (use `urllib.parse.quote_plus`) and `fromage=1` filters to last 24 hours.

2. Save the HTML output from one query to a temp file. Inspect it for the actual class names and `data-testid` attributes Indeed is using today. The selectors in `CARD_SELECTORS` may be stale.

3. If a captcha or human-verification page is detected (the existing `looks_like_captcha` helper handles this), log it clearly and exit that query rather than retrying.

**Acceptance:** At least one of the three queries returns at least one listing. If still fails after URL update and selector refresh, report what was diagnosed and stop. Do not mask failures.

---

## Priority 3: Aquent — new URL + keyword filter

**File:** `scrape_aquent.py`

### 3a. Change URL to remote-only, sorted newest first

**Replace** the current `URL` constant:

```python
URL = (
    "https://aquent.com/find-work"
    "?type=Creative+%26+Design&location=Los+Angeles%2C+CA"
)
```

**With:**

```python
URL = (
    "https://aquent.com/find-work"
    "?size=n_12_n"
    "&filters%5B0%5D%5Bfield%5D=offsite_preference.keyword"
    "&filters%5B0%5D%5Bvalues%5D%5B0%5D=Remote"
    "&filters%5B0%5D%5Btype%5D=any"
    "&sort%5B0%5D%5Bfield%5D=posted_date"
    "&sort%5B0%5D%5Bdirection%5D=desc"
)
```

This URL pulls Remote-only roles sorted by posted date descending.

### 3b. Add a title keyword filter

After scraping cards but before returning them, filter by title.

**INCLUDE titles containing any of (case-insensitive):**
- senior designer
- graphic designer
- art director
- associate creative director
- creative director
- brand designer

**EXCLUDE titles containing any of (case-insensitive):**
- price analyst
- privacy analyst
- data analyst
- digital marketing
- visual analyst
- search performance manager
- accounting support
- product manager
- technical motion designer
- adobe experience manager
- developer
- pharmaceutical

### Filter rules

1. If title contains an EXCLUDE keyword, drop it (exclude wins).
2. If title contains an INCLUDE keyword, keep it.
3. If title contains neither, drop it (default to excluding unrelated roles).
4. During `--dry-run`, print the filter decision and reason for each listing so the user can spot-check.

**Acceptance:** Dry-run output shows clear pass/skip decisions per listing, and the kept items are creative roles that Jason would actually apply for.

---

## Priority 4: Verify Everyset scraper

**File:** `scrape_everyset.py`

**Status:** Code looks correct, public URL `https://jobs.everyset.com/job-board` does not require login. User reports the section consistently shows "Nothing new today" but suspects there should be matches.

### Diagnostic steps

1. Run `python3 scrape_everyset.py --dry-run`.
2. Report:
   - How many cards were parsed before filtering
   - How many passed the filter
   - For each filtered-out card: the reason (e.g., "female-only", "age range 18-30", "kids only")
3. If 0 cards parsed, the CSS selectors in `CARD_SELECTORS` are stale and need updating against current Everyset HTML.
4. If many cards parsed but all filtered out: the filter (which is a verbatim copy from `scrape_project_casting.py`) may be too strict for Everyset's listing format. Report a sample of titles that got filtered.

**Acceptance:** Diagnostic output makes it clear whether the issue is parsing, filtering, or genuine zero matches. Do not change filter rules without showing what would change first.

---

## Priority 5: UI — "Nothing new today" should include the date

**File:** `generate.py`

In `render_platform_section`, change:

```python
elif not items:
    body = '<p class="empty-state">Nothing new today.</p>'
```

To:

```python
elif not items:
    today_str = datetime.now().strftime("%b %-d")
    body = f'<p class="empty-state">Nothing new today ({today_str}).</p>'
```

**Reason:** When every section says "Nothing new today" with no date, it's impossible to tell whether the page updated or is showing stale data. Adding the date makes the freshness obvious.

**Acceptance:** Empty sections render as e.g. `Nothing new today (May 9).`

---

## Priority 6: UI — Apply / Applied button states

**File:** `generate.py`

### Current behavior

Every item has a button labeled "Applied" that, when clicked, immediately removes the item from view via `dismissItem(id)`.

### Desired behavior

- **Default state:** button labeled `Apply`, styled with active appearance (navy `#1E3F6B`, like other links).
- **After click:** button label becomes `Applied`, styled muted (grey `#9A8878`).
- Item stays visible (does NOT get removed) so user can see what they've already applied to.
- State persists across page reloads via localStorage.

### Implementation

1. In `render_lead_item` and `render_scan_item`, change button label from `Applied` to `Apply`. Add a CSS class for the applied state.

   New button HTML pattern:
   ```html
   <button class="apply-btn" data-id="{iid}" onclick="markApplied('{iid}')">Apply</button>
   ```

2. Add CSS for both states. Replace the existing `.dismiss-btn` rules:
   ```css
   .apply-btn {
     background: none;
     border: 1px solid #1E3F6B;
     color: #1E3F6B;
     font-size: 12px;
     font-weight: 500;
     padding: 2px 8px;
     border-radius: 3px;
     cursor: pointer;
     letter-spacing: 0.04em;
     transition: all 0.15s;
   }
   .apply-btn:hover { background: #1E3F6B; color: #fff; }
   .apply-btn.applied {
     border-color: #C8BAAE;
     color: #9A8878;
     background: none;
     cursor: default;
   }
   .apply-btn.applied:hover { background: none; color: #9A8878; }
   ```

3. Replace the `<script>` block at the bottom of the page:
   ```javascript
   const STORAGE_KEY = 'morning-pull-applied';

   function getApplied() {
     try { return JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]'); }
     catch { return []; }
   }

   function markApplied(id) {
     const applied = getApplied();
     if (!applied.includes(id)) applied.push(id);
     localStorage.setItem(STORAGE_KEY, JSON.stringify(applied));
     document.querySelectorAll('.apply-btn[data-id="' + id + '"]').forEach(btn => {
       btn.textContent = 'Applied';
       btn.classList.add('applied');
     });
   }

   document.addEventListener('DOMContentLoaded', function() {
     const applied = getApplied();
     applied.forEach(id => {
       document.querySelectorAll('.apply-btn[data-id="' + id + '"]').forEach(btn => {
         btn.textContent = 'Applied';
         btn.classList.add('applied');
       });
     });
   });
   ```

4. Apply this change globally — it should affect every item across LinkedIn, Indeed, Aquent, Project Casting, Central Casting, Everyset, eBay, and any other platform.

**Acceptance:** Default button label is "Apply" in navy. Clicking flips it to "Applied" in grey. Item stays visible. Reloading the page preserves the Applied state. Old localStorage key `morning-pull-dismissed` can be left in place (no migration needed).

---

## Final verification

After all six priorities are complete, run:

```bash
python3 scrape_linkedin.py
python3 scrape_indeed.py
python3 scrape_aquent.py
python3 scrape_everyset.py
python3 scrape_project_casting.py
python3 generate.py && open index.html
```

And confirm:

1. LinkedIn section has real results
2. Indeed section has real results
3. Aquent section has Remote-only creative roles, no analyst/developer/pharma roles
4. Everyset section either has results OR shows clear diagnosis of why it's empty
5. Project Casting section retains its matches
6. Empty sections include the date
7. All buttons say "Apply" by default and flip to "Applied" on click
8. UserInterviews error message renders cleanly on a single line

Do not push to origin. Local-only for review first.

## Out of scope for this brief

- The broken `scrape_all.py` / `scrape-all.yml` cleanup
- The mystery: something on this machine overwrites `scan-data.json` with output from an older scraper system. That's a separate diagnosis session.
- The actual `scrape_user_interviews.py` timeout fix (the file looks already improved; needs a credentialed test run, not in scope here).
