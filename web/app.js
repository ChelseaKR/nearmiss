/* nearmiss accessible map UI — framework-free, no dependencies.
 *
 * Loads the published open GeoJSON and renders BOTH a supplementary schematic
 * map and the authoritative, sortable data table. The table is the non-visual
 * equivalent: every finding is reachable without seeing the map, and risk and
 * significance are stated in text, never by color alone. The chrome is bilingual
 * (English/Spanish) via the language toggle.
 */
(function () {
  "use strict";

  var DATA_URL = "../data/published/davis.geojson";
  var lang = "en";
  var rows = [];

  var I18N = {
    en: {
      title: "nearmiss — where the danger actually is (Davis)",
      skip: "Skip to the data",
      h1: "nearmiss — where the danger actually is",
      lede:
        'Road-hazard and near-miss <strong>rates, normalized by exposure</strong>, each with a ' +
        '95% confidence interval and an <em>n</em>. Raw counts are report volume, not danger. ' +
        'The <a href="#data-table">data table</a> below carries every finding and is the ' +
        "authoritative, non-visual equivalent of the map.",
      demo:
        "⚠️ Showing the <strong>Davis synthetic demo</strong> dataset — generated test data, not real reports.",
      map_h: "Map",
      map_desc:
        "A schematic map of street segments. Significant hotspots are drawn thicker and dashed " +
        "and are labeled in text; nothing here is conveyed by color alone. The map is " +
        'supplementary — the same information is in the <a href="#data-table">data table</a>.',
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
        '<a href="https://chelseakr.com">chelseakr.com</a>. Methods: <code>docs/METHODOLOGY.md</code>; ' +
        "limits and biases: <code>docs/DATA-CARD.md</code>. Every figure regenerates with " +
        "<code>make reproduce</code>.",
      th_segment: "Segment",
      th_rate: "Rate /1000",
      th_ci: "95% CI",
      th_n: "Reports (n)",
      th_conf: "Confidence",
      th_hot: "Hotspot (Gi*)",
      th_flags: "Quality flags",
      loading: "Loading published data…",
      caption: "Exposure-normalized hazard rates by segment ({n} published segments).",
      mapCaption: "{n} street segments. Thicker, dashed lines are significant hotspots.",
      mapEmpty: "No mappable segments.",
      sortStatus: "Table sorted by {col}, {dir}.",
      asc: "ascending",
      desc: "descending",
      sig: "★ Significant",
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
        'volumen de reportes, no peligro. La <a href="#data-table">tabla de datos</a> de abajo lleva ' +
        "cada hallazgo y es el equivalente no visual del mapa.",
      demo:
        "⚠️ Mostrando el conjunto de <strong>demostración sintética de Davis</strong> — datos de prueba, no reportes reales.",
      map_h: "Mapa",
      map_desc:
        "Un mapa esquemático de segmentos de calle. Los puntos calientes significativos se dibujan más " +
        "gruesos y discontinuos y se rotulan en texto; nada se transmite solo por color. El mapa es " +
        'complementario — la misma información está en la <a href="#data-table">tabla de datos</a>.',
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
        '<a href="https://chelseakr.com">chelseakr.com</a>. Métodos: <code>docs/METHODOLOGY.md</code>; ' +
        "límites y sesgos: <code>docs/DATA-CARD.md</code>. Cada cifra se regenera con " +
        "<code>make reproduce</code>.",
      th_segment: "Segmento",
      th_rate: "Tasa /1000",
      th_ci: "IC 95%",
      th_n: "Reportes (n)",
      th_conf: "Confianza",
      th_hot: "Punto caliente (Gi*)",
      th_flags: "Indicadores de calidad",
      loading: "Cargando datos publicados…",
      caption: "Tasas de peligro normalizadas por exposición, por segmento ({n} segmentos publicados).",
      mapCaption: "{n} segmentos de calle. Las líneas más gruesas y discontinuas son puntos calientes significativos.",
      mapEmpty: "No hay segmentos mapeables.",
      sortStatus: "Tabla ordenada por {col}, {dir}.",
      asc: "ascendente",
      desc: "descendente",
      sig: "★ Significativo",
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
    rows.forEach(function (p) {
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
    document.getElementById("data-caption").textContent = tpl(t("caption"), { n: rows.length });
  }

  function renderMap() {
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
      document.getElementById("map-caption").textContent = t("mapEmpty");
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
      // Color by rate: red (significant hotspot), blue (has reports), gray
      // (context street with no exposure/reports). Significance is also marked
      // by a dashed pattern, never color alone.
      var hasRate = p.rate !== null && p.rate !== undefined && p.rate > 0;
      line.setAttribute("stroke", p.getis_ord_significant ? "#8a1c1c" : hasRate ? "#0b4f9c" : "#c3ccd6");
      line.setAttribute("stroke-width", p.getis_ord_significant ? "2.6" : hasRate ? "1.6" : "1.0");
      line.setAttribute("stroke-linecap", "round");
      if (p.getis_ord_significant) line.setAttribute("stroke-dasharray", "3 1.5");
      var title = document.createElementNS("http://www.w3.org/2000/svg", "title");
      title.textContent =
        (p.name || p.segment_id) + ": " + t("th_rate") + " " + fmt(p.rate) +
        (p.getis_ord_significant ? " — " + t("sig") : "");
      line.appendChild(title);
      svg.appendChild(line);
    });
    document.getElementById("map-caption").textContent = tpl(t("mapCaption"), { n: rows.length });
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
        renderMap();
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
          renderMap();
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
    document.getElementById("map-caption").textContent = tpl(t("fail"), { msg: message });
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
      renderMap();
    })
    .catch(function (e) {
      fail(e.message);
    });
})();
