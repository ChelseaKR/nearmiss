/* nearmiss embeddable hotspot widget — self-contained, framework-free (vendored
 * Leaflet only). Drop it into any advocacy site via an <iframe> (see
 * web/nearmiss-embed.js for a one-line script-tag loader).
 *
 * It renders ONE map: exposure-normalized hazard rates, with statistically
 * significant Getis-Ord hotspots dashed and labeled — the honest "where the
 * danger actually is" view. Magnitude is encoded by line thickness and
 * significance by a dashed pattern AND text, never by color alone, and a text
 * list of the significant hotspots is rendered as the non-visual equivalent.
 *
 * Source-agnostic within the public artifact directory: ?city=<slug> or
 * ?data=../data/published/<slug>.geojson selects a published dataset. Query
 * input cannot choose another origin or directory. The provenance line and the
 * "view full" link are driven by the dataset's own embedded metadata.
 */
(function () {
  "use strict";

  function hasEncodedDatasetSelector() {
    return window.location.search
      .replace(/^\?/, "")
      .split("&")
      .some(function (part) {
        var separator = part.indexOf("=");
        var rawName = separator === -1 ? part : part.slice(0, separator);
        var rawValue = separator === -1 ? "" : part.slice(separator + 1);
        var name;
        try {
          name = decodeURIComponent(rawName.replace(/\+/g, " "));
        } catch (_error) {
          return false;
        }
        return (name === "data" || name === "city") && /%/.test(rawName + rawValue);
      });
  }

  function resolveDatasetSlug() {
    try {
      var params = new URLSearchParams(window.location.search);
      var dataValues = params.getAll("data");
      var cityValues = params.getAll("city");
      if (
        dataValues.length > 1 ||
        cityValues.length > 1 ||
        (dataValues.length && cityValues.length) ||
        hasEncodedDatasetSelector()
      ) {
        return "davis";
      }
      var data = dataValues[0] || "";
      var match = /^(?:\.\.\/|\/)?data\/published\/([a-z0-9][a-z0-9_-]*)\.geojson$/i.exec(data);
      if (match) return match[1].toLowerCase();
      var city = cityValues[0] || "";
      if (/^[a-z0-9][a-z0-9_-]*$/i.test(city)) return city.toLowerCase();
    } catch (e) {
      /* old browser — use the default */
    }
    return "davis";
  }

  var DATASET_SLUG = resolveDatasetSlug();
  var DATA_URL = "../data/published/" + DATASET_SLUG + ".geojson";

  var mapEl = document.getElementById("embed-map");
  var captionEl = document.getElementById("embed-caption");
  var listEl = document.getElementById("embed-hotspots");
  var sourceEl = document.getElementById("embed-source");

  function widthFor(value, max, lo, hi) {
    if (!max || max <= 0) return lo;
    return lo + (hi - lo) * Math.sqrt(Math.max(0, value) / max);
  }

  function featureLatLngs(geometry) {
    // GeoJSON is [lon, lat]; Leaflet wants [lat, lon].
    return (geometry.coordinates || []).map(function (c) {
      return [c[1], c[0]];
    });
  }

  function render(geojson) {
    var features = (geojson.features || []).filter(function (f) {
      return f.geometry && f.geometry.type === "LineString";
    });
    var meta = geojson.metadata || {};
    if (sourceEl) {
      var unit = meta.exposure_unit ? " per " + meta.exposure_unit : "";
      sourceEl.textContent =
        (meta.city ? meta.city + " · " : "") +
        "exposure-normalized hazard rate" +
        unit +
        " · open data";
    }
    var full = document.getElementById("embed-fulllink");
    if (full && meta.city) full.setAttribute("href", "https://nearmiss.report");

    var maxRate = features.reduce(function (m, f) {
      return Math.max(m, f.properties.rate || 0);
    }, 0);

    if (!window.L) {
      captionEl.textContent = "Map library unavailable; see the hotspot list below.";
    } else {
      var map = window.L.map(mapEl, { scrollWheelZoom: false, attributionControl: true });
      window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(map);

      var bounds = window.L.latLngBounds([]);
      features.forEach(function (f) {
        var p = f.properties;
        var sig = !!p.getis_ord_significant;
        var latlngs = featureLatLngs(f.geometry);
        var line = window.L.polyline(latlngs, {
          color: sig ? "#8a1c1c" : "#0b4f9c",
          weight: widthFor(p.rate || 0, maxRate, sig ? 3 : 2, 11),
          opacity: 0.9,
          dashArray: sig ? "6 4" : null,
          lineCap: "round",
        }).addTo(map);
        var ci =
          p.rate_ci_low != null && p.rate_ci_high != null
            ? " (95% CI " + p.rate_ci_low + "–" + p.rate_ci_high + ")"
            : "";
        var tooltipContent = document.createElement("span");
        tooltipContent.textContent =
          (p.name || p.segment_id) +
          (sig ? " — ★ significant hotspot" : "") +
          "\nrate " +
          (p.rate == null ? "n/a" : p.rate) +
          ci +
          ", n=" +
          p.n;
        line.bindTooltip(tooltipContent, { sticky: true });
        latlngs.forEach(function (ll) {
          bounds.extend(ll);
        });
      });
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [14, 14] });
    }

    // Text equivalent: the significant hotspots, in words.
    var hotspots = features
      .filter(function (f) {
        return f.properties.getis_ord_significant;
      })
      .sort(function (a, b) {
        return (b.properties.rate || 0) - (a.properties.rate || 0);
      });
    listEl.textContent = "";
    if (hotspots.length) {
      hotspots.forEach(function (f) {
        var p = f.properties;
        var li = document.createElement("li");
        li.textContent =
          "★ " +
          (p.name || p.segment_id) +
          " — rate " +
          (p.rate == null ? "n/a" : p.rate) +
          " (95% CI " +
          p.rate_ci_low +
          "–" +
          p.rate_ci_high +
          ", n=" +
          p.n +
          ")";
        listEl.appendChild(li);
      });
      captionEl.textContent =
        hotspots.length +
        " statistically significant hotspot(s) — hotter than exposure and chance explain.";
    } else {
      var li = document.createElement("li");
      li.textContent = "No statistically significant hotspots in this dataset.";
      listEl.appendChild(li);
      captionEl.textContent =
        "No statistically significant hotspots: no street is hotter than exposure and chance explain.";
    }
  }

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(render)
    .catch(function () {
      captionEl.textContent = "Could not load the hotspot dataset.";
    });
})();
