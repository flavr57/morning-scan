# Secrets — what Jason needs to add

The daily scraper runs as a GitHub Actions cron job. The scrapers that
require login pull credentials and session cookies from this repo's
Actions secrets. None of these are stored in the repo itself.

Add each one at:
**Repo > Settings > Secrets and variables > Actions > New repository secret**

## Required secrets

| Name                          | Type     | Value                                                |
| ----------------------------- | -------- | ---------------------------------------------------- |
| `RESPONDENT_SESSION_COOKIE`   | cookie   | **Required for production.** Respondent put Google reCAPTCHA Enterprise on the login form, so email/password cannot work from GitHub Actions IPs. Grab via "How to grab a session cookie" below against `app.respondent.io`. |
| `RESPONDENT_EMAIL`            | password | Optional. Used only locally; the cron runner can't get past the captcha. Leave set if you already added it. |
| `RESPONDENT_PASS`             | password | Optional. Same as above.                             |
| `USERINTERVIEWS_SESSION_COOKIE`| cookie  | **Recommended** if your UserInterviews account uses Google SSO (no password set) or if the password login keeps bouncing to OAuth. Grab against `www.userinterviews.com`. |
| `USERINTERVIEWS_EMAIL`        | password | Optional, used only when no cookie is set. Won't work for Google-SSO-only accounts. |
| `USERINTERVIEWS_PASS`         | password | Optional, same as above.                             |
| `EBAY_SESSION_COOKIE`         | cookie   | See "How to grab a session cookie" below             |
| `FB_SESSION_COOKIE`           | cookie   | Optional — FB Marketplace ships as a stub; only fill if you want to revisit it |

The scraper degrades gracefully. If a secret is missing the orchestrator
records that platform as ok / 0 items and moves on. One missing secret
will not break any other platform.

## How to grab a session cookie

1. Open eBay in Chrome (or any Chromium browser).
2. Sign in.
3. Open DevTools (Cmd+Option+I on Mac, F12 on Windows).
4. Go to the **Application** tab > **Storage** > **Cookies** > `https://www.ebay.com`.
5. Select all rows. Right-click > Copy. The format you want is one long
   string of `name=value; name=value; name=value` pairs.
6. If the row-copy gives you a different format, use this trick instead:
   in the DevTools **Console** tab, run `document.cookie` and copy the
   string it prints — that's already in the right format.
7. Paste that whole string as the value of `EBAY_SESSION_COOKIE` in
   GitHub Actions secrets.

Same procedure for the other cookie secrets:
- `RESPONDENT_SESSION_COOKIE` against `https://app.respondent.io` after signing in
- `USERINTERVIEWS_SESSION_COOKIE` against `https://www.userinterviews.com` after signing in
- `FB_SESSION_COOKIE` against `https://www.facebook.com`, if you decide to enable it

## When to refresh

Cookies expire silently. You'll know it's time to refresh when the
bookmarked page shows that platform with `0 items` for several days in
a row, or the workflow logs show "session cookie expired or invalid"
for that platform.

Refresh = repeat the steps above and update the secret value. Old
secrets are overwritten; nothing else needs to change.

Realistically expect:
- eBay cookies last weeks to months unless you sign out everywhere.
- Facebook cookies are shorter-lived, especially after security events.

## Email/password secrets

`RESPONDENT_*` and `USERINTERVIEWS_*` secrets do not need refreshing
unless you change those passwords.

If either site triggers a CAPTCHA or 2FA challenge during automated
login, the scraper logs it and returns 0 items for that day. You'll
see that platform stuck at 0 in the workflow logs. There is no fully
automatic fix — sites add CAPTCHA when they don't trust the request.
Workarounds (in order of preference):
1. Wait a day. CAPTCHA is sometimes transient.
2. Switch to the cookie-based pattern (same as eBay) for that platform.
3. Live with that platform showing 0 until you can sign in manually
   and re-establish trust.
