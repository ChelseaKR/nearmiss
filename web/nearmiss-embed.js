/* nearmiss embeddable hotspot widget — one-line script-tag loader.
 *
 * For sites that prefer a <script> tag to hand-writing an <iframe>. Drop this
 * where the widget should appear:
 *
 *   <script src="https://nearmiss.report/nearmiss-embed.js"
 *           data-city="davis"
 *           data-height="380"
 *           async></script>
 *
 * It injects a sandboxed <iframe> pointing at embed.html with the given city
 * (or a validated data/published/<slug>.geojson path). The loader reduces either
 * selector to a filename slug before constructing the iframe URL. The iframe is
 * the security boundary: the host page and the
 * widget never share script context. Everything the widget shows is the same
 * open, aggregated published data the full site uses — no tracking, no cookies.
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

  var base = me.src.replace(/\/nearmiss-embed\.js(\?.*)?$/, "/");
  var city = me.getAttribute("data-city");
  var dataPath = me.getAttribute("data-data");
  var height = me.getAttribute("data-height") || "380";
  var title = me.getAttribute("data-title") || "nearmiss hazard hotspot map";

  var src = base + "embed.html";
  var qs = [];
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
  if (slug) qs.push("city=" + slug);
  if (qs.length) src += "?" + qs.join("&");

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
