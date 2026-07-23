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
if (tierOne.tier !== 1 || tierOne.findings.length !== 6 || tierOne.suppression.withheldRows !== 0) {
  die("community-report readiness did not resolve to the bounded Tier 1 result");
}

const tenRows = Array.from({ length: 12 }, (_, index) => ({
  latitude: String(38.5 + index / 100),
  longitude: String(-121.7 - index / 100),
  occurred_at: `2026-05-${String(index + 1).padStart(2, "0")}`,
  hazard_type: "close_pass",
  corridor_id: index < 6 ? "alpha" : "beta",
}));
const tierThree = studioApi.assessReadiness(tenRows, {
  hasExposure: true,
  hasOfficial: true,
  hasReview: true,
});
if (tierThree.tier !== 3) die("reviewed, exposed, triangulated inputs did not resolve to Tier 3");

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
  !studio.window.document.querySelector("#generate-claim[disabled]")
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
const handoffValue = JSON.stringify({
  schema: "nearmiss.studio_handoff.v1",
  tier: 2,
  place: "Mercer Avenue",
  use: "field_audit",
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
  studioDraft.claim !== "The observed report rate at Mercer Avenue is elevated in the stated observation window."
) {
  die("Studio handoff did not regenerate the canonical tier-bounded dossier draft");
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
