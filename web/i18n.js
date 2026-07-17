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
  var SUPPORTED = { en: true, es: true };

  function localeRoot() {
    var script = document.currentScript;
    if (!script || !script.src) {
      // jsdom and other outside-only harnesses do not expose currentScript.
      // Fall back to the declared loader element rather than the page route.
      var scripts = document.getElementsByTagName("script");
      for (var index = scripts.length - 1; index >= 0; index -= 1) {
        if (/(^|\/)i18n\.js(?:[?#].*)?$/.test(scripts[index].src || "")) {
          script = scripts[index];
          break;
        }
      }
    }
    try {
      var scriptUrl =
        script && script.src
          ? script.src
          : new URL("/web/i18n.js", window.location.href).href;
      return new URL("locales/", scriptUrl).href;
    } catch (_error) {
      return "/web/locales/";
    }
  }

  var LOCALE_ROOT = localeRoot();

  function isSupported(lang) {
    return Object.prototype.hasOwnProperty.call(SUPPORTED, lang);
  }

  function create(namespace) {
    // Array-backed catalogs avoid treating locale names or catalog msgids as
    // JavaScript object properties. Both arrive through fetched JSON, so keeping
    // them as values also makes prototype-key injection impossible.
    var catalogs = [];
    var current = FALLBACK;

    function catalogFor(lang) {
      for (var index = 0; index < catalogs.length; index += 1) {
        if (catalogs[index].lang === lang) return catalogs[index].messages;
      }
      return null;
    }

    function messageFrom(messages, key) {
      if (!messages) return null;
      for (var index = 0; index < messages.length; index += 1) {
        if (messages[index].key === key) return messages[index].value;
      }
      return null;
    }

    function ingest(lang, raw) {
      if (!isSupported(lang)) return;
      var messages = [];
      Object.keys(raw || {}).forEach(function (fullKey) {
        if (fullKey.indexOf(namespace) === 0 && typeof raw[fullKey] === "string") {
          messages.push({ key: fullKey.slice(namespace.length), value: raw[fullKey] });
        }
      });
      catalogs = catalogs.filter(function (catalog) {
        return catalog.lang !== lang;
      });
      catalogs.push({ lang: lang, messages: messages });
    }

    return {
      // Fetch and cache locales/<lang>.json. Resolves even on failure (an empty
      // catalog), so the caller transparently falls back to English.
      load: function (lang) {
        if (!isSupported(lang) || catalogFor(lang)) return Promise.resolve();
        return fetch(LOCALE_ROOT + lang + ".json")
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
        current = isSupported(lang) ? lang : FALLBACK;
      },
      lang: function () {
        return current;
      },
      loaded: function (lang) {
        return Boolean(catalogFor(lang));
      },
      // Look up a short key in the current locale, then English, then echo the
      // key so a stray call is visible rather than silently blank.
      t: function (key) {
        var active = messageFrom(catalogFor(current), key);
        if (active !== null) return active;
        var fallback = messageFrom(catalogFor(FALLBACK), key);
        return fallback !== null ? fallback : key;
      },
    };
  }

  // Read a UI-language request from ?lang=xx, but only select a locale this
  // deployment actually ships. This keeps English fallback content labeled
  // lang="en" instead of, for example, lang="ar" when no Arabic catalog exists.
  function langFromQuery(fallback) {
    var safeFallback = isSupported(fallback) ? fallback : FALLBACK;
    try {
      var value = new URLSearchParams(window.location.search).get("lang");
      if (value && isSupported(value)) return value;
    } catch (e) {
      /* no URLSearchParams — use the fallback */
    }
    return safeFallback;
  }

  window.NearmissI18n = { create: create, langFromQuery: langFromQuery, FALLBACK: FALLBACK };
})();
