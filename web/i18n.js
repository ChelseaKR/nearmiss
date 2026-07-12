/* nearmiss shared web i18n loader — used by both index.html (app.js) and
 * submit.html (submit.js).
 *
 * The web UI's translations are single-sourced from the gettext PO catalogs:
 * tools/po2json.py compiles the `web.*` msgids into the committed, static
 * web/locales/<lang>.json catalogs this loader fetches. There is no build step
 * and no hand-maintained translation table in the JS — adding a locale means
 * committing one more locales/<lang>.json (and a language button), nothing else.
 *
 * Keys in the JSON are the full msgids (e.g. "web.app.title"). Each page creates
 * a namespaced view — NearmissI18n.create("web.app.") — so its call sites keep
 * using short keys, t("title"), unchanged. English is always loaded as the
 * fallback, so a key missing from a locale renders in English, never blank.
 */
(function () {
  "use strict";

  var FALLBACK = "en";

  function create(namespace) {
    // lang -> { shortKey: translation }, already stripped of the namespace.
    var catalogs = {};
    var current = FALLBACK;

    function ingest(lang, raw) {
      var out = {};
      Object.keys(raw || {}).forEach(function (fullKey) {
        if (fullKey.indexOf(namespace) === 0) {
          out[fullKey.slice(namespace.length)] = raw[fullKey];
        }
      });
      catalogs[lang] = out;
    }

    return {
      // Fetch and cache locales/<lang>.json. Resolves even on failure (an empty
      // catalog), so the caller transparently falls back to English.
      load: function (lang) {
        if (catalogs[lang]) return Promise.resolve();
        return fetch("locales/" + lang + ".json")
          .then(function (r) {
            if (!r.ok) throw new Error("HTTP " + r.status);
            return r.json();
          })
          .then(function (raw) {
            ingest(lang, raw);
          })
          .catch(function () {
            ingest(lang, {});
          });
      },
      setLang: function (lang) {
        current = lang;
      },
      lang: function () {
        return current;
      },
      loaded: function (lang) {
        return Object.prototype.hasOwnProperty.call(catalogs, lang);
      },
      // Look up a short key in the current locale, then English, then echo the
      // key so a stray call is visible rather than silently blank.
      t: function (key) {
        var active = catalogs[current];
        if (active && active[key] != null) return active[key];
        var fallback = catalogs[FALLBACK];
        return fallback && fallback[key] != null ? fallback[key] : key;
      },
    };
  }

  // Read a UI-language request from ?lang=xx (2–3 lowercase letters). Both pages
  // use this so a deep link renders the whole page in the requested locale.
  function langFromQuery(fallback) {
    try {
      var value = new URLSearchParams(window.location.search).get("lang");
      if (value && /^[a-z]{2,3}$/.test(value)) return value;
    } catch (e) {
      /* no URLSearchParams — use the fallback */
    }
    return fallback || FALLBACK;
  }

  window.NearmissI18n = { create: create, langFromQuery: langFromQuery, FALLBACK: FALLBACK };
})();
