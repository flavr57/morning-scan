#!/usr/bin/env python3
"""
The Morning Pull — Generate the daily income-scan newspaper page.

Reads scan-data.json (pushed by the scraper) and produces index.html.
"""

import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

SEAFOAM = "#5BADA0"
SEAFOAM_TINT = "#D6EEEA"
PEACH = "#FAAF85"
PEACH_DARK = "#E8956A"
NAVY = "#1E3F6B"
INK = "#2A2018"
MUTED = "#9A8878"
FAINT = "#B0A090"
RULE = "#C8BAAE"
BODY_COLOR = "#7A6858"
ITEM_BORDER = "#E0D4C8"
LINEN = "#FAF7F2"

PLATFORM_CATEGORY = {
        "Respondent": "Research",
        "UserInterviews": "Research",
        "Contra": "Freelance",
        "Aquent": "Freelance",
        "Central Casting": "Acting",
        "Everyset": "Acting",
        "LinkedIn": "Jobs",
        "eBay": "Marketplace",
        "eBay Sold": "Marketplace",
        "eBay Messages": "Marketplace",
        "FB Marketplace": "Marketplace",
}

PLATFORM_LINK_VERB = {
        "Respondent": "Apply on",
        "UserInterviews": "Apply on",
        "Contra": "View on",
        "Aquent": "View on",
        "Central Casting": "View on",
        "Everyset": "Apply on",
        "LinkedIn": "View on",
        "eBay": "View on",
        "eBay Sold": "View on",
        "eBay Messages": "View on",
        "FB Marketplace": "View on",
}

HIGH_SIGNAL_PLATFORMS = {
        "Respondent", "UserInterviews", "Central Casting",
        "Everyset", "Contra", "Aquent",
}


def build_meta(item):
        parts = []
        if item.get("duration"):
                    parts.append(item["duration"])
                if item.get("location"):
                            parts.append(item["location"])
                        if item.get("date"):
                                    parts.append(item["date"])
                                if item.get("deadline"):
                                            try:
                                                            dl = datetime.fromisoformat(item["deadline"])
                                                            parts.append(f"Closes {dl.strftime('%b %-d')}")
except (ValueError, TypeError):
            pass
    if item.get("source"):
                parts.append(f"Via {item['source']}")
            if item.get("time_ago"):
                        parts.append(item["time_ago"])
                    return " \u00b7 ".join(parts)


def build_lead_body(item):
        parts = []
    if item.get("duration"):
                parts.append(item["duration"])
            if item.get("deadline"):
                        try:
                                        dl = datetime.fromisoformat(item["deadline"])
                                        parts.append(f"Closes {dl.strftime('%b %-d')}")
except (ValueError, TypeError):
            pass
    if item.get("location"):
                parts.append(item["location"])
            if item.get("date"):
                        parts.append(item["date"])
                    if item.get("alert"):
                                parts.append("Profile match")
                            return ". ".join(parts) + "." if parts else ""


def get_category(item):
        return item.get("category") or PLATFORM_CATEGORY.get(item.get("platform", ""), "")


def is_urgent(item):
        if item.get("urgent"):
                    return True
                deadline = item.get("deadline")
    if deadline:
                try:
                                dl = datetime.fromisoformat(deadline)
                                now = datetime.now(timezone.utc)
                                if (dl - now).total_seconds() < 24 * 3600:
                                                    return True
                except (ValueError, TypeError):
                                pass
                        return False


def score_item(item):
        s = 0
    platform = item.get("platform", "")
    if platform in HIGH_SIGNAL_PLATFORMS:
                s += 20
    pay_str = item.get("pay", "")
    if pay_str:
                try:
                                pay = int(pay_str.replace("$", "").replace(",", "").split("/")[0].split("-")[0].strip())
                                if pay >= 200: s += 30
elif pay >= 100: s += 20
elif pay >= 50: s += 10
except ValueError:
            s += 10
    dur_str = item.get("duration", "")
    if dur_str:
                try:
                                mins = int(dur_str.lower().replace("min", "").strip())
                                if mins <= 30: s += 15
elif mins <= 60: s += 5
except ValueError:
            pass
    if item.get("alert"):
                s += 25
    if item.get("flagged"):
                s += 15
    deadline = item.get("deadline")
    if deadline:
                try:
                                dl = datetime.fromisoformat(deadline)
                                now = datetime.now(timezone.utc)
                                hours_left = (dl - now).total_seconds() / 3600
                                if hours_left < 6: s += 30
elif hours_left < 24: s += 20
elif hours_left < 48: s += 10
except (ValueError, TypeError):
            pass
    return s


def render_lead_item(item):
        platform = escape(item.get("platform", ""))
    title = escape(item.get("title", "Untitled"))
    link = item.get("link", "#")
    pay = escape(item.get("pay", ""))
    category = escape(get_category(item))
    urgent = is_urgent(item)
    body = escape(build_lead_body(item))
    verb = PLATFORM_LINK_VERB.get(item.get("platform", ""), "View on")
    link_label = f"{verb} {platform}"
    pay_html = f'<p class="lead-pay">{pay}</p>' if pay else ""
    link_html = f'<a href="{link}" target="_blank" class="item-link">{link_label} &rarr;</a>'
    tag_html = ""
    if category:
                if urgent:
                                tag_html = f'<span class="urgent-tag">{category}</span>'
else:
            tag_html = f'<span class="lead-tag">{category}</span>'
    return f'''<div class="lead-item">
          <p class="lead-source">{platform}</p>
                <p class="lead-title">{title}</p>
                      {"<p class='lead-body'>" + body + "</p>" if body else ""}
                            {pay_html}
                                  {link_html}
                                        {tag_html}
                                            </div>'''


def render_scan_item(item):
        platform = item.get("platform", "")
    title = escape(item.get("title", "Untitled"))
    link = item.get("link", "#")
    pay = escape(item.get("pay", ""))
    meta = escape(build_meta(item))
    pay_html = f'<span class="item-pay">{pay}</span>' if pay else ""
    link_html = f'<a class="item-link" href="{link}" target="_blank">View &rarr;</a>' if not pay else ""
    return f'''<div class="item">
          <p class="item-title">{title}</p>
                {"<p class='item-meta'>" + meta + "</p>" if meta else ""}
                      {pay_html}
                            {link_html}
                                </div>'''


def render_platform_section(platform, items, error=None):
        header = f'<p class="col-section-name">{escape(platform)}</p>'
    if error:
                body = f'<p class="empty-state">Scan error: {escape(error[:80])}</p>'
elif not items:
        body = '<p class="empty-state">Nothing new today.</p>'
else:
        body = "".join(render_scan_item(it) for it in items)
    return f'<div class="col-section">{header}{body}</div>'


def generate_page(data):
        scan_time = data.get("generated", datetime.now().isoformat())
    all_items = data.get("items", [])
    errors = data.get("errors", {})
    location = data.get("location", "Hermosa Beach, CA")

    try:
                dt = datetime.fromisoformat(scan_time)
except (ValueError, TypeError):
        dt = datetime.now()

    date_display = dt.strftime("%A, %B %-d")
    time_display = dt.strftime("%-I:%M %p PT")

    scored = [(score_item(it), it) for it in all_items if not it.get("error")]
    scored.sort(key=lambda x: -x[0])
    top_items = [it for sc, it in scored if sc >= 15][:6]

    grouped = {}
    for it in all_items:
                if it.get("error"):
                                continue
                            p = it.get("platform", "Other")
        grouped.setdefault(p, []).append(it)

    ebay_combined = (
                grouped.pop("eBay", [])
                + grouped.pop("eBay Sold", [])
                + grouped.pop("eBay Messages", [])
    )
    fb = grouped.pop("FB Marketplace", [])
    grouped["eBay / Marketplace"] = ebay_combined + fb

    col1_platforms = ["Central Casting", "Everyset", "Aquent"]
    col2_platforms = ["Respondent", "UserInterviews", "Contra"]
    col3_platforms = ["LinkedIn", "eBay / Marketplace"]

    def render_column(platforms):
                sections = ""
        for p in platforms:
                        items = grouped.get(p, [])
                        error = errors.get(p)
                        sections += render_platform_section(p, items, error)
                    return sections

    if top_items:
                half = (len(top_items) + 1) // 2
        col1_leads = "".join(render_lead_item(it) for it in top_items[:half])
        col2_leads = "".join(render_lead_item(it) for it in top_items[half:])
        lead_html = f'''<div class="lead-grid">
              <div>{col1_leads}</div>
                    <div class="col-divider"></div>
                          <div>{col2_leads}</div>
                              </div>'''
else:
        lead_html = '<p class="empty-state" style="text-align:center;padding:1.5rem 0;">No high-priority items today. Check the full scan below.</p>'

    html = f'''<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>The Morning Pull &mdash; {date_display}</title>
    <style>
      * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ background: {LINEN}; font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', Arial, sans-serif; }}
          .wrap {{ max-width: 880px; margin: 0 auto; padding: 2.5rem 2rem; color: {INK}; }}
            .masthead {{ text-align: center; border-bottom: 2px solid {INK}; padding-bottom: 1rem; margin-bottom: 0.35rem; }}
              .masthead-eyebrow {{ font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: {SEAFOAM}; font-weight: 500; margin: 0 0 5px; }}
                .masthead-title {{ font-size: 36px; font-weight: 500; color: {INK}; margin: 0; letter-spacing: -0.01em; }}
                  .masthead-meta {{ font-size: 13px; color: {MUTED}; margin: 8px 0 0; display: flex; justify-content: center; }}
                    .masthead-meta span {{ border-right: 1px solid {RULE}; padding: 0 18px; }}
                      .masthead-meta span:last-child {{ border: none; }}
                        .rule {{ height: 1px; background: {INK}; margin: 0 0 1.25rem; }}
                          .rule-thin {{ height: 0.5px; background: {RULE}; margin: 1.25rem 0; }}
                            .above-fold-label {{ font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: {SEAFOAM}; font-weight: 500; border-bottom: 1.5px solid {SEAFOAM}; padding-bottom: 5px; margin-bottom: 1.1rem; }}
                              .sections-label {{ font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: {MUTED}; border-bottom: 0.5px solid {RULE}; padding-bottom: 5px; margin-bottom: 1.1rem; }}
                                .lead-source {{ font-size: 12px; letter-spacing: 0.1em; text-transform: uppercase; color: {SEAFOAM}; font-weight: 500; margin: 0 0 4px; }}
                                  .lead-grid {{ display: grid; grid-template-columns: 1fr 1px 1fr; gap: 0 1.5rem; margin-bottom: 1.25rem; }}
                                    .col-divider {{ background: {RULE}; }}
                                      .lead-item {{ padding: 0 0 1rem; }}
                                        .lead-item + .lead-item {{ border-top: 0.5px solid {RULE}; padding-top: 1rem; }}
                                          .lead-title {{ font-size: 19px; font-weight: 500; color: {INK}; margin: 0 0 5px; line-height: 1.35; }}
                                            .lead-body {{ font-size: 15px; color: {BODY_COLOR}; margin: 0; line-height: 1.5; }}
                                              .lead-pay {{ font-size: 15px; font-weight: 500; background: {PEACH}; color: #fff; display: inline-block; padding: 3px 10px; border-radius: 3px; margin-top: 6px; }}
                                                .lead-tag {{ font-size: 12px; background: {PEACH}; color: #fff; padding: 3px 9px; border-radius: 3px; margin-top: 5px; font-weight: 500; display: inline-block; }}
                                                  .urgent-tag {{ font-size: 12px; background: {PEACH_DARK}; color: #fff; padding: 3px 9px; border-radius: 3px; margin-top: 5px; font-weight: 500; display: inline-block; }}
                                                    a {{ color: {NAVY}; text-decoration: none; font-weight: 500; }}
                                                      a:hover {{ text-decoration: underline; }}
                                                        .item-link {{ font-size: 14px; color: {NAVY}; font-weight: 500; display: block; margin-top: 4px; }}
                                                          .body-grid {{ display: grid; grid-template-columns: 1fr 1px 1fr 1px 1fr; gap: 0 1.25rem; }}
                                                            .col-div {{ background: {RULE}; }}
                                                              .col-section {{ margin-bottom: 1.25rem; }}
                                                                .col-section-name {{ font-size: 12px; letter-spacing: 0.1em; text-transform: uppercase; color: {SEAFOAM}; font-weight: 500; margin: 0 0 0.6rem; border-bottom: 1px solid {SEAFOAM_TINT}; padding-bottom: 4px; }}
                                                                  .item {{ margin-bottom: 0.75rem; padding-bottom: 0.75rem; border-bottom: 0.5px solid {ITEM_BORDER}; }}
                                                                    .item:last-child {{ border-bottom: none; }}
                                                                      .item-title {{ font-size: 15px; font-weight: 500; color: {INK}; margin: 0 0 3px; line-height: 1.35; }}
                                                                        .item-meta {{ font-size: 13px; color: {MUTED}; margin: 0; }}
                                                                          .item-pay {{ font-size: 13px; font-weight: 500; background: {PEACH}; color: #fff; display: inline-block; padding: 2px 8px; border-radius: 3px; margin-top: 3px; }}
                                                                            .empty-state {{ font-size: 14px; color: {FAINT}; font-style: italic; }}
                                                                              @media (max-width: 720px) {{
                                                                                  .lead-grid {{ grid-template-columns: 1fr; gap: 0; }}
                                                                                      .col-divider {{ display: none; }}
                                                                                          .body-grid {{ grid-template-columns: 1fr; gap: 0; }}
                                                                                              .col-div {{ display: none; }}
                                                                                                  .masthead-title {{ font-size: 28px; }}
                                                                                                    }}
                                                                                                    </style>
                                                                                                    </head>
                                                                                                    <body>
                                                                                                    <div class="wrap">
                                                                                                      <div class="masthead">
                                                                                                          <p class="masthead-eyebrow">Daily income scan</p>
                                                                                                              <h1 class="masthead-title">The Morning Pull</h1>
                                                                                                                  <div class="masthead-meta">
                                                                                                                        <span>{date_display}</span>
                                                                                                                              <span>{location}</span>
                                                                                                                                    <span>Generated {time_display}</span>
                                                                                                                                        </div>
                                                                                                                                          </div>
                                                                                                                                            <div class="rule"></div>
                                                                                                                                              <p class="above-fold-label">Act on these today</p>
                                                                                                                                                {lead_html}
                                                                                                                                                  <div class="rule-thin"></div>
                                                                                                                                                    <p class="sections-label">Full scan</p>
                                                                                                                                                      <div class="body-grid">
                                                                                                                                                          <div class="col">
                                                                                                                                                                {render_column(col1_platforms)}
                                                                                                                                                                    </div>
                                                                                                                                                                        <div class="col-div"></div>
                                                                                                                                                                            <div class="col">
                                                                                                                                                                                  {render_column(col2_platforms)}
                                                                                                                                                                                      </div>
                                                                                                                                                                                          <div class="col-div"></div>
                                                                                                                                                                                              <div class="col">
                                                                                                                                                                                                    {render_column(col3_platforms)}
                                                                                                                                                                                                        </div>
                                                                                                                                                                                                          </div>
                                                                                                                                                                                                          </div>
                                                                                                                                                                                                          </body>
                                                                                                                                                                                                          </html>'''

    return html


def main():
        here = Path(__file__).resolve().parent
    data_path = here / "scan-data.json"
    if not data_path.exists():
                print("No scan-data.json found — generating empty page")
        data = {
                        "generated": datetime.now().isoformat(),
                        "items": [],
                        "errors": {},
                        "location": "Hermosa Beach, CA",
        }
else:
        data = json.loads(data_path.read_text())

    html = generate_page(data)
    out = here / "index.html"
    out.write_text(html)
    print(f"Generated index.html ({len(html):,} bytes)")


if __name__ == "__main__":
        main()
