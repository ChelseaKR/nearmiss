// Browser contract for the hash-bound, five-year nationwide FARS ledger.
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import axe from "axe-core";
import { JSDOM, VirtualConsole } from "jsdom";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..");
const APEX = join(repoRoot, "index.html");
const PAGE = join(here, "us-coverage.html");
const DAVIS_HOME = join(here, "index.html");
const NATIONAL_ROUTE = "/fars/national/";
const NATIONAL_CANONICAL = "https://nearmiss.chelseakr.com/fars/national/";
const APP = join(here, "us-coverage.js");
const STUDIO_STYLE = join(here, "us-coverage-studio.css");
const I18N = join(here, "i18n.js");
const LOCALES = join(here, "locales");
const INDEX = join(repoRoot, "data", "published", "fars-state-mode-index-v2.json");
const LEGACY_INDEX = join(repoRoot, "data", "published", "fars-state-mode-index.json");
const CORRECTIONS = join(repoRoot, "data", "published", "fars-release-corrections.json");
const BOUNDARIES = join(repoRoot, "data", "published", "us-state-boundaries-2024.json");
const YEARS = [2020, 2021, 2022, 2023, 2024];
const ARTIFACTS = Object.fromEntries(
  YEARS.map((year) => [
    year,
    join(
      repoRoot,
      "data",
      "published",
      `fars-${year}-state-mode${year === 2024 ? "-r2" : ""}.json`
    ),
  ])
);

const CHECKED_INDEX_BYTES = readFileSync(INDEX);
const LEGACY_INDEX_BYTES = readFileSync(LEGACY_INDEX);
const CORRECTION_BYTES = readFileSync(CORRECTIONS);
const CHECKED_BOUNDARY_BYTES = readFileSync(BOUNDARIES);
const CHECKED_ARTIFACT_BYTES_BY_YEAR = Object.fromEntries(
  YEARS.map((year) => [year, readFileSync(ARTIFACTS[year])])
);
const CHECKED_ARTIFACT_BYTES = CHECKED_ARTIFACT_BYTES_BY_YEAR[2024];
const CHECKED_INDEX = JSON.parse(CHECKED_INDEX_BYTES.toString("utf-8"));
const CHECKED_ARTIFACT = JSON.parse(CHECKED_ARTIFACT_BYTES.toString("utf-8"));
const CHECKED_RELEASE_2024 = CHECKED_INDEX.releases.find((release) => release.dataset_year === 2024);
const EXPECTED_MODES = CHECKED_INDEX.contract.modes;
const EXPECTED_ARTIFACT_PINS = {
  2020: [27589, "db4c50d998d20bc2f341b1943c883f6d6d3c805db4bb7117564619119499290c"],
  2021: [27630, "de7406ca0980e9d092eb25a230fe17fb2500f07b3b36f781dc3e4b35b7983168"],
  2022: [27622, "39f8e39fd52cc17abf07377dc460bc9545e05b82525740d8718c57e0f6fc4af8"],
  2023: [27636, "a0ddddc47f7c9ca70b823083f9f13831844b23fc45113321a3408a894eb98ade"],
  2024: [27603, "79cf34d3af696c9e487adb9a8d3897d9c90cdf55dbe0c9b6eaf16ef634a98b79"],
};

const clone = (value) => JSON.parse(JSON.stringify(value));
const digest = (bytes) => createHash("sha256").update(bytes).digest("hex");

function die(message) {
  console.error(`us-coverage contract: FAIL — ${message}`);
  process.exit(1);
}

function canonical(value) {
  function ordered(item) {
    if (Array.isArray(item)) return item.map(ordered);
    if (item && typeof item === "object") {
      return Object.fromEntries(Object.keys(item).sort().map((key) => [key, ordered(item[key])]));
    }
    return item;
  }
  return Buffer.from(`${JSON.stringify(ordered(value))}\n`, "utf-8");
}

function releaseSubsetIndex(years) {
  const index = clone(CHECKED_INDEX);
  index.releases = index.releases.filter((release) => years.includes(release.dataset_year));
  index.default_year = years[years.length - 1];
  return canonical(index);
}

function rebindArtifact(year, bytes) {
  const index = clone(CHECKED_INDEX);
  const release = index.releases.find((candidate) => candidate.dataset_year === year);
  release.artifact_bytes = bytes.byteLength;
  release.artifact_sha256 = digest(bytes);
  return canonical(index);
}

async function settle() {
  for (let index = 0; index < 7; index += 1) {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }
}

function sameRawTargetSet(actual, expected) {
  return (
    JSON.stringify(Array.from(new Set(actual)).sort()) ===
    JSON.stringify(Array.from(new Set(expected)).sort())
  );
}

function trustedAppSource(indexBytes) {
  const source = readFileSync(APP, "utf-8");
  return source
    .replace(/var EXPECTED_INDEX_BYTES = [0-9]+;/, `var EXPECTED_INDEX_BYTES = ${indexBytes.byteLength};`)
    .replace(
      /var EXPECTED_INDEX_SHA256 = "[0-9a-f]{64}";/,
      `var EXPECTED_INDEX_SHA256 = "${digest(indexBytes)}";`
    );
}

async function boot({
  indexBytes = CHECKED_INDEX_BYTES,
  trustedIndexBytes = CHECKED_INDEX_BYTES,
  artifacts = CHECKED_ARTIFACT_BYTES_BY_YEAR,
  failFetch = false,
  disableCrypto = false,
  deferredLocales = [],
  deferredArtifacts = [],
  failArtifactYears = [],
  boundaryBytes = CHECKED_BOUNDARY_BYTES,
  url = "https://example.test/web/us-coverage.html",
} = {}) {
  const dom = new JSDOM(readFileSync(PAGE, "utf-8"), {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url,
    virtualConsole: new VirtualConsole(),
  });
  const { window } = dom;
  const localeResolvers = {};
  const artifactResolvers = {};
  const artifactFetchCounts = {};
  const fetchTargets = [];
  Object.defineProperty(window, "crypto", { value: disableCrypto ? {} : webcrypto, configurable: true });
  window.TextDecoder = TextDecoder;
  window.fetch = (requested) => {
    const target = String(requested);
    fetchTargets.push(target);
    const locale = target.match(/locales\/([a-z]{2,3})\.json$/);
    if (locale) {
      const catalog = JSON.parse(readFileSync(join(LOCALES, `${locale[1]}.json`), "utf-8"));
      const response = { ok: true, status: 200, json: () => Promise.resolve(catalog) };
      if (deferredLocales.includes(locale[1])) {
        return new Promise((resolve) => {
          localeResolvers[locale[1]] = () => resolve(response);
        });
      }
      return Promise.resolve(response);
    }
    if (failFetch) return Promise.resolve({ ok: false, status: 503 });
    let bytes;
    if (target.endsWith("us-state-boundaries-2024.json")) {
      bytes = boundaryBytes;
    } else if (target.endsWith("fars-state-mode-index-v2.json")) {
      bytes = indexBytes;
    } else {
      const match = target.match(/fars-([0-9]{4})-state-mode(?:-r[2-9][0-9]*)?\.json$/);
      const year = match ? Number(match[1]) : null;
      if (year !== null) artifactFetchCounts[year] = (artifactFetchCounts[year] || 0) + 1;
      if (year !== null && failArtifactYears.includes(year)) {
        return Promise.resolve({ ok: false, status: 503 });
      }
      bytes = year !== null ? artifacts[year] : undefined;
      if (bytes && deferredArtifacts.includes(year)) {
        const exact = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
        return new Promise((resolve) => {
          artifactResolvers[year] = () =>
            resolve({ ok: true, status: 200, arrayBuffer: () => Promise.resolve(exact) });
        });
      }
    }
    if (!bytes) return Promise.resolve({ ok: false, status: 404 });
    const exact = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
    return Promise.resolve({ ok: true, status: 200, arrayBuffer: () => Promise.resolve(exact) });
  };
  window.eval(readFileSync(I18N, "utf-8"));
  window.eval(trustedAppSource(trustedIndexBytes));
  await settle();
  return {
    dom,
    window,
    doc: window.document,
    resolveLocale: (locale) => {
      if (!localeResolvers[locale]) die(`no deferred ${locale} locale request is pending`);
      localeResolvers[locale]();
    },
    resolveArtifact: (year) => {
      if (!artifactResolvers[year]) die(`no deferred ${year} artifact request is pending`);
      artifactResolvers[year]();
    },
    artifactFetchCounts,
    fetchTargets,
  };
}

function renderedRows(doc) {
  return Array.from(doc.querySelectorAll("#coverage-body tr[data-status]"));
}

function profileRows(doc) {
  return Array.from(doc.querySelectorAll("#state-profile-table .profile-year-row"));
}

function profileCells(doc, status) {
  return Array.from(doc.querySelectorAll(`#state-profile-table td[data-status="${status}"]`));
}

function select(doc, id, value) {
  const control = doc.getElementById(id);
  control.value = value;
  control.dispatchEvent(new doc.defaultView.Event("change", { bubbles: true }));
}

function assertError(rendered, label) {
  if (!rendered.doc.getElementById("coverage-status").classList.contains("is-error")) {
    die(`${label} did not enter the visible fail-closed state`);
  }
  if (renderedRows(rendered.doc).length !== 0) {
    die(`${label} left public counts visible`);
  }
  if (rendered.doc.getElementById("artifact-download").hasAttribute("href")) {
    die(`${label} left a stale annual download link visible`);
  }
  if (profileRows(rendered.doc).length !== 0 || !rendered.doc.getElementById("state-profile-wrap").hidden) {
    die(`${label} left five-year profile values visible`);
  }
  rendered.dom.window.close();
}

function assertThrows(label, callback) {
  try {
    callback();
  } catch (_error) {
    return;
  }
  die(`${label} was accepted by the closed validator`);
}

async function assertNoAxeViolations(rendered, label) {
  rendered.window.eval(axe.source);
  const results = await rendered.window.axe.run(rendered.doc, {
    resultTypes: ["violations"],
    rules: { "color-contrast": { enabled: false } },
  });
  if (results.violations.length) {
    die(`${label} has axe violations: ${results.violations.map((violation) => violation.id).join(", ")}`);
  }
}

async function assertLocaleRootFollowsLoadedScript() {
  const dom = new JSDOM('<!doctype html><script src="/fallback/i18n.js"></script>', {
    runScripts: "outside-only",
    url: "https://example.test/fars/national/",
  });
  const { window } = dom;
  Object.defineProperty(window.document, "currentScript", {
    configurable: true,
    value: { src: "https://static.example.test/nearmiss/i18n.js?release=reviewed" },
  });
  let requested = "";
  window.fetch = (target) => {
    requested = String(target);
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({}) });
  };
  window.eval(readFileSync(I18N, "utf-8"));
  await window.NearmissI18n.create("web.coverage.").load("en");
  if (requested !== "https://static.example.test/nearmiss/locales/en.json") {
    die(`locale loader ignored the loaded script URL: ${requested}`);
  }
  dom.window.close();
}

async function main() {
  const appSource = readFileSync(APP, "utf-8");
  if (/\b(?:innerHTML|outerHTML|insertAdjacentHTML|document\.write|DOMParser)\b/.test(appSource)) {
    die("national runtime must not reinterpret translated or artifact text as HTML");
  }
  await assertLocaleRootFollowsLoadedScript();
  const apex = new JSDOM(readFileSync(APEX, "utf-8")).window.document;
  const refresh = apex.querySelector('meta[http-equiv="refresh"]');
  if (!refresh || refresh.getAttribute("content") !== "0; url=/fars/national/") {
    die("apex does not immediately redirect to the nationwide evidence ledger");
  }
  if (!apex.querySelector('a[href="/data/published/fars-state-mode-index-v2.json"]')) {
    die("apex has no direct national release-index link");
  }
  if (!apex.querySelector('a[href="/data/published/fars-2024-state-mode-r2.json"]')) {
    die("apex has no direct corrected 2024 evidence link");
  }
  if (!apex.querySelector('a[href="/data/published/fars-release-corrections.json"]')) {
    die("apex has no release-correction ledger link");
  }
  if (!apex.querySelector('a[href="/fars/national/"]')) {
    die("apex fallback does not target the canonical national route");
  }
  if (!apex.querySelector("main")) die("apex fallback content has no main landmark");

  const redirectSource = apex.querySelector("script[data-apex-redirect]")?.textContent;
  if (!redirectSource) die("apex has no strict language-preserving redirect");
  const apexTarget = (search) => {
    let target = "";
    Function("window", "URLSearchParams", redirectSource)(
      { location: { search, replace: (value) => { target = value; } } },
      URLSearchParams
    );
    return target;
  };
  const apexCases = new Map([
    ["?lang=en", "/fars/national/?lang=en"],
    ["?lang=es&state=CA&year=2024", "/fars/national/?lang=es"],
    ["?lang=es&lang=en", "/fars/national/"],
    ["?lang=ES", "/fars/national/"],
    ["?year=2024&state=CA", "/fars/national/"],
  ]);
  for (const [query, expected] of apexCases) {
    if (apexTarget(query) !== expected) {
      die(`apex did not preserve only one strict supported language for ${query}`);
    }
  }

  const coverageSource = new JSDOM(readFileSync(PAGE, "utf-8")).window.document;
  const coverageCanonical = coverageSource.querySelectorAll('link[rel~="canonical"]');
  if (
    coverageCanonical.length !== 1 ||
    coverageCanonical[0].getAttribute("href") !== NATIONAL_CANONICAL
  ) {
    die("nationwide page does not have the one absolute production canonical URL");
  }
  if (coverageSource.querySelector("base")) die("nationwide page relies on a path-rewriting base element");
  if (coverageSource.querySelector(".skip-link")?.getAttribute("href") !== "#main") {
    die("nationwide page skip link no longer targets its main landmark");
  }
  for (const dependency of [
    "/web/style.css",
    "/web/us-coverage.css",
    "/web/us-coverage-studio.css",
    "/web/i18n.js",
    "/web/us-coverage.js",
  ]) {
    if (!coverageSource.querySelector(`[href="${dependency}"], [src="${dependency}"]`)) {
      die(`nationwide page dependency ${dependency} is not root-absolute`);
    }
  }
  if (!coverageSource.querySelector('#artifact-download[href$="fars-2024-state-mode-r2.json"]')) {
    die("nationwide page lost the no-script 2024 artifact fallback");
  }
  if (!coverageSource.querySelector('a[href$="fars-state-mode-index-v2.json"]')) {
    die("nationwide page has no release-index download");
  }
  if (!coverageSource.querySelector('a[href$="fars-release-corrections.json"]')) {
    die("nationwide page has no correction-ledger download");
  }
  if (!coverageSource.querySelector('a[href="/data/published/us-state-boundaries-2024.json"]')) {
    die("nationwide page has no reviewed Census-boundary download");
  }
  const focusModeSource = coverageSource.getElementById("mode-filter");
  const ledgerModeSource = coverageSource.getElementById("ledger-mode-filter");
  if (
    !focusModeSource?.required ||
    Array.from(focusModeSource.options).some((option) => option.value === "") ||
    focusModeSource.value !== "pedalcyclist"
  ) {
    die("visualization focus is not a required specific mode with a pedalcyclist fallback");
  }
  if (
    !ledgerModeSource ||
    !ledgerModeSource.closest(".data-ledger") ||
    ledgerModeSource.options[0]?.value !== "" ||
    coverageSource.querySelector('label[for="ledger-mode-filter"]')?.getAttribute("data-i18n") !==
      "ledger_mode_label"
  ) {
    die("complete ledger does not expose its own all-modes filter");
  }
  for (const [view, hintId] of [
    ["map", "map-keyboard-hint"],
    ["matrix", "matrix-keyboard-hint"],
    ["rank", "rank-keyboard-hint"],
    ["scatter", "scatter-keyboard-hint"],
  ]) {
    const hint = coverageSource.getElementById(hintId);
    if (
      !hint ||
      hint.getAttribute("data-i18n") !== `${view}_keyboard_hint` ||
      !hint.textContent.trim() ||
      hint.classList.contains("visually-hidden")
    ) {
      die(`${view} view does not expose concise visible keyboard instructions`);
    }
  }
  if (!coverageSource.getElementById("matrix-keyboard-hint").textContent.includes("mode filters")) {
    die("matrix keyboard instructions do not distinguish its scroll, filter, and roving-grid stops");
  }
  const comparisonRegionSource = coverageSource.getElementById("state-comparison");
  if (
    comparisonRegionSource.getAttribute("tabindex") !== "0" ||
    comparisonRegionSource.getAttribute("role") !== "region" ||
    comparisonRegionSource.getAttribute("aria-labelledby") !== "compare-heading" ||
    comparisonRegionSource.getAttribute("aria-describedby") !== "compare-intro"
  ) {
    die("state comparison overflow is not exposed as a named keyboard-reachable region");
  }
  for (const button of coverageSource.querySelectorAll("[data-view]")) {
    const view = button.getAttribute("data-view");
    if (button.getAttribute("aria-controls") !== `${view}-panel`) {
      die(`${view} view control is not programmatically related to its panel`);
    }
  }
  for (const id of ["coverage-status", "state-profile-status", "brief-status"]) {
    const status = coverageSource.getElementById(id);
    if (
      !status ||
      status.getAttribute("role") !== "status" ||
      status.getAttribute("aria-live") !== "polite" ||
      status.getAttribute("aria-atomic") !== "true"
    ) {
      die(`${id} does not expose one atomic polite status contract`);
    }
  }
  const studioStyle = readFileSync(STUDIO_STYLE, "utf-8");
  if (
    !studioStyle.includes(".map-state-group:focus .map-state,\n  .plot-point:focus") ||
    !studioStyle.includes("stroke: Highlight;") ||
    !studioStyle.includes(".matrix-cell-button:focus-visible,\n  .rank-item button:focus-visible")
  ) {
    die("forced-colors mode does not retain system-colored focus indicators for dense views");
  }

  const home = new JSDOM(readFileSync(DAVIS_HOME, "utf-8")).window.document;
  const nationalCta = home.querySelector(`.national-cta a[href="${NATIONAL_ROUTE}"]`);
  if (!nationalCta) {
    die("Davis homepage has no prominent link to the nationwide evidence ledger");
  }
  if (
    !home.querySelector(".national-cta").textContent.includes("synthetic demo") ||
    !nationalCta.textContent.includes("2020–2024") ||
    !nationalCta.textContent.includes("nationwide US")
  ) {
    die("Davis CTA does not distinguish synthetic local data from nationwide reviewed evidence");
  }

  if (CHECKED_INDEX_BYTES.byteLength !== 5273 || digest(CHECKED_INDEX_BYTES) !== "594b13a65f5b88661db8acb21c73fc55ddc61ba94e5a659cdd27463c178f50f5") {
    die("checked release index drifted from its reviewed bytes");
  }
  if (
    LEGACY_INDEX_BYTES.byteLength !== 5270 ||
    digest(LEGACY_INDEX_BYTES) !== "64d73ea4f25de4ef1321e6f8bed56215b9585fdc7ee74bc05bf47ec74bedaa48"
  ) {
    die("retained release index drifted from its immutable published bytes");
  }
  if (
    CORRECTION_BYTES.byteLength !== 1078 ||
    digest(CORRECTION_BYTES) !== "783e238ae6eab3404dfcee4b5323c536d6653ac59ea9e6a6beb36fe8d91fb4f6"
  ) {
    die("release correction ledger drifted from its reviewed bytes");
  }
  if (
    CHECKED_BOUNDARY_BYTES.byteLength !== 323232 ||
    digest(CHECKED_BOUNDARY_BYTES) !== "705219b3339077f1d03466391bb286fe7f1841298fc0bcce948de1d8c66df25d"
  ) {
    die("Census state-boundary artifact drifted from its reviewed bytes");
  }
  if (
    CHECKED_INDEX.releases.length !== YEARS.length ||
    JSON.stringify(CHECKED_INDEX.releases.map((release) => release.dataset_year)) !== JSON.stringify(YEARS)
  ) {
    die("checked release index does not declare all five canonical production years");
  }
  for (const release of CHECKED_INDEX.releases) {
    const bytes = CHECKED_ARTIFACT_BYTES_BY_YEAR[release.dataset_year];
    const expected = EXPECTED_ARTIFACT_PINS[release.dataset_year];
    if (
      release.artifact_bytes !== expected[0] ||
      release.artifact_sha256 !== expected[1] ||
      bytes.byteLength !== expected[0] ||
      digest(bytes) !== expected[1]
    ) {
      die(`checked ${release.dataset_year} artifact does not match its release-index pin`);
    }
  }

  for (const locale of ["en", "es"]) {
    const cta = JSON.parse(readFileSync(join(LOCALES, `${locale}.json`), "utf-8"))[
      "web.app.us_coverage_cta"
    ];
    if (
      !cta.includes('href="/fars/national/"') ||
      !cta.includes("2020–2024") ||
      !(locale === "en" ? cta.includes("synthetic demo") : cta.includes("demostración sintética"))
    ) {
      die(`${locale} catalog does not distinguish the Davis demo from national evidence`);
    }
  }

  const canonicalRoute = await boot({
    url: "https://example.test/fars/national/?lang=es",
  });
  if (canonicalRoute.doc.getElementById("coverage-status").classList.contains("is-error")) {
    die("canonical national route did not boot the reviewed release");
  }
  select(canonicalRoute.doc, "state-filter", "CA");
  await settle();
  select(canonicalRoute.doc, "year-filter", "2021");
  await settle();
  canonicalRoute.doc.querySelector('[data-lang="en"]').click();
  await settle();
  if (
    canonicalRoute.window.location.pathname !== NATIONAL_ROUTE ||
    canonicalRoute.doc.getElementById("summary-year").textContent !== "2021" ||
    canonicalRoute.doc.getElementById("state-filter").value !== "CA" ||
    canonicalRoute.doc.documentElement.lang !== "en"
  ) {
    die("canonical route state/year/language changes did not preserve its pathname and state");
  }
  const canonicalFetchTargets = new Set(canonicalRoute.fetchTargets);
  const expectedFetchTargets = new Set([
    "https://example.test/web/locales/en.json",
    "https://example.test/web/locales/es.json",
    "/data/published/fars-state-mode-index-v2.json",
    "/data/published/us-state-boundaries-2024.json",
    ...YEARS.map((year) =>
      `/data/published/fars-${year}-state-mode${year === 2024 ? "-r2" : ""}.json`
    ),
  ]);
  if (!sameRawTargetSet(canonicalFetchTargets, expectedFetchTargets)) {
    die(
      `canonical route used unexpected, off-origin, or route-relative fetches: ${Array.from(canonicalFetchTargets).join(", ")}`
    );
  }
  const indexTarget = "/data/published/fars-state-mode-index-v2.json";
  for (const forbidden of [
    "../data/published/fars-state-mode-index-v2.json",
    "data/published/fars-state-mode-index-v2.json",
    "https://evil.test/data/published/fars-state-mode-index-v2.json",
  ]) {
    const mutated = Array.from(expectedFetchTargets, (target) =>
      target === indexTarget ? forbidden : target
    );
    if (sameRawTargetSet(mutated, expectedFetchTargets)) {
      die(`raw fetch-target gate accepted forbidden target ${forbidden}`);
    }
  }
  await assertNoAxeViolations(canonicalRoute, "canonical national route");
  canonicalRoute.dom.window.close();

  const rendered = await boot();
  const { doc, window } = rendered;
  if (doc.getElementById("coverage-status").classList.contains("is-error")) {
    die("reviewed 2024 release entered the error state");
  }
  const legacyFetchTargets = new Set(rendered.fetchTargets);
  const expectedLegacyFetchTargets = new Set([
    "https://example.test/web/locales/en.json",
    "/data/published/fars-state-mode-index-v2.json",
    "/data/published/fars-2024-state-mode-r2.json",
    "/data/published/us-state-boundaries-2024.json",
  ]);
  if (
    window.location.pathname !== "/web/us-coverage.html" ||
    !sameRawTargetSet(legacyFetchTargets, expectedLegacyFetchTargets)
  ) {
    die("legacy national route did not boot with root-absolute runtime fetches");
  }
  if (renderedRows(doc).length !== CHECKED_ARTIFACT.accounting.state_mode_cell_count) {
    die("the whole-country default did not expose every reviewed state-by-mode row");
  }
  if (!doc.getElementById("state-profile-wrap").hidden) {
    die("the whole-country default exposed a five-year profile before state selection");
  }
  if (!doc.getElementById("coverage-status").textContent.includes("306")) {
    die("the whole-country status does not report all reviewed cells");
  }
  if (doc.querySelector("main > section") !== doc.getElementById("coverage-filters").closest("section")) {
    die("state selection and profile are not the first main-content workflow");
  }
  const stateOptions = Array.from(doc.getElementById("state-filter").options, (option) => option.value);
  if (stateOptions.length !== 52 || stateOptions[0] !== "" || !stateOptions.includes("CA")) {
    die("state selector does not expose one directional option plus 50 states and DC");
  }
  const yearOptions = Array.from(doc.getElementById("year-filter").options, (option) => option.value);
  if (JSON.stringify(yearOptions) !== JSON.stringify(YEARS.map(String))) {
    die(`selector did not expose all published years: ${yearOptions.join(", ")}`);
  }
  const focusModeOptions = Array.from(doc.getElementById("mode-filter").options, (option) => option.value);
  const ledgerModeOptions = Array.from(doc.getElementById("ledger-mode-filter").options, (option) => option.value);
  if (
    JSON.stringify(focusModeOptions) !== JSON.stringify(EXPECTED_MODES) ||
    doc.getElementById("mode-filter").value !== "pedalcyclist" ||
    JSON.stringify(ledgerModeOptions) !== JSON.stringify(["", ...EXPECTED_MODES]) ||
    doc.getElementById("ledger-mode-filter").value !== ""
  ) {
    die("visual focus and ledger mode controls do not expose their distinct defaults and inventories");
  }
  if (doc.getElementById("summary-year").textContent !== "2024") {
    die("reviewed release did not render its selected year");
  }
  if (doc.getElementById("semantic-regime").textContent !== "fars_per_typ_2022_2024_v1") {
    die("reviewed release did not surface its exact semantic regime");
  }
  if (doc.getElementById("release-stage").textContent !== "Annual Report File (ARF)") {
    die("reviewed 2024 release did not surface its exact ARF status");
  }
  if (!doc.getElementById("annual-contract").textContent.includes(CHECKED_RELEASE_2024.contract.contract_sha256)) {
    die("reviewed release did not surface its exact annual contract digest");
  }
  if (!doc.querySelector(".coverage-regime-caution").textContent.includes("2020–2021")) {
    die("page omitted the cross-regime comparison caution");
  }
  if (doc.querySelectorAll('[data-i18n="can_list"] > li').length !== 3) {
    die("safe translation renderer did not preserve the three-item capability list");
  }
  if (doc.querySelectorAll('[data-i18n="cannot_list"] > li').length !== 3) {
    die("safe translation renderer did not preserve the three-item limitation list");
  }
  if (!doc.querySelector('[data-i18n="caveat"] > strong')) {
    die("safe translation renderer did not preserve the count caveat emphasis");
  }
  if (!doc.getElementById("artifact-download").href.endsWith("fars-2024-state-mode-r2.json")) {
    die("reviewed release did not bind its annual download link");
  }
  if (!doc.querySelector('.proof-rail li[data-year="2024"].is-current .proof-result:not(.is-pending)')) {
    die("proof rail did not mark the selected published year");
  }
  if (doc.getElementById("summary-retention").textContent !== "48,154 / 48,524") {
    die("published/total contribution accounting was not rendered from the artifact");
  }
  if (
    doc.querySelectorAll("#us-map .map-state-group").length !== CHECKED_ARTIFACT.accounting.state_count ||
    doc.querySelectorAll("#matrix-body tr").length !== CHECKED_ARTIFACT.accounting.state_count ||
    doc.querySelectorAll("#matrix-body .matrix-cell").length !==
      CHECKED_ARTIFACT.accounting.state_mode_cell_count
  ) {
    die("linked map or matrix did not render the complete national reviewed scope");
  }
  if (
    doc.querySelectorAll('#us-map .map-state-group[tabindex="0"]').length !== 1 ||
    doc.querySelectorAll('#matrix-body .matrix-cell-button[tabindex="0"]').length !== 1 ||
    doc.querySelectorAll('#rank-list button[tabindex="0"]').length !== 1 ||
    doc.querySelectorAll('#scatter-plot .plot-point[tabindex="0"]').length !== 1
  ) {
    die("dense national visualizations do not expose one predictable roving keyboard entry each");
  }
  const visiblePanels = doc.querySelectorAll("[data-panel]:not([hidden])");
  const pressedViews = doc.querySelectorAll('[data-view][aria-pressed="true"]');
  if (
    visiblePanels.length !== 1 ||
    pressedViews.length !== 1 ||
    pressedViews[0].getAttribute("aria-controls") !== visiblePanels[0].id ||
    doc.querySelectorAll("[data-panel][hidden]").length !== 4
  ) {
    die("view switcher does not expose exactly one pressed control and one active panel");
  }
  for (const [selector, hintId] of [
    ["#us-map .map-state-group", "map-keyboard-hint"],
    ["#matrix-body .matrix-cell-button", "matrix-keyboard-hint"],
    ["#rank-list button[data-focus-key]", "rank-keyboard-hint"],
    ["#scatter-plot .plot-point", "scatter-keyboard-hint"],
  ]) {
    const items = Array.from(doc.querySelectorAll(selector));
    if (
      !items.length ||
      !doc.getElementById(hintId).textContent.startsWith("Keyboard:") ||
      items.some((item) => item.getAttribute("aria-describedby") !== hintId)
    ) {
      die(`${hintId} is not associated with every generated roving item`);
    }
  }
  const initialMapFocus = doc.querySelector('#us-map .map-state-group[tabindex="0"]');
  initialMapFocus.focus();
  initialMapFocus.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true }));
  if (
    doc.activeElement === initialMapFocus ||
    !doc.activeElement.classList.contains("map-state-group") ||
    doc.activeElement.getAttribute("tabindex") !== "0"
  ) {
    die("national map arrow-key navigation did not advance its roving focus");
  }
  const boundary = JSON.parse(CHECKED_BOUNDARY_BYTES.toString("utf-8"));
  if (
    doc.getElementById("boundary-source").href !== boundary.source.distribution_url ||
    doc.getElementById("boundary-source").textContent !== boundary.source.name ||
    doc.getElementById("boundary-checksum").textContent !== digest(CHECKED_BOUNDARY_BYTES)
  ) {
    die("national map did not display its reviewed Census source and artifact digest");
  }

  select(doc, "state-filter", "CA");
  await settle();
  if (renderedRows(doc).length !== 6) die("California filter did not render six canonical modes");
  for (const [selector, expectedMode] of [
    ['#us-map .map-state-group[aria-current="true"]', null],
    ['#matrix-body .matrix-cell-button[aria-current="true"]', "pedalcyclist"],
    ['#rank-list button[aria-current="true"]', null],
    ['#scatter-plot .plot-point[aria-current="true"]', null],
  ]) {
    const currentItems = doc.querySelectorAll(selector);
    if (
      currentItems.length !== 1 ||
      currentItems[0].getAttribute("data-state") !== "CA" ||
      (expectedMode && currentItems[0].getAttribute("data-mode") !== expectedMode)
    ) {
      die(`${selector} did not expose the linked selection with aria-current`);
    }
  }
  const comparisonTable = doc.querySelector("#state-comparison table.comparison-table");
  if (
    !comparisonTable ||
    comparisonTable.closest('[role="region"][tabindex="0"]')?.id !== "state-comparison" ||
    !comparisonTable.querySelector("caption")?.textContent.trim() ||
    comparisonTable.querySelectorAll('thead th[scope="col"]').length !== 3 ||
    comparisonTable.querySelectorAll("tbody tr").length !== 6 ||
    comparisonTable.querySelectorAll('tbody th[scope="row"]').length !== 6 ||
    comparisonTable.querySelectorAll('.comparison-track[aria-hidden="true"]').length !== 12 ||
    !comparisonTable.querySelector("thead")?.textContent.includes("California") ||
    !comparisonTable.querySelector("thead")?.textContent.includes("Texas")
  ) {
    die("state comparison is not exposed as a captioned table with scoped state and mode headers");
  }
  if (
    window.location.pathname !== "/web/us-coverage.html" ||
    !window.location.search.includes("state=CA") ||
    !window.location.search.includes("year=2024") ||
    !window.location.search.includes("lang=en")
  ) {
    die("state selection was not persisted with its year and language in the URL");
  }
  if (profileRows(doc).length !== 5 || doc.getElementById("state-profile-wrap").hidden) {
    die("California selection did not render all five exact annual profile rows");
  }
  for (const year of YEARS) {
    if (rendered.artifactFetchCounts[year] !== 1) {
      die(`${year} artifact was fetched ${rendered.artifactFetchCounts[year] || 0} times instead of once`);
    }
    const source = JSON.parse(CHECKED_ARTIFACT_BYTES_BY_YEAR[year].toString("utf-8"));
    const california = source.states.find((state) => state.state_abbreviation === "CA");
    const renderedYear = doc.querySelector(`#state-profile-table tr[data-year="${year}"]`);
    const cells = Array.from(renderedYear.querySelectorAll("td[data-status]"));
    if (cells.length !== 6) die(`${year} profile row did not preserve six canonical modes`);
    california.cells.forEach((result, index) => {
      if (cells[index].dataset.status !== result.status) die(`${year} profile status drifted from the artifact`);
      if (result.status === "published" && cells[index].textContent.trim() !== result.crash_count.toLocaleString("en-US")) {
        die(`${year} profile count drifted from the exact artifact`);
      }
    });
  }
  const earlyLabel = doc.querySelector("#profile-early-body .profile-regime-label").textContent;
  const lateLabel = doc.querySelector("#profile-late-body .profile-regime-label").textContent;
  if (!earlyLabel.includes("2020–2021") || !lateLabel.includes("2022–2024")) {
    die("profile did not explicitly label both semantic-regime groups");
  }
  for (const body of doc.querySelectorAll("#state-profile-table tbody")) {
    const groupLabel = body.querySelector('th[scope="rowgroup"]');
    if (!groupLabel || body.getAttribute("aria-labelledby") !== groupLabel.id) {
      die("semantic-regime row group is not explicitly labeled for assistive technology");
    }
  }
  const profileText = doc.getElementById("state-profile").textContent.toLowerCase();
  if (
    doc.querySelector("#state-profile svg, #state-profile canvas, #state-profile tfoot") ||
    /\b(risk|rate|rank|ranking|total|change)\b|%/.test(profileText)
  ) {
    die("profile introduced a chart, aggregation, comparison, or risk framing outside scope");
  }
  await assertNoAxeViolations(rendered, "rendered five-year profile");

  select(doc, "status-filter", "published");
  if (renderedRows(doc).length !== 6) die("California published-status filter did not retain six rows");
  select(doc, "status-filter", "");
  select(doc, "mode-filter", "pedestrian");
  if (
    renderedRows(doc).length !== 6 ||
    window.NearmissUSCoverage.getState().primaryMode !== "pedestrian" ||
    doc.querySelectorAll("#matrix-body .matrix-cell.is-filtered").length !== 0 ||
    !window.location.search.includes("mode=pedestrian")
  ) {
    die("visualization focus incorrectly filtered the complete ledger or evidence matrix");
  }
  const matrixFirstRow = doc.getElementById("matrix-body").firstElementChild;
  const urlBeforeLedgerFilter = window.location.href;
  select(doc, "ledger-mode-filter", "motorcyclist");
  if (
    renderedRows(doc).length !== 1 ||
    window.NearmissUSCoverage.getState().primaryMode !== "pedestrian" ||
    doc.getElementById("mode-filter").value !== "pedestrian" ||
    doc.getElementById("matrix-body").firstElementChild !== matrixFirstRow ||
    window.location.href !== urlBeforeLedgerFilter
  ) {
    die("ledger mode filter changed visualization focus, rerendered the matrix, or entered the URL");
  }
  select(doc, "ledger-mode-filter", "");
  if (renderedRows(doc).length !== 6) die("all-modes ledger default did not restore the selected-state rows");
  doc.querySelector('[data-focus-key="matrix-mode:motorcyclist"]').click();
  if (
    window.NearmissUSCoverage.getState().primaryMode !== "motorcyclist" ||
    doc.getElementById("mode-filter").value !== "motorcyclist" ||
    renderedRows(doc).length !== 6 ||
    doc.querySelectorAll("#matrix-body .matrix-cell.is-filtered").length !== 0
  ) {
    die("matrix mode click did not change visual focus without filtering the evidence scope");
  }

  select(doc, "state-filter", "VT");
  await settle();
  const withheldAnnual = renderedRows(doc).filter((row) => row.dataset.status === "suppressed_or_zero");
  if (!withheldAnnual.length) die("Vermont fixture no longer exercises selected-year suppression");
  for (const row of withheldAnnual) {
    if (row.querySelectorAll("th, td")[4].textContent.trim() !== "—") {
      die("a selected-year withheld cell rendered a numeric count");
    }
  }
  const withheldProfile = profileCells(doc, "suppressed_or_zero");
  if (!withheldProfile.length) die("five-year profile fixture no longer exercises suppression");
  for (const withheld of withheldProfile) {
    if (/\d/.test(withheld.textContent)) die("a five-year withheld cell rendered a numeric value");
  }

  const form = doc.getElementById("coverage-filters");
  if (form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }))) {
    die("filter form submit was not prevented");
  }
  doc.querySelector('[data-lang="es"]').click();
  await settle();
  if (doc.documentElement.lang !== "es") die("Spanish control did not update document language");
  for (const hintId of [
    "map-keyboard-hint",
    "matrix-keyboard-hint",
    "rank-keyboard-hint",
    "scatter-keyboard-hint",
  ]) {
    if (!doc.getElementById(hintId).textContent.startsWith("Teclado:")) {
      die(`${hintId} did not render its visible Spanish keyboard instructions`);
    }
  }
  if (!doc.getElementById("matrix-keyboard-hint").textContent.includes("filtros de modo")) {
    die("Spanish matrix instructions do not distinguish its separate keyboard stops");
  }
  if (doc.getElementById("release-stage").textContent !== "Archivo del informe anual (ARF)") {
    die("Spanish locale rerender did not surface the exact ARF status");
  }
  if (!doc.getElementById("coverage-caption").textContent.includes("celdas")) {
    die("Spanish result did not use the gettext-backed catalog");
  }
  if (!doc.querySelector(".coverage-regime-caution").textContent.includes("régimen semántico")) {
    die("Spanish catalog omitted the semantic-regime caution");
  }
  if (
    doc.querySelector('label[for="mode-filter"]').textContent !== "Enfoque de visualización" ||
    doc.querySelector('label[for="ledger-mode-filter"]').textContent !== "Filtrar registro por modo" ||
    doc.getElementById("ledger-mode-filter").options[0].textContent !== "Todos los modos"
  ) {
    die("Spanish catalog did not distinguish visualization focus from ledger filtering");
  }
  if (
    !doc.querySelector("#profile-early-body .profile-regime-label").textContent.includes("codificación anterior") ||
    !doc.getElementById("profile-caption").textContent.includes("Vermont")
  ) {
    die("Spanish locale rerender did not update the loaded profile and seam labels");
  }

  const currentRelease = CHECKED_RELEASE_2024;
  assertThrows("unexpected private cell field", () => {
    const changed = clone(CHECKED_ARTIFACT);
    changed.states[0].cells[0].raw_case_ids = ["private-case-id"];
    window.NearmissUSCoverage.validateArtifact(changed, currentRelease, CHECKED_INDEX.contract);
  });
  assertThrows("changed publication floor", () => {
    const changed = clone(CHECKED_ARTIFACT);
    changed.metric.effective_k = 11;
    window.NearmissUSCoverage.validateArtifact(changed, currentRelease, CHECKED_INDEX.contract);
  });
  doc.getElementById("coverage-filters").dispatchEvent(new window.Event("reset", { bubbles: true }));
  await settle();
  if (
    window.location.search.includes("state=") ||
    window.location.search.includes("mode=") ||
    renderedRows(doc).length !== CHECKED_ARTIFACT.accounting.state_mode_cell_count ||
    !doc.getElementById("state-profile-wrap").hidden ||
    doc.getElementById("mode-filter").value !== "pedalcyclist" ||
    doc.getElementById("ledger-mode-filter").value !== ""
  ) {
    die("reset did not restore pedalcyclist focus, the all-modes ledger, and the whole-country URL");
  }
  rendered.dom.window.close();
  console.log("us-coverage contract: whole-country ledger, exact five-year profile, suppression, seam, and EN/ES passed.");

  const multiyear = await boot();
  const multiyearOptions = Array.from(multiyear.doc.getElementById("year-filter").options, (option) => option.value);
  if (JSON.stringify(multiyearOptions) !== JSON.stringify(YEARS.map(String))) {
    die("production release index did not populate all five years in ascending order");
  }
  select(multiyear.doc, "state-filter", "CA");
  await settle();
  for (const year of YEARS) {
    select(multiyear.doc, "year-filter", String(year));
    await settle();
    if (multiyear.doc.getElementById("coverage-status").classList.contains("is-error")) {
      die(`canonical ${year} selector transition failed its fixed-year contract`);
    }
    if (multiyear.doc.getElementById("summary-year").textContent !== String(year)) {
      die(`year selector left stale metadata while loading ${year}`);
    }
    if (
      renderedRows(multiyear.doc).length !== 6 ||
      renderedRows(multiyear.doc).some((row) => row.firstElementChild.textContent !== String(year))
    ) {
      die(`year selector mixed rows while loading ${year}`);
    }
  }
  select(multiyear.doc, "year-filter", "2021");
  await settle();
  if (multiyear.doc.getElementById("summary-year").textContent !== "2021") {
    die("year selector left stale 2024 metadata visible");
  }
  if (multiyear.doc.getElementById("semantic-regime").textContent !== "fars_per_typ_2020_2021_v1") {
    die("year selector left the later semantic regime visible for the early-regime release");
  }
  if (multiyear.doc.getElementById("state-code-system").textContent !== "nhtsa_fars_state_2021") {
    die("year selector left a stale state-code contract visible");
  }
  const release2021 = CHECKED_INDEX.releases.find((release) => release.dataset_year === 2021);
  if (!multiyear.doc.getElementById("annual-contract").textContent.includes(release2021.contract.contract_sha256)) {
    die("year selector left a stale annual contract digest visible");
  }
  if (!multiyear.window.location.search.includes("year=2021")) {
    die("year selector did not preserve the selected release in the URL");
  }
  if (!multiyear.doc.getElementById("artifact-download").href.endsWith("fars-2021-state-mode.json")) {
    die("year selector left a stale artifact download link");
  }
  if (!multiyear.doc.querySelector('.proof-rail li[data-year="2021"].is-current .proof-result:not(.is-pending)')) {
    die("year selector did not update release proof status");
  }
  multiyear.doc.querySelector('[data-lang="es"]').click();
  await settle();
  const shareUrl = multiyear.window.location.href;
  if (!shareUrl.includes("year=2021") || !shareUrl.includes("lang=es") || !shareUrl.includes("state=CA")) {
    die("locale switch did not preserve language, selected year, and validated state in the URL");
  }
  multiyear.dom.window.close();
  const reloaded = await boot({ url: shareUrl });
  if (
    reloaded.doc.documentElement.lang !== "es" ||
    reloaded.doc.getElementById("summary-year").textContent !== "2021" ||
    reloaded.doc.getElementById("state-filter").value !== "CA" ||
    profileRows(reloaded.doc).length !== 5
  ) {
    die("shared year/language/state URL did not survive reload");
  }
  reloaded.dom.window.close();

  const studioLink = await boot({
    url:
      "https://example.test/fars/national/?year=2022&lang=en&view=scatter&mode=motorcyclist&secondary=pedestrian&state=TX&a=TX&b=CA&scale=log&saved=CA,TX,NY",
  });
  const linkedState = studioLink.window.NearmissUSCoverage.getState();
  if (
    studioLink.doc.getElementById("summary-year").textContent !== "2022" ||
    linkedState.view !== "scatter" ||
    linkedState.primaryMode !== "motorcyclist" ||
    linkedState.secondaryMode !== "pedestrian" ||
    linkedState.selectedState !== "TX" ||
    linkedState.compareA !== "TX" ||
    linkedState.compareB !== "CA" ||
    linkedState.scale !== "log" ||
    linkedState.saved.join(",") !== "CA,TX,NY" ||
    studioLink.doc.getElementById("mode-filter").value !== "motorcyclist" ||
    studioLink.doc.getElementById("ledger-mode-filter").value !== "" ||
    studioLink.doc.getElementById("scatter-panel").hidden ||
    studioLink.doc.querySelectorAll("#brief-items .brief-card").length !== 3
  ) {
    die("validated studio deep link did not restore its exact year and linked visible state");
  }
  const linkedPoint = studioLink.doc.querySelector(
    '#scatter-plot [data-focus-key="scatter:TX"]'
  );
  linkedPoint.focus();
  linkedPoint.dispatchEvent(
    new studioLink.window.KeyboardEvent("keydown", { key: "Enter", bubbles: true })
  );
  await settle();
  if (studioLink.doc.activeElement?.getAttribute("data-focus-key") !== "scatter:TX") {
    die("scatter keyboard activation lost focus during its linked-view redraw");
  }
  const compareFromInspector = studioLink.doc.querySelector(".inspector-actions button:first-child");
  compareFromInspector.focus();
  compareFromInspector.click();
  if (
    studioLink.window.NearmissUSCoverage.getState().view !== "compare" ||
    studioLink.doc.getElementById("compare-panel").hidden ||
    studioLink.doc.getElementById("compare-a").value !== "TX" ||
    studioLink.doc.activeElement !== studioLink.doc.getElementById("compare-a") ||
    !studioLink.window.location.search.includes("view=compare")
  ) {
    die("inspector comparison action did not switch views and restore focus to the first state");
  }
  let removeButtons = Array.from(studioLink.doc.querySelectorAll("#brief-items .remove-brief"));
  removeButtons[2].click();
  if (
    studioLink.doc.activeElement !== studioLink.doc.querySelectorAll("#brief-items .remove-brief")[1] ||
    !studioLink.doc.activeElement.getAttribute("aria-label").includes("Texas")
  ) {
    die("removing the last brief card did not focus the previous remove action");
  }
  removeButtons = Array.from(studioLink.doc.querySelectorAll("#brief-items .remove-brief"));
  removeButtons[0].click();
  if (
    studioLink.doc.activeElement !== studioLink.doc.querySelector("#brief-items .remove-brief") ||
    !studioLink.doc.activeElement.getAttribute("aria-label").includes("Texas")
  ) {
    die("removing a brief card did not focus the next remove action");
  }
  studioLink.doc.activeElement.click();
  if (
    studioLink.doc.querySelector("#brief-items .remove-brief") ||
    studioLink.doc.activeElement !== studioLink.doc.getElementById("clear-brief")
  ) {
    die("removing the only brief card did not focus the clear-brief action");
  }
  studioLink.dom.window.close();

  const localeRace = await boot({
    deferredLocales: ["es"],
    url: "https://example.test/web/us-coverage.html?year=2023&state=TX",
  });
  localeRace.doc.querySelector('[data-lang="es"]').click();
  localeRace.doc.querySelector('[data-lang="en"]').click();
  await settle();
  if (
    localeRace.doc.documentElement.lang !== "en" ||
    !localeRace.window.location.search.includes("year=2023") ||
    !localeRace.window.location.search.includes("state=TX") ||
    !localeRace.window.location.search.includes("lang=en")
  ) {
    die("latest locale click did not win while preserving the selected year");
  }
  localeRace.resolveLocale("es");
  await settle();
  if (localeRace.doc.documentElement.lang !== "en" || !localeRace.window.location.search.includes("lang=en")) {
    die("late Spanish response overwrote the newer English locale selection");
  }
  localeRace.dom.window.close();
  console.log("us-coverage contract: five real years, state URL sharing, and latest-click locale ordering passed.");

  const yearRace = await boot({ deferredArtifacts: [2020] });
  select(yearRace.doc, "year-filter", "2020");
  select(yearRace.doc, "year-filter", "2021");
  await settle();
  if (yearRace.doc.getElementById("summary-year").textContent !== "2021") {
    die("latest selected year did not render while an older artifact was pending");
  }
  yearRace.resolveArtifact(2020);
  await settle();
  if (
    yearRace.doc.getElementById("summary-year").textContent !== "2021" ||
    !yearRace.window.location.search.includes("year=2021")
  ) {
    die("late annual completion overwrote the latest selected year");
  }
  yearRace.dom.window.close();

  const parallelBoot = await boot({
    deferredArtifacts: [2020, 2024],
    url: "https://example.test/web/us-coverage.html?state=CA",
  });
  for (const year of YEARS) {
    if (parallelBoot.artifactFetchCounts[year] !== 1) {
      die("state URL did not start all five deduplicated annual loads in parallel");
    }
  }
  parallelBoot.resolveArtifact(2020);
  parallelBoot.resolveArtifact(2024);
  await settle();
  if (renderedRows(parallelBoot.doc).length !== 6 || profileRows(parallelBoot.doc).length !== 5) {
    die("parallel state URL boot did not converge on both verified views");
  }
  parallelBoot.dom.window.close();

  const stateRace = await boot({ deferredArtifacts: [2020] });
  select(stateRace.doc, "state-filter", "CA");
  select(stateRace.doc, "state-filter", "NY");
  await settle();
  if (
    !stateRace.doc.getElementById("state-profile-wrap").hidden ||
    stateRace.doc.getElementById("state-profile").getAttribute("aria-busy") !== "true"
  ) {
    die("state profile exposed a stale state while an annual artifact was pending");
  }
  stateRace.resolveArtifact(2020);
  await settle();
  if (
    !stateRace.doc.getElementById("profile-caption").textContent.includes("New York") ||
    stateRace.doc.getElementById("profile-caption").textContent.includes("California") ||
    !stateRace.window.location.search.includes("state=NY") ||
    stateRace.doc.getElementById("state-profile").getAttribute("aria-busy") !== "false"
  ) {
    die("late profile completion overwrote the latest selected state");
  }
  for (const year of YEARS) {
    if (stateRace.artifactFetchCounts[year] !== 1) {
      die(`state race fetched the shared ${year} artifact more than once`);
    }
  }
  stateRace.dom.window.close();

  const transientFailureYears = [2020];
  const retryableProfile = await boot({
    failArtifactYears: transientFailureYears,
    url: "https://example.test/web/us-coverage.html?year=2024&state=CA",
  });
  if (!retryableProfile.doc.getElementById("state-profile-status").classList.contains("is-error")) {
    die("transient historical failure did not clear the profile");
  }
  transientFailureYears.length = 0;
  select(retryableProfile.doc, "state-filter", "NY");
  await settle();
  if (
    !retryableProfile.doc.getElementById("profile-caption").textContent.includes("New York") ||
    retryableProfile.artifactFetchCounts[2020] !== 2
  ) {
    die("a rejected historical fetch promise was not safely retryable");
  }
  retryableProfile.dom.window.close();

  const changedHistorical = Buffer.from(CHECKED_ARTIFACT_BYTES_BY_YEAR[2020]);
  const historicalDigit = changedHistorical.indexOf(Buffer.from('"case_count":'));
  if (historicalDigit < 0) die("could not construct historical artifact drift fixture");
  changedHistorical[historicalDigit + '"case_count":'.length] = "9".charCodeAt(0);
  const isolatedProfileFailure = await boot({
    artifacts: { ...CHECKED_ARTIFACT_BYTES_BY_YEAR, 2020: changedHistorical },
    url: "https://example.test/web/us-coverage.html?year=2024&state=CA",
  });
  if (
    isolatedProfileFailure.doc.getElementById("coverage-status").classList.contains("is-error") ||
    renderedRows(isolatedProfileFailure.doc).length !== 6 ||
    !isolatedProfileFailure.doc.getElementById("state-profile-status").classList.contains("is-error") ||
    !isolatedProfileFailure.doc.getElementById("state-profile-wrap").hidden
  ) {
    die("historical artifact drift did not fail closed only within the five-year profile");
  }
  isolatedProfileFailure.dom.window.close();
  console.log("us-coverage contract: deduplicated profile promises, latest-state ordering, and isolated historical failure passed.");

  assertError(
    await boot({ url: "https://example.test/web/us-coverage.html?year=2019" }),
    "unknown requested year"
  );
  assertError(
    await boot({ url: "https://example.test/web/us-coverage.html?year=2024&year=2020" }),
    "ambiguous requested year"
  );
  assertError(
    await boot({ url: "https://example.test/web/us-coverage.html?state=ca" }),
    "malformed requested state"
  );
  assertError(
    await boot({ url: "https://example.test/web/us-coverage.html?state=ZZ" }),
    "unknown requested state"
  );
  assertError(
    await boot({ url: "https://example.test/web/us-coverage.html?state=CA&state=NY" }),
    "ambiguous requested state"
  );
  assertError(
    await boot({ url: "https://example.test/web/us-coverage.html?lang=en&lang=es" }),
    "ambiguous requested language"
  );
  const studioParameterCases = [
    ["view=globe", "unsupported requested view"],
    ["view=map&view=rank", "ambiguous requested view"],
    ["mode=bicycle", "unsupported requested mode"],
    ["mode=pedestrian&mode=pedalcyclist", "ambiguous requested mode"],
    ["secondary=bicycle", "unsupported requested secondary mode"],
    ["secondary=pedestrian&secondary=motorcyclist", "ambiguous requested secondary mode"],
    ["scale=sqrt", "unsupported requested scale"],
    ["scale=linear&scale=log", "ambiguous requested scale"],
    ["a=ca", "unsupported requested comparison state A"],
    ["a=CA&a=NY", "ambiguous requested comparison state A"],
    ["b=ZZ", "unsupported requested comparison state B"],
    ["b=CA&b=NY", "ambiguous requested comparison state B"],
    ["saved=CA,CA", "invalid requested saved-state list"],
    ["saved=CA&saved=NY", "ambiguous requested saved-state list"],
  ];
  for (const [query, label] of studioParameterCases) {
    assertError(
      await boot({ url: `https://example.test/web/us-coverage.html?year=2024&${query}` }),
      label
    );
  }
  const oneYearIndex = releaseSubsetIndex([2024]);
  assertError(
    await boot({
      indexBytes: oneYearIndex,
      trustedIndexBytes: oneYearIndex,
      url: "https://example.test/web/us-coverage.html?year=2021",
    }),
    "unpublished requested year"
  );
  assertError(
    await boot({ indexBytes: Buffer.concat([CHECKED_INDEX_BYTES.subarray(0, -1), Buffer.from(" \n")]) }),
    "release-index digest drift"
  );

  const changedArtifact = Buffer.from(CHECKED_ARTIFACT_BYTES);
  const digit = changedArtifact.indexOf(Buffer.from('"case_count":36127'));
  if (digit < 0) die("could not construct same-length artifact drift fixture");
  changedArtifact[digit + '"case_count":'.length + 4] = "8".charCodeAt(0);
  assertError(await boot({ artifacts: { 2024: changedArtifact } }), "annual artifact digest drift");

  const leaked = clone(CHECKED_ARTIFACT);
  leaked.states[0].cells[0].raw_case_ids = ["private-case-id"];
  const leakedBytes = canonical(leaked);
  const leakedIndex = rebindArtifact(2024, leakedBytes);
  assertError(
    await boot({
      indexBytes: leakedIndex,
      trustedIndexBytes: leakedIndex,
      artifacts: { 2024: leakedBytes },
    }),
    "hash-bound artifact with a private field"
  );

  const wrongStage = clone(CHECKED_ARTIFACT);
  wrongStage.source.release_stage = "final";
  const wrongStageBytes = canonical(wrongStage);
  const wrongStageIndex = rebindArtifact(2024, wrongStageBytes);
  assertError(
    await boot({
      indexBytes: wrongStageIndex,
      trustedIndexBytes: wrongStageIndex,
      artifacts: { 2024: wrongStageBytes },
    }),
    "hash-bound artifact with the superseded release stage"
  );

  const wrongRevision = clone(CHECKED_INDEX);
  const wrongRevision2024 = wrongRevision.releases.find((release) => release.dataset_year === 2024);
  wrongRevision2024.contract.contract_revision = 1;
  const wrongRevisionBytes = canonical(wrongRevision);
  assertError(
    await boot({ indexBytes: wrongRevisionBytes, trustedIndexBytes: wrongRevisionBytes }),
    "current index with the superseded contract revision"
  );

  const changedBoundary = Buffer.from(CHECKED_BOUNDARY_BYTES);
  const boundaryNameOffset = changedBoundary.indexOf(Buffer.from('"Alabama"'));
  if (boundaryNameOffset < 0) die("could not construct Census boundary drift fixture");
  changedBoundary[boundaryNameOffset + 1] = "X".charCodeAt(0);
  assertError(
    await boot({ boundaryBytes: changedBoundary }),
    "Census boundary artifact digest drift"
  );

  assertError(await boot({ disableCrypto: true }), "missing Web Crypto digest support");
  assertError(await boot({ failFetch: true }), "release-index fetch failure");

  assertError(
    await boot({ url: "https://example.test/web/us-coverage.html?lang=ar" }),
    "unsupported requested language"
  );
  console.log("us-coverage contract: unknown years, drift, private fields, fetch, locale, and crypto fail closed.");
}

main().catch((error) => die(error && error.stack ? error.stack : String(error)));
