/* nearmiss accessible map UI — framework-free except a locally vendored Leaflet.
 *
 * Loads the published open GeoJSON and renders TWO real (OpenStreetMap-backed)
 * maps of the SAME reports — raw counts on the left, exposure-normalized rate on
 * the right — so the contrast is the point: the busiest street recedes and the
 * statistically real hotspot emerges. The sortable data table below is the
 * authoritative, non-visual equivalent: every finding is reachable without
 * seeing the maps, and risk and significance are stated in text, never by color
 * alone (magnitude is also encoded by line thickness; significance by a dashed
 * pattern and a text label). The chrome is bilingual (English/Spanish).
 */
(function () {
  "use strict";

  // Which published dataset to load. Defaults to the committed synthetic demo,
  // but the page is source-agnostic: ?city=<slug> loads ../data/published/<slug>.geojson
  // and ?data=<path> loads an explicit file, so a real city (once published into
  // data/published/) goes live by URL with no code change. The provenance banner
  // and title below are driven by the dataset's own embedded metadata, so they
  // are always truthful about what is actually loaded.
  function resolveDataUrl() {
    try {
      var params = new URLSearchParams(window.location.search);
      var data = params.get("data");
      // Only same-origin relative paths (no scheme, no protocol-relative URL).
      if (data && !/^[a-z]+:|^\/\//i.test(data)) return data;
      var city = params.get("city");
      if (city && /^[a-z0-9_-]+$/i.test(city)) return "../data/published/" + city + ".geojson";
    } catch (e) {
      /* no URLSearchParams (very old browser) — fall through to the default */
    }
    return "../data/published/davis.geojson";
  }

  var DATA_URL = resolveDataUrl();
  // Initial UI language: ?lang=xx if present (deep-linkable), else English. The
  // language buttons switch it at runtime.
  var lang = window.NearmissI18n.langFromQuery("en");
  var rows = [];
  var filterText = ""; // R21 table name filter (lowercased)
  var meta = {}; // embedded dataset metadata (city, dataset_note, exposure_unit, …)
  var maps = {}; // { reports: L.Map, rate: L.Map }
  var dataLayers = { reports: [], rate: [] };

  // Web UI translations are single-sourced from the gettext PO catalogs and
  // compiled to web/locales/<lang>.json by tools/po2json.py; the shared loader
  // in web/i18n.js fetches them. app.js keeps using short keys — t("title") —
  // via the "web.app." namespace, with English always loaded as the fallback.
  var i18n = window.NearmissI18n.create("web.app.");

  function t(key) {
    return i18n.t(key);
  }
  function tpl(s, obj) {
    return s.replace(/\{(\w+)\}/g, function (_, k) {
      return obj[k];
    });
  }
  function fmt(v) {
    return v === null || v === undefined ? t("none") : Number(v).toFixed(2);
  }
  function hasRate(p) {
    return p.rate !== null && p.rate !== undefined;
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
      p._coords = f.geometry && Array.isArray(f.geometry.coordinates) ? f.geometry.coordinates : [];
      return p;
    });
  }

  function matchesFilter(p) {
    if (!filterText) return true;
    return String(p.name || p.segment_id).toLowerCase().indexOf(filterText) !== -1;
  }

  function renderTable() {
    var body = document.getElementById("data-body");
    body.textContent = "";
    // The table is the authoritative DATA view: only analyzed segments (those with
    // an exposure denominator and a rate). The maps' gray context streets carry no
    // data, so they are not table rows.
    var allData = rows.filter(hasRate);
    var dataRows = allData.filter(matchesFilter);
    dataRows.forEach(function (p) {
      var tr = document.createElement("tr");
      if (p.getis_ord_significant) tr.className = "is-hotspot";

      var th = cell("th", p.name || p.segment_id);
      th.setAttribute("scope", "row");
      th.id = "seg-" + p.segment_id; // R20: stable deep-link / anchor target
      tr.appendChild(th);

      tr.appendChild(cell("td", fmt(p.rate)));
      tr.appendChild(cell("td", fmt(p.rate_ci_low) + " – " + fmt(p.rate_ci_high)));
      tr.appendChild(cell("td", String(p.n)));

      // R24: the reported hazard mix, where it survives small-sample suppression.
      var hb = p.hazard_breakdown || {};
      var hbKeys = Object.keys(hb).sort(function (a, b) {
        return hb[b] - hb[a];
      });
      var hzText = hbKeys.length
        ? hbKeys
            .map(function (k) {
              return (t("hz_" + k) || k) + " (" + hb[k] + ")";
            })
            .join(", ")
        : t("none");
      tr.appendChild(cell("td", hzText));

      var conf = cell("td", t("conf_" + p.confidence_label) || p.confidence_label);
      if (p.confidence_label !== "certain") conf.className = "uncertain";
      tr.appendChild(conf);

      var hot = document.createElement("td");
      if (p.getis_ord_significant) {
        hot.appendChild(cell("span", t("sig"), "tag tag-hot"));
        hot.appendChild(document.createTextNode(" (Gi* z=" + fmt(p.getis_ord_z) + ")"));
      } else {
        hot.textContent = p.getis_ord_z === null ? t("none") : "z=" + fmt(p.getis_ord_z);
      }
      tr.appendChild(hot);

      var flags = (p.quality_flags || []).map(function (fl) {
        return t("flag_" + fl) || fl;
      });
      // R6: a modeled (not measured) exposure denominator is surfaced as a flag,
      // never silently treated as a real count.
      if (p.exposure_source && /modeled/i.test(p.exposure_source)) {
        flags.push(t("flag_modeled_exposure"));
      }
      tr.appendChild(cell("td", flags.length ? flags.join(", ") : t("none")));
      body.appendChild(tr);
    });
    var caption = document.getElementById("data-caption");
    if (dataRows.length === allData.length) {
      caption.textContent = tpl(t("caption"), { n: allData.length });
    } else {
      caption.textContent = tpl(t("captionFiltered"), { shown: dataRows.length, n: allData.length });
    }
    var status = document.getElementById("filter-status");
    if (status) {
      status.textContent = filterText
        ? tpl(t("filterStatus"), { shown: dataRows.length, n: allData.length })
        : "";
    }
  }

  // ---- Maps -----------------------------------------------------------------

  function leafletAvailable() {
    return typeof window.L !== "undefined";
  }

  // Interpolate between two "rrggbb" hex colors; t in [0,1].
  function lerpColor(aHex, bHex, frac) {
    var a = aHex.match(/\w\w/g).map(function (h) {
      return parseInt(h, 16);
    });
    var b = bHex.match(/\w\w/g).map(function (h) {
      return parseInt(h, 16);
    });
    var c = a.map(function (av, i) {
      return Math.round(av + (b[i] - av) * frac);
    });
    return "rgb(" + c.join(",") + ")";
  }

  // Square-root scaling so magnitude is perceptually fair, not dominated by outliers.
  function widthFor(value, max, lo, hi) {
    var frac = max > 0 ? Math.sqrt(Math.max(0, value) / max) : 0;
    return lo + (hi - lo) * frac;
  }

  function toLatLngs(coords) {
    return coords.map(function (c) {
      return [c[1], c[0]];
    });
  }

  function initMaps() {
    if (maps.reports) return true;
    if (!leafletAvailable()) return false;
    ["reports", "rate"].forEach(function (which) {
      var m = window.L.map("map-" + which, {
        zoomControl: true,
        // Don't hijack page scrolling; users zoom with the +/- control or keyboard.
        scrollWheelZoom: false,
        attributionControl: true,
      });
      window.L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
      }).addTo(m);
      maps[which] = m;
    });
    syncMaps(maps.reports, maps.rate);
    return true;
  }

  // Keep the two maps showing the same area so the comparison is honest.
  function syncMaps(a, b) {
    var syncing = false;
    function link(src, dst) {
      src.on("move zoom", function () {
        if (syncing) return;
        syncing = true;
        dst.setView(src.getCenter(), src.getZoom(), { animate: false });
        syncing = false;
      });
    }
    link(a, b);
    link(b, a);
  }

  function clearLayers() {
    ["reports", "rate"].forEach(function (which) {
      dataLayers[which].forEach(function (l) {
        maps[which].removeLayer(l);
      });
      dataLayers[which] = [];
    });
  }

  // Bind ONE tooltip per polyline: a permanent call-out label for the protagonist
  // segments, or a sticky hover tooltip for the rest. (Binding both to the same
  // layer collides, so they are mutually exclusive.)
  function addSegment(which, latlngs, style, tip, label) {
    var line = window.L.polyline(latlngs, style);
    if (label) {
      line.bindTooltip(label, {
        permanent: true,
        direction: "top",
        className: "map-label",
        opacity: 1,
      });
    } else if (tip) {
      line.bindTooltip(tip, { sticky: true });
    }
    line.addTo(maps[which]);
    if (label) line.openTooltip();
    dataLayers[which].push(line);
  }

  function contextStyle() {
    return { color: "#c3ccd6", weight: 1, opacity: 0.85, lineCap: "round" };
  }

  function renderMaps() {
    var capR = document.getElementById("cap-reports");
    var capRate = document.getElementById("cap-rate");
    if (!initMaps()) {
      capR.textContent = t("mapNoLeaflet");
      capRate.textContent = t("mapNoLeaflet");
      return;
    }
    clearLayers();

    var dataRows = rows.filter(hasRate);
    if (!dataRows.length) {
      capR.textContent = t("mapEmpty");
      capRate.textContent = t("mapEmpty");
      return;
    }

    var maxReports = Math.max.apply(
      null,
      dataRows.map(function (p) {
        return p.report_count || 0;
      })
    );
    var maxRate = Math.max.apply(
      null,
      dataRows.map(function (p) {
        return p.rate || 0;
      })
    );
    // Call out the protagonists: the single most-reported street (the decoy) and
    // every statistically significant hotspot (what the rate map actually surfaces).
    var peak = dataRows.reduce(function (a, b) {
      return (b.report_count || 0) > (a.report_count || 0) ? b : a;
    });
    var hotspots = dataRows.filter(function (p) {
      return p.getis_ord_significant;
    });

    var bounds = [];
    rows.forEach(function (p) {
      if (!p._coords.length) return;
      var latlngs = toLatLngs(p._coords);
      latlngs.forEach(function (ll) {
        bounds.push(ll);
      });
      if (!hasRate(p)) {
        addSegment("reports", latlngs, contextStyle());
        addSegment("rate", latlngs, contextStyle());
        return;
      }

      // Left map: raw report count. Magnitude in BOTH width and a blue ramp.
      var rc = p.report_count || 0;
      addSegment(
        "reports",
        latlngs,
        {
          color: lerpColor("9ecae1", "08306b", maxReports > 0 ? rc / maxReports : 0),
          weight: widthFor(rc, maxReports, 2, 11),
          opacity: 0.95,
          lineCap: "round",
        },
        tpl(t("tipReports"), { name: p.name || p.segment_id, count: rc }),
        p.segment_id === peak.segment_id
          ? tpl(t("lblBusiest"), { name: p.name || p.segment_id, count: rc })
          : null
      );

      // Right map: exposure-normalized rate. Significant hotspots are red + dashed
      // (a pattern, not color alone) + permanently labeled.
      var sig = p.getis_ord_significant;
      addSegment(
        "rate",
        latlngs,
        {
          color: sig ? "#8a1c1c" : "#0b4f9c",
          weight: widthFor(p.rate || 0, maxRate, sig ? 3 : 2, 11),
          opacity: 0.95,
          lineCap: "round",
          dashArray: sig ? "6 4" : null,
        },
        tpl(t("tipRate"), { name: p.name || p.segment_id, rate: fmt(p.rate) }) +
          (sig ? t("sigShort") : ""),
        sig ? tpl(t("lblHotspot"), { name: p.name || p.segment_id, rate: fmt(p.rate) }) : null
      );
    });

    if (bounds.length) {
      maps.reports.fitBounds(bounds, { padding: [18, 18] });
      maps.rate.fitBounds(bounds, { padding: [18, 18] });
    }

    capR.textContent = tpl(t("capReports"), {
      n: rows.length,
      peak: peak.name || peak.segment_id,
    });
    capRate.textContent = hotspots.length
      ? tpl(t("capRate"), { hot: hotspots.length })
      : t("capRateNone");
  }

  // ---- Table sorting / i18n / wiring ----------------------------------------

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

  function applyI18n() {
    i18n.setLang(lang);
    document.documentElement.lang = lang;
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.innerHTML = t(el.getAttribute("data-i18n"));
    });
    // R2: translated tooltips on the table column headers (glossary on hover).
    document.querySelectorAll("[data-i18n-title]").forEach(function (el) {
      el.setAttribute("title", t(el.getAttribute("data-i18n-title")));
    });
    document.querySelectorAll(".lang-switch button").forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-lang") === lang ? "true" : "false");
    });
  }

  // Drive the provenance banner and the title from the dataset's OWN embedded
  // metadata, so the page never claims "real" or "demo" wrongly. A note that
  // mentions "synthetic"/"demo" (or no metadata at all) keeps the amber demo
  // warning; anything else is shown as real, with its exposure unit and source.
  function applyProvenance() {
    var note = document.querySelector(".demo-note, .real-note");
    if (!note || !meta || !Object.keys(meta).length) return; // pre-load: leave static
    var city = meta.city || "";
    var unit = meta.exposure_unit || "";
    var rawNote = meta.dataset_note || "";
    var synthetic = !rawNote || /synthet|demo/i.test(rawNote);
    if (city) document.title = tpl(t("titleCity"), { city: city });
    if (synthetic) {
      note.className = "demo-note";
      note.innerHTML = tpl(t("demo_synth"), { city: city || "demo" });
    } else {
      note.className = "real-note";
      // Keep the banner sentence fully in the active language; the source note is
      // mostly proper nouns (BikeMaps, OpenStreetMap), shown after a translated
      // "Source:" label, with any leading "Real data:"/"Datos reales:" stripped so
      // it doesn't read as a second, English sentence (R16).
      var cleaned = rawNote.replace(/^\s*(real data|datos reales)\s*:?\s*/i, "");
      var source = cleaned ? t("source_label") + " " + cleaned : "";
      note.innerHTML = tpl(t("demo_real"), { city: city, unit: unit, source: source });
    }
  }

  // R8 — a text equivalent of the map's main finding for screen-reader users (and
  // everyone): which segments are statistically significant hotspots, in words.
  function applyHotspotSummary() {
    var el = document.getElementById("hotspot-summary");
    if (!el || !rows.length) return; // pre-load: leave the "summarizing…" text
    var dataRows = rows.filter(hasRate);
    if (!dataRows.length) {
      el.textContent = t("hsEmpty");
      return;
    }
    var hot = dataRows
      .filter(function (p) {
        return p.getis_ord_significant;
      })
      .sort(function (a, b) {
        return (b.rate || 0) - (a.rate || 0);
      });
    if (!hot.length) {
      el.textContent = t("hsSummaryNone");
      return;
    }
    // R20: each named hotspot links to its row in the authoritative table, so a
    // reader (or a journalist citing it) can jump straight to the numbers.
    el.textContent = "";
    var template = t("hsSummary");
    var parts = template.split("{list}");
    el.appendChild(document.createTextNode(tpl(parts[0], { n: hot.length })));
    hot.forEach(function (p, i) {
      if (i > 0) el.appendChild(document.createTextNode(", "));
      var a = document.createElement("a");
      a.href = "#seg-" + p.segment_id;
      a.textContent = p.name || p.segment_id;
      el.appendChild(a);
    });
    if (parts[1]) el.appendChild(document.createTextNode(parts[1]));
  }

  // R4/R5 — a plain-language "bottom line" for a council member or neighbor: how
  // many blocks are real hotspots out of how many, the worst few by rate per
  // rider, and the one-line catch that volume is not danger.
  function applyBottomLine() {
    var el = document.getElementById("bottom-line");
    if (!el || !rows.length) return;
    var dataRows = rows.filter(hasRate);
    if (!dataRows.length) {
      el.textContent = t("blEmpty");
      return;
    }
    var hot = dataRows.filter(function (p) {
      return p.getis_ord_significant;
    });
    if (!hot.length) {
      el.textContent = tpl(t("blNone"), { n: dataRows.length });
      return;
    }
    var top = dataRows
      .slice()
      .sort(function (a, b) {
        return (b.rate || 0) - (a.rate || 0);
      })
      .slice(0, 3)
      .map(function (p) {
        return (p.name || p.segment_id) + " (" + fmt(p.rate) + ")";
      })
      .join(", ");
    el.textContent = tpl(t("blSummary"), { hot: hot.length, n: dataRows.length, list: top });
  }

  // R48 — surface the reporting-bias audit (bias.py) in the UI, not only in the
  // brief and data artifacts: the caveat note verbatim, then who the dataset
  // over- and under-reports relative to exposure. Driven entirely by the dataset's
  // own embedded metadata (meta.bias); the whole panel stays hidden when that is
  // absent, so an older dataset degrades gracefully.
  function applyBias() {
    var section = document.getElementById("bias-panel");
    if (!section) return;
    var bias = meta && meta.bias;
    var over = (bias && bias.over_represented) || [];
    var under = (bias && bias.under_represented) || [];
    if (!bias || (!over.length && !under.length)) {
      section.hidden = true;
      return;
    }
    var nameById = {};
    rows.forEach(function (p) {
      nameById[p.segment_id] = p.name || p.segment_id;
    });
    var noteEl = document.getElementById("bias-note");
    if (noteEl) noteEl.textContent = bias.caveat || "";
    fillBiasList("bias-over", "bias-over-h", over, nameById);
    fillBiasList("bias-under", "bias-under-h", under, nameById);
    section.hidden = false;
  }

  // Render one bias list (over- or under-represented) and hide its heading+list
  // when that side is empty. Each segment links to its row in the authoritative
  // table (R20), and shares are shown as percentages — no coordinate or raw count.
  function fillBiasList(listId, headingId, items, nameById) {
    var ul = document.getElementById(listId);
    var heading = document.getElementById(headingId);
    if (!ul) return;
    ul.textContent = "";
    var empty = !items || !items.length;
    if (heading) heading.hidden = empty;
    ul.hidden = empty;
    if (empty) return;
    items.forEach(function (it) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = "#seg-" + it.segment_id;
      a.textContent = nameById[it.segment_id] || it.segment_id;
      li.appendChild(a);
      li.appendChild(
        document.createTextNode(
          " — " +
            tpl(t("bias_shares"), {
              rshare: pct(it.report_share),
              eshare: pct(it.exposure_share),
            })
        )
      );
      ul.appendChild(li);
    });
  }

  function pct(share) {
    if (share === null || share === undefined) return t("none");
    return (Number(share) * 100).toFixed(1) + "%";
  }

  // R22 — point the download link at whatever dataset is actually loaded, and
  // name it (city, version, segment count) so people know what they're getting.
  function applyDownload() {
    var a = document.getElementById("download-data");
    if (a) a.setAttribute("href", DATA_URL);
    var m = document.getElementById("download-meta");
    if (!m) return;
    if (rows.length && meta && Object.keys(meta).length) {
      var n = meta.segments_published != null ? meta.segments_published : rows.filter(hasRate).length;
      m.textContent = tpl(t("downloadMeta"), {
        city: meta.city || "",
        ver: meta.dataset_version || "?",
        n: n,
      });
    } else {
      m.textContent = "";
    }
  }

  function wireSorting() {
    document.querySelectorAll("th button[data-sort]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var key = btn.getAttribute("data-sort");
        var asc = btn.closest("th").getAttribute("aria-sort") !== "ascending";
        setSortState(key, asc);
        rows.sort(compare(key, asc ? 1 : -1));
        renderTable();
        var status = document.getElementById("sort-status");
        if (status) {
          status.textContent = tpl(t("sortStatus"), {
            col: btn.textContent.trim(),
            dir: asc ? t("asc") : t("desc"),
          });
        }
      });
    });
  }

  function wireFilter() {
    var input = document.getElementById("table-filter");
    if (!input) return;
    input.addEventListener("input", function () {
      filterText = input.value.toLowerCase().trim();
      renderTable();
    });
  }

  // R10: let the reader show one map at a time (kinder on small screens and at
  // high zoom). Leaflet must recompute its size when a hidden map reappears.
  function wireMapToggle() {
    var split = document.querySelector(".map-split");
    var buttons = document.querySelectorAll(".map-toggle button[data-mapview]");
    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) {
          b.setAttribute("aria-pressed", b === btn ? "true" : "false");
        });
        if (split) split.setAttribute("data-view", btn.getAttribute("data-mapview"));
        if (maps.reports) {
          setTimeout(function () {
            maps.reports.invalidateSize();
            maps.rate.invalidateSize();
          }, 0);
        }
      });
    });
  }

  // R23: stamp the "generated on" date (and city, when known) into the print-only
  // header and footer, in the active language. Called on load, on language switch,
  // and again just before printing.
  function stampPrintMeta() {
    var now = new Date();
    var dateStr;
    try {
      dateStr = now.toLocaleDateString(lang === "es" ? "es" : "en", {
        year: "numeric",
        month: "long",
        day: "numeric",
      });
    } catch (e) {
      dateStr = now.toISOString().slice(0, 10);
    }
    var city = meta && meta.city ? meta.city : "";
    var text = city ? city + " · " + dateStr : dateStr;
    ["print-generated", "print-generated-footer"].forEach(function (id) {
      var el = document.getElementById(id);
      if (el) el.textContent = text;
    });
  }

  // R23: council-ready print / save-as-PDF. No external PDF library — the print
  // stylesheet does the layout. Here we (1) force the map view to "both" and clear
  // the table filter so the printout is the complete equivalent of the data, (2)
  // invalidate both Leaflet map sizes so tiles re-render at the print dimensions,
  // then restore the prior view/filter after printing.
  function wirePrint() {
    var btn = document.getElementById("print-btn");
    if (!btn) return;
    var saved = null;

    function beforePrint() {
      if (saved) return; // guard against beforeprint + matchMedia both firing
      var split = document.querySelector(".map-split");
      var filterInput = document.getElementById("table-filter");
      saved = {
        view: split ? split.getAttribute("data-view") : null,
        filter: filterText,
        filterValue: filterInput ? filterInput.value : "",
      };
      if (split) split.setAttribute("data-view", "both");
      if (filterText) {
        filterText = "";
        if (filterInput) filterInput.value = "";
        renderTable();
      }
      stampPrintMeta();
      if (maps.reports) {
        maps.reports.invalidateSize();
        maps.rate.invalidateSize();
      }
    }

    function afterPrint() {
      if (!saved) return;
      var split = document.querySelector(".map-split");
      var filterInput = document.getElementById("table-filter");
      if (split && saved.view) split.setAttribute("data-view", saved.view);
      if (saved.filter) {
        filterText = saved.filter;
        if (filterInput) filterInput.value = saved.filterValue;
        renderTable();
      }
      if (maps.reports) {
        setTimeout(function () {
          maps.reports.invalidateSize();
          maps.rate.invalidateSize();
        }, 0);
      }
      saved = null;
    }

    // The print lifecycle (button, Ctrl/Cmd+P, browser menu) is observed via both
    // beforeprint/afterprint and matchMedia('print'); engines vary in which fire,
    // and the `saved` guard makes a double-fire idempotent.
    window.addEventListener("beforeprint", beforePrint);
    window.addEventListener("afterprint", afterPrint);
    if (window.matchMedia) {
      var mql = window.matchMedia("print");
      var onChange = function (m) {
        if (m.matches) beforePrint();
        else afterPrint();
      };
      if (mql.addEventListener) mql.addEventListener("change", onChange);
      else if (mql.addListener) mql.addListener(onChange);
    }

    btn.addEventListener("click", function () {
      window.print();
    });
  }

  function wireLangSwitch() {
    document.querySelectorAll(".lang-switch button").forEach(function (b) {
      b.addEventListener("click", function () {
        var next = b.getAttribute("data-lang");
        // Fetch the locale catalog on demand (cached after first load), then
        // re-render everything in the new language.
        i18n.load(next).then(function () {
          lang = next;
          applyI18n();
          applyProvenance();
          applyHotspotSummary();
          applyBottomLine();
          applyBias();
          applyDownload();
          stampPrintMeta();
          if (rows.length) {
            renderTable();
            renderMaps();
          }
        });
      });
    });
  }

  function fail(message) {
    var body = document.getElementById("data-body");
    body.textContent = "";
    var tr = document.createElement("tr");
    var td = document.createElement("td");
    td.setAttribute("colspan", "8");
    td.textContent = tpl(t("fail"), { msg: message });
    tr.appendChild(td);
    body.appendChild(tr);
    document.getElementById("data-caption").textContent = tpl(t("fail"), { msg: message });
    document.getElementById("cap-reports").textContent = tpl(t("fail"), { msg: message });
    document.getElementById("cap-rate").textContent = tpl(t("fail"), { msg: message });
  }

  // Load the English fallback catalog and (if different) the requested locale
  // before the first render, so the page never flashes raw keys. Wiring is set
  // up first so the controls respond even while the data request is in flight.
  // E19 — a shareable PNG "card" of the honest headline (how many significant
  // hotspots, plus the top few) drawn client-side from the data already loaded,
  // via share-card.js. No new fetch, no map tiles, no external service.
  function wireShareCard() {
    var btn = document.getElementById("share-card-btn");
    if (!btn || !window.NearmissShareCard) return;
    btn.addEventListener("click", function () {
      if (!rows.length) return;
      NearmissShareCard.download(NearmissShareCard.buildData(rows, meta));
      var status = document.getElementById("share-card-status");
      if (status) status.textContent = t("shareCardDone");
    });
  }

  wireSorting();
  wireFilter();
  wireMapToggle();
  wirePrint();
  wireLangSwitch();
  wireShareCard();
  stampPrintMeta();

  i18n
    .load("en")
    .then(function () {
      return lang === "en" ? null : i18n.load(lang);
    })
    .then(function () {
      applyI18n();
      return fetch(DATA_URL);
    })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (geojson) {
      meta = (geojson && geojson.metadata) || {};
      applyProvenance();
      rows = rowsFromGeojson(geojson);
      rows.sort(compare("rate", -1));
      setSortState("rate", false);
      renderTable();
      renderMaps();
      applyHotspotSummary();
      applyBottomLine();
      applyBias();
      applyDownload();
      var shareBtn = document.getElementById("share-card-btn");
      if (shareBtn && window.NearmissShareCard) shareBtn.disabled = false;
      stampPrintMeta();
    })
    .catch(function (e) {
      fail(e.message);
    });
})();
