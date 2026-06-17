/* nearmiss accessible map UI — framework-free, no dependencies.
 *
 * Loads the published open GeoJSON and renders BOTH a supplementary schematic
 * map and the authoritative, sortable data table. The table is the non-visual
 * equivalent: every finding is reachable without seeing the map, and risk and
 * significance are stated in text, never by color alone.
 */
(function () {
  "use strict";

  var DATA_URL = "../data/published/davis.geojson";

  function fmt(v) {
    return v === null || v === undefined ? "—" : Number(v).toFixed(2);
  }

  function text(el, value) {
    el.textContent = value;
    return el;
  }

  function cell(tag, value, className) {
    var el = document.createElement(tag);
    if (value !== undefined) el.textContent = value;
    if (className) el.className = className;
    return el;
  }

  function rowsFromGeojson(geojson) {
    return geojson.features.map(function (f) {
      var p = f.properties;
      p._coords = f.geometry.coordinates;
      return p;
    });
  }

  function renderTable(rows) {
    var body = document.getElementById("data-body");
    body.textContent = "";
    rows.forEach(function (p) {
      var tr = document.createElement("tr");
      if (p.significant) tr.className = "is-hotspot";

      tr.appendChild(cell("th", p.name || p.segment_id));
      tr.firstChild.setAttribute("scope", "row");

      tr.appendChild(cell("td", fmt(p.rate)));
      tr.appendChild(cell("td", fmt(p.rate_ci_low) + " – " + fmt(p.rate_ci_high)));
      tr.appendChild(cell("td", String(p.n)));

      var conf = cell("td", p.confidence_label.replace("_", " "));
      if (p.confidence_label !== "certain") conf.className = "uncertain";
      tr.appendChild(conf);

      var hot = document.createElement("td");
      if (p.significant) {
        var tag = cell("span", "★ Significant", "tag tag-hot");
        hot.appendChild(tag);
        hot.appendChild(
          text(document.createElement("span"), " (Gi* z=" + fmt(p.getis_ord_z) + ")")
        );
      } else {
        hot.textContent = p.getis_ord_z === null ? "—" : "z=" + fmt(p.getis_ord_z);
      }
      tr.appendChild(hot);

      tr.appendChild(cell("td", p.quality_flags.length ? p.quality_flags.join(", ") : "—"));
      body.appendChild(tr);
    });
    document.getElementById("data-caption").textContent =
      "Exposure-normalized hazard rates by segment (" + rows.length + " segments).";
  }

  function renderMap(rows) {
    var svg = document.getElementById("map");
    svg.textContent = "";
    var lons = [];
    var lats = [];
    rows.forEach(function (p) {
      p._coords.forEach(function (c) {
        lons.push(c[0]);
        lats.push(c[1]);
      });
    });
    var lonMin = Math.min.apply(null, lons),
      lonMax = Math.max.apply(null, lons);
    var latMin = Math.min.apply(null, lats),
      latMax = Math.max.apply(null, lats);
    var pad = 8;
    function px(lon) {
      return pad + ((lon - lonMin) / (lonMax - lonMin || 1)) * (100 - 2 * pad);
    }
    function py(lat) {
      return pad + (1 - (lat - latMin) / (latMax - latMin || 1)) * (100 - 2 * pad);
    }

    rows.forEach(function (p) {
      var pts = p._coords
        .map(function (c) {
          return px(c[0]).toFixed(2) + "," + py(c[1]).toFixed(2);
        })
        .join(" ");
      var line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      line.setAttribute("points", pts);
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", p.significant ? "#8a1c1c" : "#0b4f9c");
      line.setAttribute("stroke-width", p.significant ? "2.4" : "1.2");
      line.setAttribute("stroke-linecap", "round");
      if (p.significant) line.setAttribute("stroke-dasharray", "3 1.5"); // pattern, not color alone
      var title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent =
        (p.name || p.segment_id) +
        ": rate " +
        fmt(p.rate) +
        "/1000" +
        (p.significant ? " — significant hotspot" : "");
      line.appendChild(title);
      svg.appendChild(line);
    });
    document.getElementById("map-caption").textContent =
      rows.length + " street segments. Thicker, dashed lines are significant hotspots.";
  }

  function compare(key, dir) {
    return function (a, b) {
      var av = a[key],
        bv = b[key];
      if (typeof av === "string") return dir * av.localeCompare(bv);
      av = av === null || av === undefined ? -Infinity : av;
      bv = bv === null || bv === undefined ? -Infinity : bv;
      return dir * (av - bv);
    };
  }

  function wireSorting(rows) {
    var buttons = document.querySelectorAll("th button[data-sort]");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = btn.getAttribute("data-sort");
        var th = btn.closest("th");
        var asc = th.getAttribute("aria-sort") !== "ascending";
        document.querySelectorAll("th[aria-sort]").forEach(function (h) {
          h.removeAttribute("aria-sort");
        });
        th.setAttribute("aria-sort", asc ? "ascending" : "descending");
        rows.sort(compare(key, asc ? 1 : -1));
        renderTable(rows);
        renderMap(rows);
      });
    });
  }

  function fail(message) {
    document.getElementById("data-caption").textContent = message;
    document.getElementById("data-body").innerHTML =
      '<tr><td colspan="7">' + message + "</td></tr>";
    document.getElementById("map-caption").textContent = message;
  }

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (geojson) {
      var rows = rowsFromGeojson(geojson);
      rows.sort(compare("rate", -1)); // default: highest rate first
      renderTable(rows);
      renderMap(rows);
      wireSorting(rows);
    })
    .catch(function (e) {
      fail(
        "Could not load published data (" +
          e.message +
          "). Run `make publish`, then `nearmiss serve` and open /web/index.html."
      );
    });
})();
