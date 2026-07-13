// Browser contract for the hash-bound, five-year nationwide FARS ledger.
import { createHash, webcrypto } from "node:crypto";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..");
const APEX = join(repoRoot, "index.html");
const PAGE = join(here, "us-coverage.html");
const DAVIS_HOME = join(here, "index.html");
const APP = join(here, "us-coverage.js");
const I18N = join(here, "i18n.js");
const LOCALES = join(here, "locales");
const INDEX = join(repoRoot, "data", "published", "fars-state-mode-index.json");
const YEARS = [2020, 2021, 2022, 2023, 2024];
const ARTIFACTS = Object.fromEntries(
  YEARS.map((year) => [year, join(repoRoot, "data", "published", `fars-${year}-state-mode.json`)])
);

const CHECKED_INDEX_BYTES = readFileSync(INDEX);
const CHECKED_ARTIFACT_BYTES_BY_YEAR = Object.fromEntries(
  YEARS.map((year) => [year, readFileSync(ARTIFACTS[year])])
);
const CHECKED_ARTIFACT_BYTES = CHECKED_ARTIFACT_BYTES_BY_YEAR[2024];
const CHECKED_INDEX = JSON.parse(CHECKED_INDEX_BYTES.toString("utf-8"));
const CHECKED_ARTIFACT = JSON.parse(CHECKED_ARTIFACT_BYTES.toString("utf-8"));
const CHECKED_RELEASE_2024 = CHECKED_INDEX.releases.find((release) => release.dataset_year === 2024);
const EXPECTED_ARTIFACT_PINS = {
  2020: [27589, "db4c50d998d20bc2f341b1943c883f6d6d3c805db4bb7117564619119499290c"],
  2021: [27630, "de7406ca0980e9d092eb25a230fe17fb2500f07b3b36f781dc3e4b35b7983168"],
  2022: [27622, "39f8e39fd52cc17abf07377dc460bc9545e05b82525740d8718c57e0f6fc4af8"],
  2023: [27636, "a0ddddc47f7c9ca70b823083f9f13831844b23fc45113321a3408a894eb98ade"],
  2024: [27590, "29b5dc2673987cc7bedd0a83b2147e724e1fb2a2cb1458053af3d017ac8d6578"],
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
  Object.defineProperty(window, "crypto", { value: disableCrypto ? {} : webcrypto, configurable: true });
  window.TextDecoder = TextDecoder;
  window.fetch = (requested) => {
    const target = String(requested);
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
    if (target.endsWith("fars-state-mode-index.json")) {
      bytes = indexBytes;
    } else {
      const match = target.match(/fars-([0-9]{4})-state-mode\.json$/);
      bytes = match ? artifacts[Number(match[1])] : undefined;
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
  };
}

function renderedRows(doc) {
  return Array.from(doc.querySelectorAll("#coverage-body tr[data-status]"));
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

async function main() {
  const apex = new JSDOM(readFileSync(APEX, "utf-8")).window.document;
  const refresh = apex.querySelector('meta[http-equiv="refresh"]');
  if (!refresh || refresh.getAttribute("content") !== "0; url=web/us-coverage.html") {
    die("apex does not immediately redirect to the nationwide evidence ledger");
  }
  if (!apex.querySelector('a[href="data/published/fars-state-mode-index.json"]')) {
    die("apex has no direct national release-index link");
  }
  if (!apex.querySelector('a[href="data/published/fars-2024-state-mode.json"]')) {
    die("apex lost the backward-compatible 2024 evidence link");
  }
  if (!apex.querySelector("main")) die("apex fallback content has no main landmark");

  const coverageSource = new JSDOM(readFileSync(PAGE, "utf-8")).window.document;
  const coverageCanonical = coverageSource.querySelectorAll('link[rel~="canonical"]');
  if (
    coverageCanonical.length !== 1 ||
    coverageCanonical[0].getAttribute("href") !== "https://nearmiss.report/web/us-coverage.html"
  ) {
    die("nationwide page does not have the one absolute production canonical URL");
  }
  if (!coverageSource.querySelector('#artifact-download[href$="fars-2024-state-mode.json"]')) {
    die("nationwide page lost the no-script 2024 artifact fallback");
  }
  if (!coverageSource.querySelector('a[href$="fars-state-mode-index.json"]')) {
    die("nationwide page has no release-index download");
  }

  const home = new JSDOM(readFileSync(DAVIS_HOME, "utf-8")).window.document;
  if (!home.querySelector('.national-cta a[href="us-coverage.html"]')) {
    die("Davis homepage has no prominent link to the nationwide evidence ledger");
  }

  if (CHECKED_INDEX_BYTES.byteLength !== 5270 || digest(CHECKED_INDEX_BYTES) !== "64d73ea4f25de4ef1321e6f8bed56215b9585fdc7ee74bc05bf47ec74bedaa48") {
    die("checked release index drifted from its reviewed bytes");
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

  const rendered = await boot();
  const { doc, window } = rendered;
  if (doc.getElementById("coverage-status").classList.contains("is-error")) {
    die("reviewed 2024 release entered the error state");
  }
  if (renderedRows(doc).length !== 306) {
    die(`reviewed 2024 release rendered ${renderedRows(doc).length} rows, expected 306`);
  }
  const yearOptions = Array.from(doc.getElementById("year-filter").options, (option) => option.value);
  if (JSON.stringify(yearOptions) !== JSON.stringify(YEARS.map(String))) {
    die(`selector did not expose all published years: ${yearOptions.join(", ")}`);
  }
  if (doc.getElementById("summary-year").textContent !== "2024") {
    die("reviewed release did not render its selected year");
  }
  if (doc.getElementById("semantic-regime").textContent !== "fars_per_typ_2022_2024_v1") {
    die("reviewed release did not surface its exact semantic regime");
  }
  if (!doc.getElementById("annual-contract").textContent.includes(CHECKED_RELEASE_2024.contract.contract_sha256)) {
    die("reviewed release did not surface its exact annual contract digest");
  }
  if (!doc.querySelector(".coverage-regime-caution").textContent.includes("2020–2021")) {
    die("page omitted the cross-regime comparison caution");
  }
  if (!doc.getElementById("artifact-download").href.endsWith("fars-2024-state-mode.json")) {
    die("reviewed release did not bind its annual download link");
  }
  if (!doc.querySelector('.proof-rail li[data-year="2024"].is-current .proof-result:not(.is-pending)')) {
    die("proof rail did not mark the selected published year");
  }
  if (doc.querySelectorAll('#coverage-body tr[data-status="published"]').length !== 206) {
    die("reviewed release did not render exactly 206 published cells");
  }
  const withheld = Array.from(doc.querySelectorAll('#coverage-body tr[data-status="suppressed_or_zero"]'));
  if (withheld.length !== 100) die("reviewed release did not render exactly 100 withheld cells");
  for (const row of withheld) {
    if (row.querySelectorAll("th, td")[4].textContent.trim() !== "—") {
      die("a withheld cell rendered a numeric count");
    }
  }
  if (doc.getElementById("summary-retention").textContent !== "48,154 / 48,524") {
    die("published/total contribution accounting was not rendered from the artifact");
  }

  select(doc, "status-filter", "published");
  if (renderedRows(doc).length !== 206) die("published-status filter did not render 206 rows");
  select(doc, "status-filter", "");
  select(doc, "state-filter", "CA");
  if (renderedRows(doc).length !== 6) die("California filter did not render six canonical modes");
  select(doc, "state-filter", "");
  select(doc, "mode-filter", "pedestrian");
  if (renderedRows(doc).length !== 51) die("pedestrian filter did not render all jurisdictions");

  const form = doc.getElementById("coverage-filters");
  if (form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }))) {
    die("filter form submit was not prevented");
  }
  doc.querySelector('[data-lang="es"]').click();
  await settle();
  if (doc.documentElement.lang !== "es") die("Spanish control did not update document language");
  if (!doc.getElementById("coverage-caption").textContent.includes("celdas")) {
    die("Spanish result did not use the gettext-backed catalog");
  }
  if (!doc.querySelector(".coverage-regime-caution").textContent.includes("régimen semántico")) {
    die("Spanish catalog omitted the semantic-regime caution");
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
  rendered.dom.window.close();
  console.log("us-coverage contract: reviewed 2024 index, artifact, filters, accounting, and EN/ES passed.");

  const multiyear = await boot();
  const multiyearOptions = Array.from(multiyear.doc.getElementById("year-filter").options, (option) => option.value);
  if (JSON.stringify(multiyearOptions) !== JSON.stringify(YEARS.map(String))) {
    die("production release index did not populate all five years in ascending order");
  }
  for (const year of YEARS) {
    select(multiyear.doc, "year-filter", String(year));
    await settle();
    if (multiyear.doc.getElementById("coverage-status").classList.contains("is-error")) {
      die(`canonical ${year} selector transition failed its fixed-year contract`);
    }
    if (multiyear.doc.getElementById("summary-year").textContent !== String(year)) {
      die(`year selector left stale metadata while loading ${year}`);
    }
    if (renderedRows(multiyear.doc).some((row) => row.firstElementChild.textContent !== String(year))) {
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
  if (!shareUrl.includes("year=2021") || !shareUrl.includes("lang=es")) {
    die("locale switch did not preserve both whitelisted language and selected year in the URL");
  }
  multiyear.dom.window.close();
  const reloaded = await boot({ url: shareUrl });
  if (
    reloaded.doc.documentElement.lang !== "es" ||
    reloaded.doc.getElementById("summary-year").textContent !== "2021"
  ) {
    die("shared year/language URL did not survive reload");
  }
  reloaded.dom.window.close();

  const localeRace = await boot({
    deferredLocales: ["es"],
    url: "https://example.test/web/us-coverage.html?year=2023",
  });
  localeRace.doc.querySelector('[data-lang="es"]').click();
  localeRace.doc.querySelector('[data-lang="en"]').click();
  await settle();
  if (
    localeRace.doc.documentElement.lang !== "en" ||
    !localeRace.window.location.search.includes("year=2023") ||
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
  console.log("us-coverage contract: five real years, URL sharing, and latest-click locale ordering passed.");

  assertError(
    await boot({ url: "https://example.test/web/us-coverage.html?year=2019" }),
    "unknown requested year"
  );
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

  assertError(await boot({ disableCrypto: true }), "missing Web Crypto digest support");
  assertError(await boot({ failFetch: true }), "release-index fetch failure");

  const unsupportedLocale = await boot({
    url: "https://example.test/web/us-coverage.html?lang=ar",
  });
  if (unsupportedLocale.doc.documentElement.lang !== "en") {
    die("unsupported locale mislabeled English fallback content");
  }
  unsupportedLocale.dom.window.close();
  console.log("us-coverage contract: unknown years, drift, private fields, fetch, locale, and crypto fail closed.");
}

main().catch((error) => die(error && error.stack ? error.stack : String(error)));
