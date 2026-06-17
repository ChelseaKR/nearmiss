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
      // Guard against missing/odd geometry rather than throwing and blanking the page.
      p._coords =
        f.geometry && Array.isArray(f.geometry.coordinates) ? f.geometry.coordinates : [];
      return p;
    });
  }

  function renderTable(rows) {
    var body = document.getElementById("data-body");
    body.textContent = "";
    rows.forEach(function (p) {
      var tr = document.createElement("tr");
      if (p.getis_ord_significant) tr.className = "is-hotspot";

      tr.appendChild(cell("th", p.name || p.segment_id));
      tr.firstChild.setAttribute("scope", "row");

      tr.appendChild(cell("td", fmt(p.rate)));
      tr.appendChild(cell("td", fmt(p.rate_ci_low) + " – " + fmt(p.rate_ci_high)));
      tr.appendChild(cell("td", String(p.n)));

      var conf = cell("td", String(p.confidence_label).replace(/_/g, " "));
      if (p.confidence_label !== "certain") conf.className = "uncertain";
      tr.appendChild(conf);

      var hot = document.createElement("td");
      if (p.getis_ord_significant) {
        hot.appendChild(cell("span", "★ Significant", "tag tag-hot"));
        hot.appendChild(text(document.createElement("span"), " (Gi* z=" + fmt(p.getis_ord_z) + ")"));
      } else {
        hot.textContent = p.getis_ord_z === null ? "—" : "z=" + fmt(p.getis_ord_z);
      }
      tr.appendChild(hot);

      tr.appendChild(cell("td", p.quality_flags.length ? p.quality_flags.join(", ") : "—"));
      body.appendChild(tr);
    });
    document.getElementById("data-caption").textContent =
      "Exposure-normalized hazard rates by segment (" + rows.length + " published segments).";
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
    if (!lons.length) {
      document.getElementById("map-caption").textContent = "No mappable segments.";
      return;
    }
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
      if (!p._coords.length) return;
      var pts = p._coords
        .map(function (c) {
          return px(c[0]).toFixed(2) + "," + py(c[1]).toFixed(2);
        })
        .join(" ");
      var line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
      line.setAttribute("points", pts);
      line.setAttribute("fill", "none");
      line.setAttribute("stroke", p.getis_ord_significant ? "#8a1c1c" : "#0b4f9c");
      line.setAttribute("stroke-width", p.getis_ord_significant ? "2.4" : "1.2");
      line.setAttribute("stroke-linecap", "round");
      if (p.getis_ord_significant) line.setAttribute("stroke-dasharray", "3 1.5"); // pattern, not color alone
      var title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent =
        (p.name || p.segment_id) +
        ": rate " +
        fmt(p.rate) +
        "/1000" +
        (p.getis_ord_significant ? " — significant hotspot" : "");
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
      if (typeof av === "string" || typeof bv === "string") {
        return dir * String(av).localeCompare(String(bv));
      }
      var an = av === null || av === undefined,
        bn = bv === null || bv === undefined;
      if (an && bn) return String(a.segment_id).localeCompare(String(b.segment_id));
      av = an ? -Infinity : av;
      bv = bn ? -Infinity : bv;
      if (av === bv) return String(a.segment_id).localeCompare(String(b.segment_id));
      return dir * (av - bv);
    };
  }

  function setSortState(key, asc) {
    document.querySelectorAll("th[aria-sort]").forEach(function (h) {
      h.removeAttribute("aria-sort");
    });
    var btn = document.querySelector('th button[data-sort="' + key + '"]');
    if (btn) btn.closest("th").setAttribute("aria-sort", asc ? "ascending" : "descending");
  }

  function wireSorting(rows) {
    document.querySelectorAll("th button[data-sort]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = btn.getAttribute("data-sort");
        var asc = btn.closest("th").getAttribute("aria-sort") !== "ascending";
        setSortState(key, asc);
        rows.sort(compare(key, asc ? 1 : -1));
        renderTable(rows);
        renderMap(rows);
        var status = document.getElementById("sort-status");
        if (status) {
          status.textContent =
            "Table sorted by " +
            btn.textContent.trim() +
            ", " +
            (asc ? "ascending" : "descending") +
            ".";
        }
      });
    });
  }

  function fail(message) {
    var body = document.getElementById("data-body");
    body.textContent = "";
    var tr = document.createElement("tr");
    var td = document.createElement("td");
    td.setAttribute("colspan", "7");
    td.textContent = message; // textContent, never innerHTML (no injection sink)
    tr.appendChild(td);
    body.appendChild(tr);
    document.getElementById("data-caption").textContent = message;
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
      setSortState("rate", false); // reflect the initial descending order in aria-sort
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
