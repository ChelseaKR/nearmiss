// Browser contract for the public nationwide FARS evidence ledger. It boots the
// real checked-in artifact in jsdom, proves all 306 state-mode cells render,
// exercises the filters and bilingual seam, and verifies fail-closed behavior
// for source-pin changes or leaked/private fields.
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const here = dirname(fileURLToPath(import.meta.url));
const repoRoot = join(here, "..");
const PAGE = join(here, "us-coverage.html");
const HOME = join(here, "index.html");
const APP = join(here, "us-coverage.js");
const I18N = join(here, "i18n.js");
const LOCALES = join(here, "locales");
const ARTIFACT = join(repoRoot, "data", "published", "fars-2024-state-mode.json");

const clone = (value) => JSON.parse(JSON.stringify(value));

function die(message) {
  console.error(`us-coverage contract: FAIL — ${message}`);
  process.exit(1);
}

async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
  await new Promise((resolve) => setTimeout(resolve, 0));
}

async function boot(data, { failFetch = false, disableCrypto = false, url = "https://example.test/web/us-coverage.html" } = {}) {
  const artifactBytes = Buffer.isBuffer(data) ? data : Buffer.from(JSON.stringify(data), "utf-8");
  const dom = new JSDOM(readFileSync(PAGE, "utf-8"), {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url,
    virtualConsole: new VirtualConsole(),
  });
  const { window } = dom;
  Object.defineProperty(window, "crypto", { value: disableCrypto ? {} : webcrypto, configurable: true });
  window.TextDecoder = TextDecoder;
  window.fetch = (url) => {
    const target = String(url);
    const locale = target.match(/locales\/([a-z]{2,3})\.json$/);
    if (locale) {
      const catalog = JSON.parse(readFileSync(join(LOCALES, `${locale[1]}.json`), "utf-8"));
      return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve(catalog) });
    }
    if (failFetch) return Promise.resolve({ ok: false, status: 503 });
    const exact = artifactBytes.buffer.slice(
      artifactBytes.byteOffset,
      artifactBytes.byteOffset + artifactBytes.byteLength
    );
    return Promise.resolve({ ok: true, status: 200, arrayBuffer: () => Promise.resolve(exact) });
  };
  window.eval(readFileSync(I18N, "utf-8"));
  window.eval(readFileSync(APP, "utf-8"));
  await settle();
  return { dom, window, doc: window.document };
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
  rendered.dom.window.close();
}

async function rejectedMutation(base, label, mutate) {
  const changed = clone(base);
  mutate(changed);
  assertError(await boot(changed), label);
}

function rejectedValidator(window, base, label, mutate) {
  const changed = clone(base);
  mutate(changed);
  try {
    window.NearmissUSCoverage.validateArtifact(changed);
  } catch (_error) {
    return;
  }
  die(`${label} was accepted by the closed semantic validator`);
}

async function main() {
  const home = new JSDOM(readFileSync(HOME, "utf-8")).window.document;
  if (!home.querySelector('.national-cta a[href="us-coverage.html"]')) {
    die("Davis homepage has no prominent link to the nationwide evidence ledger");
  }
  const artifactBytes = readFileSync(ARTIFACT);
  if (artifactBytes.byteLength !== 27590) {
    die(`real artifact is ${artifactBytes.byteLength} bytes, expected the reviewed 27590`);
  }
  const artifact = JSON.parse(artifactBytes.toString("utf-8"));
  const expectedAccounting = {
    case_count: 36127,
    state_count: 51,
    state_mode_cell_count: 306,
    published_cell_count: 206,
    suppressed_or_zero_cell_count: 100,
    positive_candidate_cell_count: 292,
    positive_suppressed_cell_count: 86,
    crash_contribution_total: 48524,
    published_crash_contribution_total: 48154,
    suppressed_crash_contribution_total: 370,
  };
  for (const [field, expected] of Object.entries(expectedAccounting)) {
    if (artifact.accounting[field] !== expected) {
      die(`real artifact accounting.${field} is ${artifact.accounting[field]}, expected ${expected}`);
    }
  }

  const rendered = await boot(artifactBytes);
  const { doc, window } = rendered;
  if (doc.getElementById("coverage-status").classList.contains("is-error")) {
    die("real artifact entered the error state");
  }
  if (renderedRows(doc).length !== 306) die(`real artifact rendered ${renderedRows(doc).length} rows, expected 306`);
  if (doc.querySelectorAll('#coverage-body tr[data-status="published"]').length !== 206) {
    die("real artifact did not render exactly 206 published cells");
  }
  const withheld = Array.from(doc.querySelectorAll('#coverage-body tr[data-status="suppressed_or_zero"]'));
  if (withheld.length !== 100) die(`real artifact rendered ${withheld.length} withheld cells, expected 100`);
  for (const row of withheld) {
    const cells = row.querySelectorAll("th, td");
    if (!cells[3].textContent.includes("Not published (suppressed or zero)")) {
      die("a withheld cell lost its explicit suppressed-or-zero publication status");
    }
    if (cells[4].textContent.trim() !== "—") {
      die(`a withheld count rendered as "${cells[4].textContent.trim()}" instead of an em dash`);
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
  if (renderedRows(doc).length !== 51) die("pedestrian filter did not render all 51 jurisdictions");

  const form = doc.getElementById("coverage-filters");
  const allowedNavigation = form.dispatchEvent(new window.Event("submit", { bubbles: true, cancelable: true }));
  if (allowedNavigation) die("filter form submit was not prevented");

  doc.querySelector('[data-lang="es"]').click();
  await settle();
  if (doc.documentElement.lang !== "es") die("Spanish language control did not update document language");
  select(doc, "mode-filter", "other_road_user");
  if (!doc.getElementById("coverage-caption").textContent.includes("celdas")) {
    die("Spanish filter result did not use the gettext-backed catalog");
  }
  rejectedValidator(window, artifact, "numeric source-native state code", (data) => {
    data.states[0].state_code = 1;
  });
  rejectedValidator(window, artifact, "changed publication floor", (data) => {
    data.metric.effective_k = 11;
  });
  rejectedValidator(window, artifact, "unexpected private cell field", (data) => {
    data.states[0].cells[0].raw_case_ids = ["private-case-id"];
  });
  rendered.dom.window.close();
  console.log("us-coverage contract: real artifact rendered 306 cells; filters, accounting, and EN/ES passed.");

  const unsupportedLocale = await boot(artifactBytes, {
    url: "https://example.test/web/us-coverage.html?lang=ar",
  });
  if (unsupportedLocale.doc.documentElement.lang !== "en") {
    die("unsupported ?lang value mislabeled English fallback content");
  }
  unsupportedLocale.dom.window.close();

  await rejectedMutation(artifact, "unexpected top-level private field", (data) => {
    data.source_lineage = { raw_path: "/private/fars.csv" };
  });
  await rejectedMutation(artifact, "unexpected private cell field", (data) => {
    data.states[0].cells[0].raw_case_ids = ["private-case-id"];
  });
  await rejectedMutation(artifact, "changed artifact type", (data) => {
    data.artifact_type = "nearmiss.private.fars_state_context";
  });
  await rejectedMutation(artifact, "changed source URL", (data) => {
    data.source.distribution_url = "https://example.test/unreviewed.zip";
  });
  await rejectedMutation(artifact, "changed source checksum", (data) => {
    data.source.raw_sha256 = "0".repeat(64);
  });
  await rejectedMutation(artifact, "changed crosswalk checksum", (data) => {
    data.geography.state_crosswalk_sha256 = "0".repeat(64);
  });
  await rejectedMutation(artifact, "changed reviewed accounting", (data) => {
    data.accounting.case_count += 1;
  });
  await rejectedMutation(artifact, "changed publication floor", (data) => {
    data.metric.effective_k = 11;
  });
  await rejectedMutation(artifact, "count added to withheld cell", (data) => {
    const cell = data.states.flatMap((state) => state.cells).find((candidate) => candidate.status === "suppressed_or_zero");
    cell.crash_count = 0;
  });
  const swapped = clone(artifact);
  const published = swapped.states.flatMap((state) => state.cells).filter((cell) => cell.status === "published");
  published[0].crash_count -= 1;
  published[1].crash_count += 1;
  assertError(await boot(swapped), "compensating published-cell swap");
  assertError(await boot(artifactBytes, { disableCrypto: true }), "missing Web Crypto digest support");
  assertError(await boot(artifactBytes, { failFetch: true }), "artifact fetch failure");
  console.log("us-coverage contract: byte drift, private fields, unsupported locale, zero leakage, and missing crypto all fail closed.");
}

main().catch((error) => die(error && error.stack ? error.stack : String(error)));
