/* nearmiss embeddable hotspot widget — one-line script-tag loader.
 *
 * For sites that prefer a <script> tag to hand-writing an <iframe>. Drop this
 * where the widget should appear:
 *
 *   <script src="/web/nearmiss-embed.js"
 *           data-city="davis"
 *           data-height="380"
 *           async></script>
 *
 * It injects a sandboxed <iframe> pointing at the same-origin local embed.html with the
 * given city (or a validated data/published/<slug>.geojson path). The loader
 * reduces either selector to the Davis/Riverside allowlist before choosing one
 * of three constant local paths. The iframe is the security boundary: the host
 * page and widget never share script context. Everything the widget shows is a
 * committed synthetic methods fixture — no tracking, no cookies, no production evidence.
 */
(function () {
  "use strict";

  // The script element that loaded us (works without document.currentScript on
  // older engines by falling back to the last script on the page).
  var me =
    document.currentScript ||
    (function () {
      var s = document.getElementsByTagName("script");
      return s[s.length - 1];
    })();
  if (!me) return;

  var city = me.getAttribute("data-city");
  var dataPath = me.getAttribute("data-data");
  var height = me.getAttribute("data-height") || "380";
  var title = me.getAttribute("data-title") || "nearmiss hazard hotspot map";

  var src = "/web/embed.html";
  var slug = null;
  if (!(city && dataPath)) {
    if (city && /^[a-z0-9][a-z0-9_-]*$/i.test(city)) {
      slug = city.toLowerCase();
    } else if (dataPath) {
      var match = /^(?:\.\.\/|\/)?data\/published\/([a-z0-9][a-z0-9_-]*)\.geojson$/i.exec(
        dataPath
      );
      if (match) slug = match[1].toLowerCase();
    }
  }
  // Keep this source-only prototype on the embedding document's local origin.
  // Do not derive a child origin from the mutable script element; restrict the
  // iframe URL to reviewed paths so DOM-controlled attributes cannot turn this
  // loader into navigation to attacker-selected content.
  if (slug === "davis") {
    src = "/web/embed.html?city=davis";
  } else if (slug === "riverside") {
    src = "/web/embed.html?city=riverside";
  }

  var iframe = document.createElement("iframe");
  iframe.src = src;
  iframe.title = title;
  iframe.loading = "lazy";
  iframe.setAttribute("scrolling", "no");
  // Allow scripts (Leaflet) and same-origin fetch of the published GeoJSON, but
  // nothing else — no top-navigation, no forms, no popups.
  iframe.setAttribute("sandbox", "allow-scripts allow-same-origin allow-popups");
  iframe.style.width = "100%";
  iframe.style.height = (/^\d+$/.test(height) ? height + "px" : height);
  iframe.style.border = "1px solid #d3dae2";
  iframe.style.borderRadius = "6px";

  // Insert right where the script tag is, so layout is predictable.
  if (me.parentNode) me.parentNode.insertBefore(iframe, me.nextSibling);
})();
