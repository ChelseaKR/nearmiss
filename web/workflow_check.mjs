import { readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { JSDOM, VirtualConsole } from "jsdom";

const here = fileURLToPath(new URL(".", import.meta.url));

function die(message) {
  console.error(`workflow contract: FAIL — ${message}`);
  process.exit(1);
}

function load(htmlName, scriptNames, url) {
  const dom = new JSDOM(readFileSync(join(here, htmlName), "utf-8"), {
    runScripts: "outside-only",
    pretendToBeVisual: true,
    url,
    virtualConsole: new VirtualConsole(),
  });
  for (const scriptName of [scriptNames].flat()) {
    const source = readFileSync(join(here, scriptName), "utf-8");
    if (/\b(?:innerHTML|outerHTML|insertAdjacentHTML|document\.write|DOMParser)\b/.test(source)) {
      die(`${scriptName} must not reinterpret file, query, or generated text as HTML`);
    }
    dom.window.eval(source);
  }
  dom.window.document.dispatchEvent(new dom.window.Event("DOMContentLoaded"));
  return dom;
}

const studio = load("studio.html", "studio.js", "https://example.test/studio/");
const studioApi = studio.window.NearmissStudio;
if (!studioApi) die("Studio does not expose its testable local-readiness contract");

const csv = [
  "report_id,latitude,longitude,occurred_at,hazard_type,corridor_id",
  '1,38.5,-121.7,2026-05-01,"close, pass",alpha',
  "2,38.6,-121.8,2026-05-02,sightline,alpha",
  "3,38.7,-121.9,2026-05-03,surface,alpha",
].join("\n");
const rows = studioApi.parseCsv(csv);
if (rows.length !== 3 || rows[0].hazard_type !== "close, pass") {
  die("CSV parser did not preserve rows and quoted fields");
}

const tierOne = studioApi.assessReadiness(rows, {
  hasExposure: false,
  hasOfficial: false,
  hasReview: false,
});
if (tierOne.tier !== 1 || tierOne.findings.length !== 7 || tierOne.suppression.withheldRows !== 0) {
  die("community-report readiness did not resolve to the bounded Tier 1 result");
}

// #155 — the scenario from the issue: ten meaningless rows (one point, one date,
// no hazard type, no corridor) with every declaration ticked. Nothing here can be
// a rate, so nothing here may be Tier 2, and the Tier 2/3 sentences must refuse
// to render without a computed basis.
const meaningless = Array.from({ length: 10 }, () => ({
  latitude: "0.0",
  longitude: "0.0",
  occurred_at: "2026-01-01",
}));
const declaredOnly = studioApi.assessReadiness(meaningless, {
  hasExposure: true,
  hasOfficial: true,
  hasReview: true,
});
if (declaredOnly.tier !== 1 || declaredOnly.basis !== null) {
  die("three unverified declarations produced a Tier 2/3 result without any computed rate (#155)");
}
const rateFinding = declaredOnly.findings.find((finding) => finding.label === "Rate at the named place");
if (!rateFinding || rateFinding.ready || !/No denominator column/.test(rateFinding.detail)) {
  die("readiness did not say that the denominator column is missing");
}
for (const tier of [2, 3]) {
  let refused = false;
  try {
    studioApi.compileClaim(tier, "Main Street", "staff_memo");
  } catch (error) {
    refused = /computed rate basis/.test(error.message);
  }
  if (!refused) die(`Tier ${tier} sentence rendered without a computed basis (#155)`);
  try {
    studioApi.compileClaim(tier, "Main Street", "staff_memo", { count: 10, rate: 5 });
    die(`Tier ${tier} sentence accepted a partial basis`);
  } catch (error) {
    if (!/computed rate basis/.test(error.message)) throw error;
  }
}

// The JavaScript rate port must agree with honest_rates.rates on the committed
// vectors (tests/test_studio_rates_port.py keeps those vectors equal to Python).
const vectors = JSON.parse(
  readFileSync(join(here, "..", "tests", "fixtures", "rates", "interval_vectors.json"), "utf-8")
);
const close = (actual, expected) =>
  Math.abs(actual - expected) <= 1e-12 * Math.max(1, Math.abs(expected));
const rates = studioApi.rates;
if (!close(rates.Z95, vectors.z95)) die("Z95 differs from honest_rates");
for (const v of vectors.poisson_ci) {
  const [low, high] = rates.poissonCi(v.count);
  if (!close(low, v.low) || !close(high, v.high)) die(`poissonCi(${v.count}) differs from Python`);
}
for (const v of vectors.quasi_poisson_ci) {
  const [low, high] = rates.quasiPoissonCi(v.count, v.dispersion);
  if (!close(low, v.low) || !close(high, v.high)) {
    die(`quasiPoissonCi(${v.count}, ${v.dispersion}) differs from Python`);
  }
}
for (const v of vectors.rate_with_ci) {
  const [rate, low, high] = rates.rateWithCi(v.count, v.exposure, v.per, rates.Z95, v.dispersion);
  if (!close(rate, v.rate) || !close(low, v.low) || !close(high, v.high)) {
    die(`rateWithCi(${v.count}, ${v.exposure}, ${v.per}, ${v.dispersion}) differs from Python`);
  }
}
for (const v of vectors.wilson_ci) {
  const [low, high] = rates.wilsonCi(v.successes, v.trials);
  if (!close(low, v.low) || !close(high, v.high)) {
    die(`wilsonCi(${v.successes}, ${v.trials}) differs from Python`);
  }
}
for (const v of vectors.pearson_dispersion) {
  if (!close(rates.pearsonDispersion(v.counts, v.exposures), v.phi)) {
    die(`pearsonDispersion(${JSON.stringify(v.counts)}) differs from Python`);
  }
}
let rejectedExposure = false;
try {
  rates.rateWithCi(5, 0);
} catch (_error) {
  rejectedExposure = true;
}
if (!rejectedExposure) die("a rate was produced without a positive denominator");

// A file that carries a per-segment denominator: Tier 2 is computed, carries its
// numbers, and hands the basis to the dossier. Segment "alpha" has 7 reports over
// 400 bike_count; the other two segments pool to 3 reports over 3,500.
function segmentRows(spec) {
  const rows = [];
  for (const [segment, count, exposure] of spec) {
    for (let index = 0; index < count; index += 1) {
      rows.push({
        latitude: String(38.5 + rows.length / 100),
        longitude: String(-121.7 - rows.length / 100),
        occurred_at: `2026-05-${String((rows.length % 28) + 1).padStart(2, "0")}`,
        hazard_type: "close_pass",
        corridor_id: segment,
        bike_count: exposure,
      });
    }
  }
  return rows;
}
const withDenominator = segmentRows([["alpha", 7, "400"], ["beta", 2, "2000"], ["gamma", 1, "1500"]]);
if (studioApi.segmentValues(withDenominator, "corridor_id").join(",") !== "alpha,beta,gamma") {
  die("segment identifiers were not read from the file");
}
const unchosen = studioApi.assessReadiness(withDenominator, {
  hasExposure: true,
  hasOfficial: false,
  hasReview: true,
});
if (unchosen.tier !== 1 || !/Choose which segment/.test(unchosen.summary)) {
  die("a rate was attached to a place the file did not identify");
}
const tierTwo = studioApi.assessReadiness(withDenominator, {
  segment: "alpha",
  hasExposure: true,
  hasOfficial: false,
  hasReview: true,
});
const expectedAlpha = rates.rateWithCi(7, 400, 1000, rates.Z95, 1);
if (
  tierTwo.tier !== 2 ||
  !tierTwo.basis ||
  tierTwo.basis.segment !== "alpha" ||
  tierTwo.basis.count !== 7 ||
  tierTwo.basis.exposure !== 400 ||
  tierTwo.basis.unit !== "bike_count" ||
  !close(tierTwo.basis.rate, expectedAlpha[0]) ||
  !close(tierTwo.basis.low, expectedAlpha[1]) ||
  !close(tierTwo.basis.high, expectedAlpha[2]) ||
  tierTwo.basis.comparisonSegments !== 2 ||
  !close(tierTwo.basis.comparisonRate, (3 / 3500) * 1000) ||
  !(tierTwo.basis.dispersion > 1) ||
  typeof tierTwo.basis.widenedLow !== "number"
) {
  die("a computed denominator did not produce a Tier 2 basis with the engine's rate and interval");
}
const computedClaim = studioApi.compileClaim(2, "Alpha Street", "staff_memo", tierTwo.basis);
if (
  !/^The observed report rate at Alpha Street is elevated in the stated observation window: 7 reports over 400 bike_count \(17\.5 per 1000; 95% interval 7\.01–36\.04\) against 0\.86 per 1000 pooled across the other 2 segments in the same file\.$/.test(computedClaim.claim) ||
  !/Computed in this browser from the file's bike_count column for segment alpha/.test(computedClaim.computed) ||
  !/Sensitivity: widened by √φ/.test(computedClaim.computed) ||
  !/Declared by the preparer, not verified here: denominator alignment/.test(computedClaim.declared)
) {
  die(`Tier 2 sentence did not carry its count, denominator, interval, comparison, and provenance: ${computedClaim.claim}`);
}
const tierThree = studioApi.assessReadiness(withDenominator, {
  segment: "alpha",
  hasExposure: true,
  hasOfficial: true,
  hasReview: true,
});
if (tierThree.tier !== 3) die("a computed Tier 2 plus a declared official source did not resolve to Tier 3");
const triangulated = studioApi.compileClaim(3, "Alpha Street", "grant", tierThree.basis);
if (
  !triangulated.claim.startsWith("If the declared independent outcome source agrees on review, it supports prioritizing Alpha Street") ||
  !/agreement of the independent outcome source/.test(triangulated.declared)
) {
  die("Tier 3 sentence asserted agreement that nothing evaluated");
}

// Declarations gate but never create the tier.
for (const [label, options] of [
  ["no alignment declaration", { segment: "alpha", hasExposure: false, hasReview: true }],
  ["no review declaration", { segment: "alpha", hasExposure: true, hasReview: false }],
]) {
  const gated = studioApi.assessReadiness(withDenominator, { hasOfficial: false, ...options });
  if (gated.tier !== 1 || gated.basis !== null) die(`Tier 2 was issued with ${label}`);
}

// The interval covering the comparison, a count under the small-sample threshold,
// a count under the privacy floor, and an inconsistent denominator each stop at
// Tier 1 and say why.
const covered = studioApi.assessReadiness(segmentRows([["alpha", 5, "1000"], ["beta", 4, "1000"], ["gamma", 5, "1000"]]), {
  segment: "alpha",
  hasExposure: true,
  hasOfficial: false,
  hasReview: true,
});
if (covered.tier !== 2 - 1 || !/covers the pooled rate/.test(covered.summary)) {
  die("an interval that covers the comparison was called elevated");
}
const small = studioApi.assessReadiness(segmentRows([["alpha", 4, "100"], ["beta", 2, "5000"]]), {
  segment: "alpha",
  hasExposure: true,
  hasOfficial: false,
  hasReview: true,
});
if (small.tier !== 1 || !/below the small-sample threshold of 5/.test(small.summary)) {
  die("a count below the small-sample threshold carried an elevated-rate claim");
}
const inconsistent = segmentRows([["alpha", 7, "400"], ["beta", 2, "2000"]]);
inconsistent[0].bike_count = "401";
const disagreeing = studioApi.assessReadiness(inconsistent, {
  segment: "alpha",
  hasExposure: true,
  hasOfficial: false,
  hasReview: true,
});
if (disagreeing.tier !== 1 || !/rows disagree on its denominator/.test(disagreeing.summary)) {
  die("a segment whose rows disagree on the denominator was given a rate");
}
const sample = studioApi.assessReadiness(studioApi.sampleRows, {
  segment: "mercer-8",
  hasExposure: true,
  hasOfficial: true,
  hasReview: true,
});
if (sample.tier !== 1 || !/below the small-sample threshold/.test(sample.summary)) {
  die("the safe sample reached an elevated-rate tier");
}

const claim = studioApi.compileClaim(1, "Mercer Avenue", "field_audit");
if (
  claim.claim !== "Repeated community reports at Mercer Avenue warrant investigation." ||
  !claim.cannot.includes("caused") ||
  !claim.next.includes("investigation")
) {
  die("claim compiler lost its permitted language, boundary, or next action");
}

if (
  studio.window.document.querySelector('input[type="file"]')?.getAttribute("accept") !==
    ".csv,.json,text/csv,application/json" ||
  !studio.window.document.querySelector("#readiness-status[aria-live]") ||
  !studio.window.document.querySelector('a[href="/dossier/"]') ||
  !studio.window.document.querySelector("#claim-tier[disabled]") ||
  !studio.window.document.querySelector("#generate-claim[disabled]") ||
  !studio.window.document.querySelector("#place-segment[disabled]") ||
  !studio.window.document.querySelector("#claim-provenance")
) {
  die("Studio lost its local-file, status, readiness-bound tier, or dossier handoff controls");
}
studio.window.close();

const dossier = load(
  "dossier.html",
  ["studio.js", "dossier.js"],
  "https://example.test/dossier/?source=atlas&year=2024&mode=pedalcyclist&states=CA,TX"
);
const dossierApi = dossier.window.NearmissDossier;
const atlasDraft = dossierApi.dossierFromQuery(
  "?source=atlas&year=2024&mode=pedalcyclist&states=CA,TX"
);
if (
  atlasDraft.source !== "atlas" ||
  atlasDraft.tier !== 0 ||
  !atlasDraft.claim.includes("do not establish local risk") ||
  !atlasDraft.sourceLabel.includes("CA,TX")
) {
  die("Atlas handoff did not remain a Tier 0 official-context draft");
}

const rejected = dossierApi.dossierFromQuery(
  "?source=atlas&year=2024&mode=pedalcyclist&states=CA,CA"
);
if (!rejected || rejected.sourceLabel.includes("CA,CA")) {
  die("Dossier accepted a duplicated or ambiguous saved-state list");
}

const inventedState = dossierApi.dossierFromQuery(
  "?source=atlas&year=2024&mode=pedalcyclist&states=ZZ"
);
if (!inventedState || inventedState.sourceLabel.includes("ZZ")) {
  die("Dossier accepted a non-jurisdiction Atlas state code");
}

const handoffId = "1234567890abcdef";
const handoffBasis = tierTwo.basis;
const handoffValue = JSON.stringify({
  schema: studioApi.handoffSchema,
  tier: 2,
  place: "Mercer Avenue",
  use: "field_audit",
  basis: handoffBasis,
});
const handoffStore = {
  getItem(key) {
    return key === `${studioApi.handoffPrefix}${handoffId}` ? handoffValue : null;
  },
};
const studioDraft = dossierApi.dossierFromQuery(
  `?source=studio&handoff=${handoffId}`,
  handoffStore
);
if (
  studioDraft.tier !== 2 ||
  studioDraft.place !== "Mercer Avenue" ||
  studioDraft.claim !== studioApi.compileClaim(2, "Mercer Avenue", "field_audit", handoffBasis).claim ||
  !/7 reports over 400 bike_count/.test(studioDraft.claim) ||
  !studioDraft.declared
) {
  die("Studio handoff did not regenerate the canonical tier-bounded dossier draft with its computed basis");
}

// A Tier 2 handoff without a computed basis (the pre-#155 v1 shape, or a tampered
// session entry) must not become a dossier draft that asserts a rate.
for (const [label, value] of [
  ["missing basis", { schema: studioApi.handoffSchema, tier: 2, place: "Mercer Avenue", use: "field_audit" }],
  ["v1 schema", { schema: "nearmiss.studio_handoff.v1", tier: 2, place: "Mercer Avenue", use: "field_audit" }],
  ["basis below the comparison", { schema: studioApi.handoffSchema, tier: 2, place: "Mercer Avenue", use: "field_audit", basis: { ...handoffBasis, comparisonRate: handoffBasis.low + 1 } }],
  ["basis under the small-sample threshold", { schema: studioApi.handoffSchema, tier: 3, place: "Mercer Avenue", use: "field_audit", basis: { ...handoffBasis, count: 4 } }],
]) {
  const store = { getItem: () => JSON.stringify(value) };
  if (dossierApi.dossierFromQuery(`?source=studio&handoff=${handoffId}`, store) !== null) {
    die(`Dossier accepted a Tier 2/3 handoff with ${label}`);
  }
}
const tierOneHandoff = {
  getItem: () => JSON.stringify({ schema: studioApi.handoffSchema, tier: 1, place: "Mercer Avenue", use: "field_audit", basis: null }),
};
const tierOneDraft = dossierApi.dossierFromQuery(`?source=studio&handoff=${handoffId}`, tierOneHandoff);
if (!tierOneDraft || tierOneDraft.tier !== 1 || !/warrant investigation/.test(tierOneDraft.claim)) {
  die("a Tier 1 handoff, which needs no basis, was rejected");
}

const forgedClaim = dossierApi.dossierFromQuery(
  "?source=studio&tier=3&place=Mercer%20Avenue&claim=This%20is%20dangerous&action=Install%20barriers",
  handoffStore
);
if (forgedClaim !== null) {
  die("Dossier accepted tier, claim, or action text from a crafted URL");
}

if (
  !dossier.window.document.querySelector(".evidence-chain") ||
  !dossier.window.document.querySelector(".verification-panel") ||
  !dossier.window.document.querySelector("#copy-citation") ||
  !dossier.window.document.querySelector('script[src="/web/studio.js"]') ||
  dossier.window.document.getElementById("verify-tier").textContent !== "0 · Coverage gap"
) {
  die("Dossier lost its evidence chain, canonical compiler, visible verification, citation action, or Atlas tier");
}
dossier.window.close();

const home = new JSDOM(readFileSync(join(here, "..", "index.html"), "utf-8")).window.document;
for (const href of ["/studio/", "/dossier/", "/fars/national/"]) {
  if (!home.querySelector(`a[href="${href}"]`)) die(`gateway does not link to ${href}`);
}
if (!home.querySelector(".gateway-dossier-preview")) {
  die("gateway does not show the promised dossier output before the machinery");
}

console.log("workflow contract: local readiness, bounded claims, dossier verification, and Atlas handoff passed.");
