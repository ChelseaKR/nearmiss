# 22. Google Analytics 4 on the public pages, guarded and disclosed

Date: 2026-09-17

## Status

Accepted

## Deciders

Owner decision (Chelsea Kelly-Reif), 2026-09-17

## Context

Until now the public site ran no analytics. On 2026-09-17 the owner decided that every public site in
the portfolio runs Google Analytics 4, with privacy pages and claims changed so nothing published
becomes false. The property was provisioned the same day: GA4 property 554897671, web stream
measurement ID `G-GSJMYXZTHM`, event data retention 14 months, Google signals disabled on the
property.

Three things about this repository shaped how:

- The site is hand-authored static HTML copied into an allowlisted artifact by
  `tools/build_site.py`, with no templating step. Anything every page shares has to be a shared file.
- The Conflict Atlas (`/fars/national/`) is bilingual, and its strings are single-sourced from the
  gettext catalogs (`src/nearmiss/web_i18n.py` → PO → `web/locales/*.json`). A hand-maintained
  translation table in JavaScript is exactly what that pipeline exists to prevent.
- The Atlas keeps its view state (year, selected and compared states, mode, view) in the query
  string, and `docs/COUNTY-DRILLDOWN-IMPLEMENTATION-PLAN.md` §21 and
  `docs/STATE-MAP-DRILLDOWN-PLAN.md` both ask that measurement not collect those selections.

## Decision

**One shared loader, `web/analytics.js`, holds the ID and every guard.** It is loaded synchronously
from `<head>` on the gateway, the Atlas (both routes), Studio, the sample dossier and the new
`/privacy/` page. It is not loaded on `404.html` or on the legacy `web/index.html` redirect stub,
which no reader reads. Set `MEASUREMENT_ID` to `""` and it loads nothing from Google anywhere.

**When nothing loads.** The loader returns before creating `dataLayer` or requesting gtag.js:

- off `nearmiss.chelseakr.com`, so local previews, the jsdom gates, CI, and the legacy
  `nearmiss.report` GitHub Pages host never contact Google;
- when `navigator.globalPrivacyControl === true`;
- when `navigator.doNotTrack`, `window.doNotTrack` or `navigator.msDoNotTrack` is `"1"` or `"yes"`;
- when `localStorage["nearmiss:analytics-opt-out"]` is `"1"`.

**How it is configured.** Consent Mode v2 defaults deny `ad_storage`, `ad_user_data` and
`ad_personalization` everywhere, and deny `analytics_storage` through `region` for the 27 EU states,
Iceland, Liechtenstein, Norway, the UK and Switzerland, granting it elsewhere. There is no consent
banner, so nothing updates those defaults; readers in those regions get no GA cookie and gtag sends
Google cookieless pings, which the owner accepted. The config sets `allow_google_signals: false` and
`allow_ad_personalization_signals: false`, and passes `page_location` as origin, path and `utm_*`
parameters only, and `page_referrer` as the referring origin (or, from this site, the path without
its query).

**Not a single-page app.** Every route is its own document, so gtag's page view on `config` is the
page view. The Atlas rewrites its query string with `pushState`/`replaceState` as a reader changes
the view; those are view changes on one page, not new pages, and this loader sends nothing for them (GA's own
history listener is a stream setting; see the owner step below).

**The footer opt-out.** Every page that loads GA carries a footer block: a sentence disclosing GA4
with a link to `/privacy/`, and a `hidden` "Opt out of analytics" / "Opt back in" `<button>` with a
`role="status"` line. `web/analytics.js` wires it on every host. The labels and the five status
messages are all in the page's markup; the script only chooses which to show with the `hidden`
attribute. On the Atlas each of those spans carries a `data-i18n` key (`web.coverage.analytics_*`,
nine keys, in `web_i18n.py` and both PO catalogs), so the Atlas's own renderer translates them and the
script holds no translation table. The opt-out also sets Google's `window["ga-disable-<ID>"]`.

**`/privacy/`** (`web/privacy.html`) is a new indexable page, in the sitemap, the build allowlist, the
Pages deploy verifier's critical paths, and all three accessibility gates. It is written in English
with a full Spanish section (`lang="es"`).

**No CSP change.** Neither host sends a Content-Security-Policy and no page carries a CSP meta tag;
`infra/aws-static-site.yml`'s response-headers policy sets none. A future CSP would need
`https://www.googletagmanager.com` in `script-src` and `https://*.google-analytics.com
https://*.analytics.google.com` in `connect-src` and `img-src`.

## Consequences

- Reading the site now sends Google a page view with the cut-down page address, the referring origin,
  browser and device data and an approximate location, and outside the EEA, UK and Switzerland sets
  the `_ga` cookies for up to two years. `/privacy/`, `README.md`, `docs/DPIA.md` and
  `docs/RESPONSIBLE-TECH-AUDITS.md` §C say so. Contributor reports, the published data files and a
  file inspected in Studio never reach GA.
- `tests/test_analytics.py` runs the loader in Node against stubbed browser objects and checks the
  built pages. Removing the hostname, GPC, DNT or opt-out guard, or sending the raw address, is
  caught by a negative control that first asserts its sabotage landed.
- **Owner steps in the GA4 web stream.** Enhanced measurement's "Page changes based on browser
  history events" fires on `pushState` and `replaceState` and reads the raw URL, even though this
  loader passes a scrubbed `page_location`. On the Atlas that would count every view change as a
  page view and send its selections. Turn it off on this stream. "Form interactions" would record
  Studio's forms by id, never their values; turn it off unless it is wanted.
