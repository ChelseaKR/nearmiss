// Web-consumer contract test (FIX-10). The published dataset promises a schema
// (schema/dataset.schema.json); this check proves the browser consumer (app.js)
// actually depends on that contract and breaks when it is violated — so a schema
// change that would strand the map cannot land silently.
//
// It loads the committed data/published/davis.geojson fixture, boots app.js in
// jsdom (no browser, no Leaflet), and:
//   1. asserts every feature property app.js reads is declared REQUIRED in the
//      JSON Schema (the schema guarantees what the consumer needs);
//   2. exercises app.js's GeoJSON parse+render path against the fixture and
//      asserts it consumes those properties without error, rendering the right
//      per-segment rate / n / name into the authoritative data table; and
//   3. removes each required, table-rendered property in turn and asserts the
//      rendered output visibly changes — i.e. dropping a required property fails
//      the consumer rather than passing silently.
//
// Lives in web/ so Node resolves web/node_modules (jsdom), mirroring axe_check.mjs.
// Usage:  cd web && npm install && npm run contract
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

const here = dirname(fileURLToPath(import.meta.url)); // web/
const repoRoot = join(here, "..");
const INDEX = join(here, "davis-demo.html");
const APP_JS = join(here, "app.js");
const EMBED_HTML = join(here, "embed.html");
const EMBED_JS = join(here, "embed.js");
const EMBED_LOADER_JS = join(here, "nearmiss-embed.js");
const I18N_JS = join(here, "i18n.js");
const LOCALES_DIR = join(here, "locales");
const FIXTURE = join(repoRoot, "data", "published", "davis.geojson");
const SCHEMA = join(repoRoot, "schema", "dataset.schema.json");

function die(msg) {
  console.error(`contract: FAIL — ${msg}`);
  process.exit(1);
}

// Feature properties app.js reads out of each feature's `properties` object while
// parsing and rendering the dataset. Kept in step with web/app.js by hand; every
// entry must be declared required by the JSON Schema (checked below).
//   segment_id, name         -> renderTable row header + anchor id (l.404-406)
//   rate                     -> hasRate filter + rate cell (l.369, 409)
//   rate_ci_low/high         -> interval cell (l.410)
//   n                        -> sample-size cell (l.411)
//   hazard_breakdown         -> hazard-mix cell (l.414-425)
//   confidence_label         -> confidence cell + styling (l.427-429)
//   getis_ord_significant    -> hotspot row class + cell (l.402, 431)
//   getis_ord_z              -> hotspot cell z-score (l.436)
//   report_count             -> map intensity + protagonist selection (l.585-597)
const CONSUMED_FEATURE_PROPS = [
  "segment_id",
  "name",
  "rate",
  "rate_ci_low",
  "rate_ci_high",
  "n",
  "hazard_breakdown",
  "confidence_label",
  "getis_ord_significant",
  "getis_ord_z",
  "report_count",
];

// Embedded-metadata members app.js reads (applyProvenance / applyDownload).
const CONSUMED_META_MEMBERS = [
  "city",
  "exposure_unit",
  "dataset_note",
  "dataset_version",
  "segments_published",
];

// The subset of consumed properties that render into the authoritative data
// table, so removing any one of them observably changes the rendered rows.
const TABLE_RENDERED_PROPS = [
  "segment_id",
  "name",
  "rate",
  "rate_ci_low",
  "rate_ci_high",
  "n",
  "hazard_breakdown",
  "confidence_label",
  "getis_ord_significant",
];

const clone = (o) => JSON.parse(JSON.stringify(o));

function without(geojson, prop) {
  const copy = clone(geojson);
  for (const f of copy.features) delete f.properties[prop];
  return copy;
}

function installLeafletStub(window, tooltipContents) {
  const map = {
    fitBounds() {},
    getCenter() {
      return [0, 0];
    },
    getZoom() {
      return 1;
    },
    on() {},
    removeLayer() {},
    setView() {},
  };
  window.L = {
    latLngBounds() {
      return {
        extend() {},
        isValid() {
          return true;
        },
      };
    },
    map() {
      return map;
    },
    polyline() {
      return {
        addTo() {
          return this;
        },
        bindTooltip(content) {
          tooltipContents.push(content);
          return this;
        },
        openTooltip() {
          return this;
        },
      };
    },
    tileLayer() {
      return {
        addTo() {},
      };
    },
  };
}

// Boot app.js in jsdom with fetch stubbed to serve `geojson`, no Leaflet present
// (so renderMaps short-circuits and the data TABLE is the parse-path evidence).
async function render(
  geojson,
  { leaflet = false, url = "https://example.test/web/davis-demo.html" } = {}
) {
  const html = readFileSync(INDEX, "utf-8");
  const appSource = readFileSync(APP_JS, "utf-8");
  const i18nSource = readFileSync(I18N_JS, "utf-8");
  const dom = new JSDOM(html, {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url,
    virtualConsole: new VirtualConsole(),
  });
  const { window } = dom;
  const fetchTargets = [];
  const tooltipContents = [];
  if (leaflet) installLeafletStub(window, tooltipContents);
  // app.js fetches both the dataset and the web locale catalogs (FIX-13's
  // single-sourced translations); serve the committed catalogs for locales/*
  // and the fixture under test for everything else.
  window.fetch = (url) => {
    const target = String(url);
    fetchTargets.push(target);
    const locale = target.match(/locales\/([a-z]{2,3})\.json$/);
    if (locale) {
      const raw = JSON.parse(readFileSync(join(LOCALES_DIR, `${locale[1]}.json`), "utf-8"));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(raw) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(clone(geojson)) });
  };
  // i18n.js loads first in index.html and app.js depends on window.NearmissI18n.
  window.eval(i18nSource);
  window.eval(appSource);
  // Flush the fetch().then().then() microtask chain.
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));

  const doc = window.document;
  const body = doc.getElementById("data-body");
  const failed = !!body.querySelector("td[colspan]"); // app.js fail() marker
  return { doc, window, body, failed, html: body.innerHTML, fetchTargets, tooltipContents };
}

async function renderEmbed(url, geojson, { leaflet = false } = {}) {
  const dom = new JSDOM(
    '<!doctype html><a id="embed-brand-link"></a><div id="embed-map"></div>' +
      '<p id="embed-caption"></p><ul id="embed-hotspots"></ul><p id="embed-source"></p>' +
      '<a id="embed-fulllink"></a>',
    { runScripts: "outside-only", pretendToBeVisual: true, url }
  );
  const targets = [];
  const tooltipContents = [];
  if (leaflet) installLeafletStub(dom.window, tooltipContents);
  dom.window.fetch = (target) => {
    targets.push(String(target));
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(clone(geojson)) });
  };
  dom.window.eval(readFileSync(EMBED_JS, "utf-8"));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  const brandHref = dom.window.document.getElementById("embed-brand-link").href;
  const fullHref = dom.window.document.getElementById("embed-fulllink").href;
  dom.window.close();
  return { targets, tooltipContents, brandHref, fullHref };
}

function renderEmbedLoader(attributes) {
  const dom = new JSDOM(
    '<!doctype html><div id="host"><script id="loader" ' +
      'src="/web/nearmiss-embed.js"></script></div>',
    { runScripts: "outside-only", url: "http://127.0.0.1:8000/embed-fixture.html" }
  );
  const loader = dom.window.document.getElementById("loader");
  Object.entries(attributes).forEach(([name, value]) => loader.setAttribute(name, value));
  dom.window.eval(readFileSync(EMBED_LOADER_JS, "utf-8"));
  const iframe = dom.window.document.querySelector("iframe");
  const result = iframe
    ? { src: iframe.src, title: iframe.title, sandbox: iframe.getAttribute("sandbox") }
    : null;
  dom.window.close();
  return result;
}

function datasetTarget(rendered) {
  return rendered.fetchTargets.find((target) => !target.includes("/locales/"));
}

function cellsFor(doc, segmentId) {
  const th = doc.getElementById(`seg-${segmentId}`);
  if (!th) return null;
  const tr = th.parentElement;
  return Array.from(tr.children).map((c) => c.textContent);
}

function linksToPublicSite(source) {
  const externalUrls = source.match(/(?:https?:)?\/\/[^\s"'`<>\\)]+/g) ?? [];
  return externalUrls.some((candidate) => {
    try {
      return new URL(candidate, "https://source-fixture.invalid").hostname === "nearmiss.chelseakr.com";
    } catch {
      return false;
    }
  });
}

async function main() {
  const productionLinkCases = [
    ['href="https://nearmiss.chelseakr.com/web/embed.html"', true],
    ['href="//nearmiss.chelseakr.com/web/embed.html"', true],
    ['href="https://nearmiss.chelseakr.com.attacker.example/"', false],
    ['href="https://attacker.example/nearmiss.chelseakr.com"', false],
  ];
  for (const [source, expected] of productionLinkCases) {
    if (linksToPublicSite(source) !== expected) {
      die(`production-link classifier failed closed for ${source}`);
    }
  }
  for (const script of [APP_JS, EMBED_JS, EMBED_LOADER_JS, I18N_JS]) {
    const source = readFileSync(script, "utf-8");
    if (/\b(?:innerHTML|outerHTML|insertAdjacentHTML|document\.write|DOMParser)\b/.test(source)) {
      die(`${script} must not reinterpret translation or dataset text as HTML`);
    }
  }
  for (const sourceFile of [EMBED_HTML, EMBED_JS, EMBED_LOADER_JS]) {
    if (linksToPublicSite(readFileSync(sourceFile, "utf-8"))) {
      die(`${sourceFile} sent the source-only embed back to the retired public demo`);
    }
  }
  const embedDocument = new JSDOM(readFileSync(EMBED_HTML, "utf-8")).window.document;
  if (embedDocument.querySelector('meta[name="robots"]')?.content !== "noindex, nofollow") {
    die("embed.html did not keep the source-only fixture out of search and link crawling");
  }
  for (const id of ["embed-brand-link", "embed-fulllink"]) {
    if (embedDocument.getElementById(id)?.getAttribute("href") !== "/web/davis-demo.html?city=davis") {
      die(`embed.html did not default ${id} to the local Davis methods fixture`);
    }
  }
  const schema = JSON.parse(readFileSync(SCHEMA, "utf-8"));
  const requiredProps = new Set(schema.$defs.properties.required);
  const requiredMeta = new Set(schema.$defs.metadata.required);
  const fixture = JSON.parse(readFileSync(FIXTURE, "utf-8"));

  // (1) The schema must promise every property the consumer relies on.
  for (const p of CONSUMED_FEATURE_PROPS) {
    if (!requiredProps.has(p)) {
      die(`app.js consumes feature property "${p}" but the schema does not require it`);
    }
  }
  for (const m of CONSUMED_META_MEMBERS) {
    if (!requiredMeta.has(m)) {
      die(`app.js consumes metadata member "${m}" but the schema does not require it`);
    }
  }
  console.log(
    `contract: schema requires all ${CONSUMED_FEATURE_PROPS.length} consumed feature ` +
      `properties and all ${CONSUMED_META_MEMBERS.length} consumed metadata members.`
  );

  // (2) Positive: app.js parses the real fixture and renders it without error.
  const rated = fixture.features.filter(
    (f) => f.properties.rate !== null && f.properties.rate !== undefined
  );
  if (rated.length === 0) die("fixture has no rate-bearing features to exercise");

  const base = await render(fixture);
  if (base.failed) die("app.js entered its error state on the valid fixture");
  if (base.doc.querySelector('a[href="/fars/national/"]')) {
    die("source-only methods UI linked to the production-only national route");
  }
  if (base.doc.querySelectorAll('a[href="/web/us-coverage.html"]').length < 2) {
    die("source-only methods UI did not link locally to the national preview");
  }
  const rows = base.doc.querySelectorAll("#data-body tr").length;
  if (rows !== rated.length) {
    die(`expected ${rated.length} rendered data rows, got ${rows}`);
  }
  for (const f of rated) {
    const p = f.properties;
    const cells = cellsFor(base.doc, p.segment_id);
    if (!cells) die(`no rendered row (anchor seg-${p.segment_id}) — segment_id not consumed`);
    if (cells[0] !== p.name) die(`row ${p.segment_id}: name not rendered (got "${cells[0]}")`);
    if (cells[1] !== p.rate.toFixed(2)) {
      die(`row ${p.segment_id}: rate not rendered (got "${cells[1]}")`);
    }
    if (cells[3] !== String(p.n)) die(`row ${p.segment_id}: n not rendered (got "${cells[3]}")`);
    const ci = `${p.rate_ci_low.toFixed(2)} – ${p.rate_ci_high.toFixed(2)}`;
    if (cells[2] !== ci) die(`row ${p.segment_id}: interval not rendered (got "${cells[2]}")`);
  }
  if (!base.doc.querySelector('.lede strong') || !base.doc.querySelector('.lede em')) {
    die("safe translation renderer dropped the lede's semantic emphasis");
  }
  if (base.doc.querySelector('.lede a')?.getAttribute("href") !== "#data-table") {
    die("safe translation renderer dropped the lede's audited table link");
  }
  if (base.doc.querySelectorAll('[data-i18n="legend"] > li').length !== 4) {
    die("safe translation renderer dropped the four-item evidence legend");
  }
  if (base.doc.querySelectorAll('footer [data-i18n="footer"] a').length !== 3) {
    die("safe translation renderer dropped an audited footer link");
  }
  console.log(
    `contract: app.js parsed the fixture and rendered ${rows} segments with correct ` +
      `rate / interval / n / name.`
  );

  // (3) Negative: dropping any required, table-rendered property must change output.
  for (const prop of TABLE_RENDERED_PROPS) {
    const mutated = await render(without(fixture, prop));
    if (mutated.html === base.html) {
      die(`removing required property "${prop}" did not change the rendered output`);
    }
  }
  // rate is the linchpin the consumer filters on: without it the data view collapses.
  const noRate = await render(without(fixture, "rate"));
  const noRateRows = noRate.doc.querySelectorAll("#data-body tr").length;
  if (noRateRows === rated.length) {
    die("removing required property \"rate\" left the data table fully populated");
  }
  console.log(
    `contract: removing each of ${TABLE_RENDERED_PROPS.length} required properties ` +
      `visibly breaks the rendered dataset.`
  );

  // Metadata consumption: dropping the embedded metadata empties the provenance-
  // driven download summary that applyDownload builds from it.
  const noMeta = clone(fixture);
  delete noMeta.metadata;
  const rendered = await render(noMeta);
  const dl = rendered.doc.getElementById("download-meta");
  const baseDl = base.doc.getElementById("download-meta");
  if ((baseDl.textContent || "") === "" ) {
    die("expected the valid fixture to populate the download-meta summary");
  }
  if (dl.textContent === baseDl.textContent) {
    die("removing embedded metadata did not change the metadata-driven summary");
  }

  const hostileMeta = clone(fixture);
  hostileMeta.metadata.city = '<img src=x onerror="alert(1)">';
  hostileMeta.metadata.dataset_note = "Real data: reviewed fixture";
  const hostileRendered = await render(hostileMeta);
  if (hostileRendered.doc.querySelector(".real-note img")) {
    die("dataset metadata created executable markup in the provenance banner");
  }
  if (!hostileRendered.doc.querySelector(".real-note strong")?.textContent.includes("<img")) {
    die("dataset metadata was not preserved as literal provenance text");
  }

  const hostileMap = clone(fixture);
  hostileMap.features[0].properties.name = '<img src=x onerror="alert(1)">';
  const hostileAppMap = await render(hostileMap, { leaflet: true });
  const hostileEmbedMap = await renderEmbed(
    "https://example.test/web/embed.html?city=davis",
    hostileMap,
    { leaflet: true }
  );
  for (const [consumer, contents] of [
    ["app.js", hostileAppMap.tooltipContents],
    ["embed.js", hostileEmbedMap.tooltipContents],
  ]) {
    if (!contents.length || contents.some((content) => content.nodeType !== 1)) {
      die(`${consumer} did not bind tooltip text through DOM elements`);
    }
    if (
      contents.some((content) => content.querySelector("img")) ||
      !contents.some((content) => content.textContent.includes("<img"))
    ) {
      die(`${consumer} reinterpreted hostile dataset labels as tooltip markup`);
    }
  }

  const i18nFetchTargets = [];
  base.window.fetch = (target) => {
    i18nFetchTargets.push(String(target));
    return Promise.reject(new Error("unsupported locale must not be fetched"));
  };
  const isolatedI18n = base.window.NearmissI18n.create("web.app.");
  await isolatedI18n.load("__proto__");
  await isolatedI18n.load("constructor");
  isolatedI18n.setLang("__proto__");
  if (i18nFetchTargets.length || isolatedI18n.lang() !== "en" || isolatedI18n.loaded("__proto__")) {
    die("i18n loader did not reject unsupported prototype-like locale names");
  }

  const datasetCases = [
    ["?city=riverside", "../data/published/riverside.geojson"],
    ["?data=../data/published/riverside.geojson", "../data/published/riverside.geojson"],
    ["?data=/data/published/riverside.geojson", "../data/published/riverside.geojson"],
    ["?data=https://attacker.example/private.geojson", "../data/published/davis.geojson"],
    ["?data=../../data/raw/private.geojson", "../data/published/davis.geojson"],
    ["?data=../data/published/../../raw/private.geojson", "../data/published/davis.geojson"],
    ["?data=../data/published/%252e%252e%252fprivate.geojson", "../data/published/davis.geojson"],
    ["?data=..%2Fdata%2Fpublished%2Friverside.geojson", "../data/published/davis.geojson"],
    ["?data=..%5Cdata%5Cpublished%5Criverside.geojson", "../data/published/davis.geojson"],
    ["?data=..\\data\\published\\riverside.geojson", "../data/published/davis.geojson"],
    ["?data=../data/published/riverside.geojson%3Fraw=1", "../data/published/davis.geojson"],
    ["?data=../data/published/riverside.geojson%23raw", "../data/published/davis.geojson"],
    ["?data=javascript:alert(1)", "../data/published/davis.geojson"],
    ["?data=../data/published/riverside.geojson&data=../data/published/davis.geojson", "../data/published/davis.geojson"],
    ["?city=riverside&data=../data/published/riverside.geojson", "../data/published/davis.geojson"],
    ["?city=unlisted", "../data/published/davis.geojson"],
    ["?city=../../private", "../data/published/davis.geojson"],
  ];
  for (const [query, expected] of datasetCases) {
    const url = `https://example.test/web/davis-demo.html${query}`;
    const appRendered = await render(fixture, { url });
    if (datasetTarget(appRendered) !== expected) {
      die(`app.js did not fail closed for dataset query ${query}`);
    }
    const embedded = await renderEmbed(
      `https://example.test/web/embed.html${query}`,
      fixture
    );
    if (embedded.targets[0] !== expected) {
      die(`embed.js did not fail closed for dataset query ${query}`);
    }
    const expectedSlug = expected.includes("riverside") ? "riverside" : "davis";
    const expectedDemo = `https://example.test/web/davis-demo.html?city=${expectedSlug}`;
    if (embedded.brandHref !== expectedDemo || embedded.fullHref !== expectedDemo) {
      die(`embed.js did not keep local demo links aligned for dataset query ${query}`);
    }
  }

  const loaderCases = [
    [{}, "http://127.0.0.1:8000/web/embed.html"],
    [{ "data-city": "riverside" }, "http://127.0.0.1:8000/web/embed.html?city=riverside"],
    [
      { "data-data": "../data/published/riverside.geojson" },
      "http://127.0.0.1:8000/web/embed.html?city=riverside",
    ],
    [
      { "data-data": "../../data/raw/private.geojson" },
      "http://127.0.0.1:8000/web/embed.html",
    ],
    [
      { "data-data": "https://attacker.example/private.geojson" },
      "http://127.0.0.1:8000/web/embed.html",
    ],
    [
      { "data-data": "../data/published/riverside.geojson?raw=1" },
      "http://127.0.0.1:8000/web/embed.html",
    ],
    [
      { "data-city": "riverside", "data-data": "../data/published/riverside.geojson" },
      "http://127.0.0.1:8000/web/embed.html",
    ],
    [{ "data-city": "unlisted" }, "http://127.0.0.1:8000/web/embed.html"],
    [{ "data-city": "../../private" }, "http://127.0.0.1:8000/web/embed.html"],
    [
      { src: "https://attacker.example/nearmiss-embed.js", "data-city": "riverside" },
      "http://127.0.0.1:8000/web/embed.html?city=riverside",
    ],
  ];
  for (const [attributes, expected] of loaderCases) {
    const loaded = renderEmbedLoader(attributes);
    if (!loaded || loaded.src !== expected) {
      die(`nearmiss-embed.js did not canonicalize ${JSON.stringify(attributes)}`);
    }
    if (!loaded.sandbox?.includes("allow-scripts")) {
      die("nearmiss-embed.js dropped the iframe security boundary");
    }
  }

  const hostileLoader = renderEmbedLoader({ "data-title": '<img src=x onerror="alert(1)">' });
  if (!hostileLoader || hostileLoader.title !== '<img src=x onerror="alert(1)">') {
    die("nearmiss-embed.js did not preserve a hostile title as literal text");
  }

  console.log(
    "contract: OK — web consumers honor the published schema and restrict query-selected data to allowlisted source fixtures."
  );
}

main().catch((e) => die(e && e.stack ? e.stack : String(e)));
