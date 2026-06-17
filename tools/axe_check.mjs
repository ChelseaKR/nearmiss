// Deeper automated accessibility check: run axe-core against the static web page
// in jsdom (no browser needed). This complements tools/a11y_check.py (structural)
// and CI; the full conformance picture still requires manual NVDA/VoiceOver review
// (see docs/accessibility/ACR.md). Exit 1 on any violation.
//
// Usage:  cd web && npm ci && npm run axe      (or: node tools/axe_check.mjs web/index.html)
import { readFileSync } from "node:fs";
import { JSDOM } from "jsdom";
import axe from "axe-core";

const file = process.argv[2] || "index.html";
const html = readFileSync(file, "utf-8");

const dom = new JSDOM(html, { runScripts: "outside-only", pretendToBeVisual: true });
const { window } = dom;
window.eval(axe.source);

const results = await window.axe.run(window.document, { resultTypes: ["violations"] });

if (results.violations.length > 0) {
  for (const v of results.violations) {
    console.log(`axe: [${v.impact}] ${v.id} — ${v.help}`);
    for (const node of v.nodes) {
      console.log(`   at: ${node.target.join(" ")}`);
    }
  }
  console.log(`\naxe: ${results.violations.length} violation(s) in ${file}.`);
  process.exit(1);
}
console.log(`axe: no violations in ${file} (static DOM). Manual SR review still required.`);
