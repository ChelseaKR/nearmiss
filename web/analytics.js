/* nearmiss — Google Analytics 4 on the public pages, and the footer's opt-out
 * (docs/adr/0022-google-analytics-4-on-the-public-pages.md).
 *
 * The owner decided on 2026-09-17 to run GA4 on every public site in the
 * portfolio, with the privacy copy changed to match. This file is the one place
 * that decision is implemented, and MEASUREMENT_ID below is the one place the
 * property's measurement ID lives. The ID is public (every page that loads GA
 * hands it to the browser), so it is committed as site configuration. Set it to
 * "" and this file loads nothing from Google on any page.
 *
 * Loaded synchronously from <head> on the gateway, the Conflict Atlas, Studio,
 * the sample dossier and /privacy/. It does two things:
 *
 * 1. Wires the footer's "Opt out of analytics" control on every host, so it
 *    can be exercised anywhere. The control's labels and status messages are
 *    in the page's own markup (on the bilingual Atlas they carry data-i18n keys
 *    from the gettext catalogs), and this only chooses which one to show: it
 *    holds no translation table of its own.
 * 2. Loads GA4, but only when every guard passes: the page is served from
 *    PRODUCTION_HOST (so no local preview, test run or CI job contacts Google),
 *    the browser sends neither Global Privacy Control nor Do Not Track, and the
 *    reader has not opted out. Consent Mode v2 defaults deny the three ad
 *    signals everywhere and deny analytics_storage in the EEA, the UK and
 *    Switzerland; Google signals and ad personalization are off.
 *
 * The page address GA receives is the origin and path plus any utm_* campaign
 * parameters. The Atlas keeps its view state (year, state, comparison states)
 * in the query string, and the county-drilldown plan asks that selections not
 * be collected, so the rest of the query string never leaves the browser. A
 * referrer from another site is sent as that site's origin only.
 */
(function () {
  "use strict";

  var MEASUREMENT_ID = "G-GSJMYXZTHM";
  var PRODUCTION_HOST = "nearmiss.chelseakr.com";
  // Renaming this key would silently opt every opted-out reader back in.
  var OPT_OUT_KEY = "nearmiss:analytics-opt-out";
  // The 27 EU member states, Iceland, Liechtenstein, Norway, the UK, Switzerland.
  var DENIED_REGIONS = [
    "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR", "HU", "IE",
    "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK", "SI", "ES", "SE",
    "IS", "LI", "NO", "GB", "CH"
  ];

  var w = window;
  var n = navigator;
  var d = document;

  var store = null;
  try {
    store = w.localStorage;
    store.getItem(OPT_OUT_KEY);
  } catch (_error) {
    store = null;
  }

  function optedOut() {
    try {
      return Boolean(store) && store.getItem(OPT_OUT_KEY) === "1";
    } catch (_error) {
      return false;
    }
  }

  var dnt = n.doNotTrack || w.doNotTrack || n.msDoNotTrack;
  var signal = n.globalPrivacyControl === true || dnt === "1" || dnt === "yes";

  function showOnly(box, attribute, value) {
    var nodes = box.querySelectorAll("[" + attribute + "]");
    for (var index = 0; index < nodes.length; index += 1) {
      nodes[index].hidden = nodes[index].getAttribute(attribute) !== value;
    }
  }

  function wireChoice() {
    var box = d.querySelector("[data-analytics-choice]");
    if (!box || !MEASUREMENT_ID) return;
    var button = box.querySelector("button");
    function render(message) {
      showOnly(box, "data-analytics-label", optedOut() ? "back-in" : "opt-out");
      button.hidden = signal || !store;
      showOnly(box, "data-analytics-message", message);
      box.hidden = false;
    }
    button.addEventListener("click", function () {
      try {
        if (optedOut()) {
          store.removeItem(OPT_OUT_KEY);
          w["ga-disable-" + MEASUREMENT_ID] = false;
          render("back-in");
        } else {
          store.setItem(OPT_OUT_KEY, "1");
          w["ga-disable-" + MEASUREMENT_ID] = true;
          render("opted-out");
        }
      } catch (_error) {
        store = null;
        render("no-storage");
      }
    });
    render(signal ? "signal" : !store ? "no-storage" : optedOut() ? "is-out" : "");
  }

  if (d.readyState === "loading") d.addEventListener("DOMContentLoaded", wireChoice);
  else wireChoice();

  function scrubbedLocation() {
    var kept = [];
    var query = w.location.search.replace(/^\?/, "");
    if (query) {
      query.split("&").forEach(function (pair) {
        if (/^utm_(?:source|medium|campaign|term|content|id)=/.test(pair)) kept.push(pair);
      });
    }
    return w.location.origin + w.location.pathname + (kept.length ? "?" + kept.join("&") : "");
  }

  function scrubbedReferrer() {
    var referrer = d.referrer;
    if (!referrer) return "";
    var match = /^(https?:\/\/[^/?#]+)([^?#]*)/.exec(referrer);
    if (!match) return "";
    return match[1] === w.location.origin ? match[1] + match[2] : match[1] + "/";
  }

  if (!MEASUREMENT_ID) return;
  if (w.location.hostname !== PRODUCTION_HOST) return;
  if (n.globalPrivacyControl === true) return;
  if (dnt === "1" || dnt === "yes") return;
  if (optedOut()) return;

  w.dataLayer = w.dataLayer || [];
  function gtag() {
    w.dataLayer.push(arguments);
  }
  gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "denied",
    region: DENIED_REGIONS
  });
  gtag("consent", "default", {
    ad_storage: "denied",
    ad_user_data: "denied",
    ad_personalization: "denied",
    analytics_storage: "granted"
  });
  gtag("js", new Date());
  gtag("config", MEASUREMENT_ID, {
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    page_location: scrubbedLocation(),
    page_referrer: scrubbedReferrer()
  });
  var script = d.createElement("script");
  script.async = true;
  script.src = "https://www.googletagmanager.com/gtag/js?id=" + MEASUREMENT_ID;
  d.head.appendChild(script);
})();
