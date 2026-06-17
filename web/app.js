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

  var DATA_URL = "../data/published/davis.geojson";
  var lang = "en";
  var rows = [];
  var maps = {}; // { reports: L.Map, rate: L.Map }
  var dataLayers = { reports: [], rate: [] };

  var I18N = {
    en: {
      title: "nearmiss — where the danger actually is (Davis)",
      skip: "Skip to the data",
      h1: "nearmiss — where the danger actually is",
      lede:
        'Road-hazard and near-miss <strong>rates, normalized by exposure</strong>, each with a ' +
        '95% confidence interval and an <em>n</em>. Raw counts are report volume, not danger. ' +
        'The two maps below show the difference; the <a href="#data-table">data table</a> ' +
        "carries every finding and is the authoritative, non-visual equivalent of the maps.",
      demo:
        "⚠️ Showing the <strong>Davis synthetic demo</strong> dataset — generated test data, not " +
        "real reports. The method is the point: swap in real reports with no code change.",
      map_h: "Two maps, the same reports",
      map_desc:
        "The same near-miss reports, mapped two ways on a real street map. On the left, the " +
        "<strong>raw report count</strong> — what most safety maps show: the busiest street looks " +
        "the most dangerous. On the right, the <strong>rate per 1000 units of exposure</strong> — " +
        "which is what actually reflects danger. Watch the busiest street recede and the real " +
        "hotspot emerge. Nothing is conveyed by color alone: line thickness scales with the value, " +
        "and significant hotspots are dashed and labeled. Everything here is in the " +
        '<a href="#data-table">data table</a>, which the maps supplement.',
      map_reports_t: "① Raw report count — what most maps show",
      map_rate_t: "② Exposure-normalized rate — where the danger actually is",
      data_h: "Ranked segments",
      sort_help:
        "Sort the table with the column buttons. <strong>Significance</strong> and " +
        "<strong>confidence</strong> are stated in words, not by color.",
      legend_h: "How to read this",
      legend:
        "<li><strong>Rate /1000</strong> — reports per 1000 units of exposure, not a raw count.</li>" +
        "<li><strong>95% CI</strong> — the plausible range. A wide range means uncertainty.</li>" +
        "<li><strong>Confidence</strong> — “uncertain” marks small samples; “exposure unknown” " +
        "marks segments with no denominator (never ranked as if certain).</li>" +
        "<li><strong>Hotspot (Gi*)</strong> — “★ Significant” marks a statistically significant " +
        "cluster (Getis-Ord Gi*, z &gt; 1.96): hot beyond what exposure and chance explain.</li>",
      footer:
        'Open data, Apache-2.0. <a href="https://github.com/ChelseaKR/nearmiss">Source on GitHub</a> · ' +
        '<a href="https://chelseakr.com">chelseakr.com</a>. Maps © ' +
        '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors. Methods: ' +
        "<code>docs/METHODOLOGY.md</code>; limits and biases: <code>docs/DATA-CARD.md</code>. " +
        "Every figure regenerates with <code>make reproduce</code>.",
      th_segment: "Segment",
      th_rate: "Rate /1000",
      th_ci: "95% CI",
      th_n: "Reports (n)",
      th_conf: "Confidence",
      th_hot: "Hotspot (Gi*)",
      th_flags: "Quality flags",
      loading: "Loading published data…",
      loading_map: "Loading map…",
      caption: "Exposure-normalized hazard rates for the {n} analyzed segments (streets with reports).",
      capReports:
        "{n} street segments. Thicker, darker lines have more reports. The most-reported street " +
        "({peak}) dominates — but volume is exposure, not danger.",
      capRate:
        "The same segments by exposure-normalized rate. {hot} significant hotspot(s) — dashed and " +
        "labeled — emerge, while the most-reported street recedes to a thin line.",
      capRateNone:
        "The same segments by exposure-normalized rate. No segment is a statistically significant " +
        "hotspot; the most-reported street recedes.",
      mapEmpty: "No mappable segments.",
      mapNoLeaflet:
        "The interactive maps need JavaScript and the map library. The data table below carries every finding.",
      tipReports: "{name}: {count} reports",
      tipRate: "{name}: rate {rate}/1000",
      lblBusiest: "{name} — {count} reports (most-reported)",
      lblHotspot: "{name} — ★ rate {rate}",
      sortStatus: "Table sorted by {col}, {dir}.",
      asc: "ascending",
      desc: "descending",
      sig: "★ Significant",
      sigShort: " — ★ significant hotspot",
      conf_certain: "certain",
      conf_uncertain: "uncertain",
      conf_exposure_unknown: "exposure unknown",
      flag_low_sample: "low sample",
      flag_geocode_low_confidence: "low location confidence",
      flag_exposure_unknown: "exposure unknown",
      fail:
        "Could not load published data ({msg}). Run `make publish`, then `nearmiss serve` and open /web/index.html.",
      none: "—",
    },
    es: {
      title: "nearmiss — dónde está realmente el peligro (Davis)",
      skip: "Saltar a los datos",
      h1: "nearmiss — dónde está realmente el peligro",
      lede:
        'Tasas de peligros viales y cuasi-accidentes, <strong>normalizadas por exposición</strong>, ' +
        "cada una con un intervalo de confianza del 95% y una <em>n</em>. Los conteos crudos son " +
        'volumen de reportes, no peligro. Los dos mapas de abajo muestran la diferencia; la ' +
        '<a href="#data-table">tabla de datos</a> lleva cada hallazgo y es el equivalente no visual de los mapas.',
      demo:
        "⚠️ Mostrando el conjunto de <strong>demostración sintética de Davis</strong> — datos de prueba, no " +
        "reportes reales. El método es lo importante: se cambian por reportes reales sin tocar el código.",
      map_h: "Dos mapas, los mismos reportes",
      map_desc:
        "Los mismos reportes de cuasi-accidentes, mapeados de dos formas sobre un mapa de calles real. " +
        "A la izquierda, el <strong>conteo crudo de reportes</strong> — lo que muestran casi todos los " +
        "mapas: la calle más transitada parece la más peligrosa. A la derecha, la <strong>tasa por 1000 " +
        "unidades de exposición</strong> — que es lo que de verdad refleja el peligro. Observe cómo la " +
        "calle más transitada se desvanece y el punto caliente real aparece. Nada se transmite solo por " +
        "color: el grosor de la línea escala con el valor y los puntos calientes significativos van " +
        'discontinuos y etiquetados. Todo está en la <a href="#data-table">tabla de datos</a>, que los mapas complementan.',
      map_reports_t: "① Conteo crudo de reportes — lo que muestran casi todos los mapas",
      map_rate_t: "② Tasa normalizada por exposición — dónde está realmente el peligro",
      data_h: "Segmentos clasificados",
      sort_help:
        "Ordene la tabla con los botones de columna. La <strong>significancia</strong> y la " +
        "<strong>confianza</strong> se expresan en palabras, no por color.",
      legend_h: "Cómo leer esto",
      legend:
        "<li><strong>Tasa /1000</strong> — reportes por 1000 unidades de exposición, no un conteo crudo.</li>" +
        "<li><strong>IC 95%</strong> — el rango plausible. Un rango amplio significa incertidumbre.</li>" +
        "<li><strong>Confianza</strong> — “incierto” marca muestras pequeñas; “exposición desconocida” " +
        "marca segmentos sin denominador (nunca clasificados como ciertos).</li>" +
        "<li><strong>Punto caliente (Gi*)</strong> — “★ Significativo” marca un grupo estadísticamente " +
        "significativo (Getis-Ord Gi*, z &gt; 1.96): peligroso más allá de lo que explican exposición y azar.</li>",
      footer:
        'Datos abiertos, Apache-2.0. <a href="https://github.com/ChelseaKR/nearmiss">Código en GitHub</a> · ' +
        '<a href="https://chelseakr.com">chelseakr.com</a>. Mapas © ' +
        '<a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contribuyentes. Métodos: ' +
        "<code>docs/METHODOLOGY.md</code>; límites y sesgos: <code>docs/DATA-CARD.md</code>. " +
        "Cada cifra se regenera con <code>make reproduce</code>.",
      th_segment: "Segmento",
      th_rate: "Tasa /1000",
      th_ci: "IC 95%",
      th_n: "Reportes (n)",
      th_conf: "Confianza",
      th_hot: "Punto caliente (Gi*)",
      th_flags: "Indicadores de calidad",
      loading: "Cargando datos publicados…",
      loading_map: "Cargando mapa…",
      caption: "Tasas normalizadas por exposición de los {n} segmentos analizados (calles con reportes).",
      capReports:
        "{n} segmentos de calle. Las líneas más gruesas y oscuras tienen más reportes. La calle más " +
        "reportada ({peak}) domina — pero el volumen es exposición, no peligro.",
      capRate:
        "Los mismos segmentos por tasa normalizada por exposición. {hot} punto(s) caliente(s) " +
        "significativo(s) — discontinuos y etiquetados — aparecen, mientras la calle más reportada se " +
        "reduce a una línea delgada.",
      capRateNone:
        "Los mismos segmentos por tasa normalizada por exposición. Ningún segmento es un punto caliente " +
        "estadísticamente significativo; la calle más reportada se desvanece.",
      mapEmpty: "No hay segmentos mapeables.",
      mapNoLeaflet:
        "Los mapas interactivos necesitan JavaScript y la biblioteca de mapas. La tabla de datos de abajo lleva cada hallazgo.",
      tipReports: "{name}: {count} reportes",
      tipRate: "{name}: tasa {rate}/1000",
      lblBusiest: "{name} — {count} reportes (más reportada)",
      lblHotspot: "{name} — ★ tasa {rate}",
      sortStatus: "Tabla ordenada por {col}, {dir}.",
      asc: "ascendente",
      desc: "descendente",
      sig: "★ Significativo",
      sigShort: " — ★ punto caliente significativo",
      conf_certain: "cierto",
      conf_uncertain: "incierto",
      conf_exposure_unknown: "exposición desconocida",
      flag_low_sample: "muestra pequeña",
      flag_geocode_low_confidence: "ubicación poco confiable",
      flag_exposure_unknown: "exposición desconocida",
      fail:
        "No se pudieron cargar los datos publicados ({msg}). Ejecute `make publish`, luego `nearmiss serve` y abra /web/index.html.",
      none: "—",
    },
  };

  function t(key) {
    return (I18N[lang] && I18N[lang][key]) || I18N.en[key];
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

  function renderTable() {
    var body = document.getElementById("data-body");
    body.textContent = "";
    // The table is the authoritative DATA view: only analyzed segments (those with
    // an exposure denominator and a rate). The maps' gray context streets carry no
    // data, so they are not table rows.
    var dataRows = rows.filter(hasRate);
    dataRows.forEach(function (p) {
      var tr = document.createElement("tr");
      if (p.getis_ord_significant) tr.className = "is-hotspot";

      tr.appendChild(cell("th", p.name || p.segment_id));
      tr.firstChild.setAttribute("scope", "row");

      tr.appendChild(cell("td", fmt(p.rate)));
      tr.appendChild(cell("td", fmt(p.rate_ci_low) + " – " + fmt(p.rate_ci_high)));
      tr.appendChild(cell("td", String(p.n)));

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
      tr.appendChild(cell("td", flags.length ? flags.join(", ") : t("none")));
      body.appendChild(tr);
    });
    document.getElementById("data-caption").textContent = tpl(t("caption"), { n: dataRows.length });
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
    document.documentElement.lang = lang;
    document.title = t("title");
    document.querySelectorAll("[data-i18n]").forEach(function (el) {
      el.innerHTML = t(el.getAttribute("data-i18n"));
    });
    document.querySelectorAll(".lang-switch button").forEach(function (b) {
      b.setAttribute("aria-pressed", b.getAttribute("data-lang") === lang ? "true" : "false");
    });
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

  function wireLangSwitch() {
    document.querySelectorAll(".lang-switch button").forEach(function (b) {
      b.addEventListener("click", function () {
        lang = b.getAttribute("data-lang");
        applyI18n();
        if (rows.length) {
          renderTable();
          renderMaps();
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
    td.textContent = tpl(t("fail"), { msg: message });
    tr.appendChild(td);
    body.appendChild(tr);
    document.getElementById("data-caption").textContent = tpl(t("fail"), { msg: message });
    document.getElementById("cap-reports").textContent = tpl(t("fail"), { msg: message });
    document.getElementById("cap-rate").textContent = tpl(t("fail"), { msg: message });
  }

  applyI18n();
  wireSorting();
  wireLangSwitch();

  fetch(DATA_URL)
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(function (geojson) {
      rows = rowsFromGeojson(geojson);
      rows.sort(compare("rate", -1));
      setSortState("rate", false);
      renderTable();
      renderMaps();
    })
    .catch(function (e) {
      fail(e.message);
    });
})();
