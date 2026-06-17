// Deeper automated accessibility check: run axe-core against the static web page
// in jsdom (no browser needed). This complements tools/a11y_check.py (structural)
// and CI; the full conformance picture still requires manual NVDA/VoiceOver review
// (see docs/accessibility/ACR.md). Exit 1 on any violation.
//
// Lives in web/ so Node resolves web/node_modules (axe-core, jsdom).
// Usage:  cd web && npm install && npm run axe   (or: node web/axe_check.mjs index.html)
import { readFileSync } from "node:fs";
import { JSDOM, VirtualConsole } from "jsdom";
import axe from "axe-core";

const file = process.argv[2] || "index.html";
const html = readFileSync(file, "utf-8");

// A bare VirtualConsole keeps jsdom's "not implemented" notices (e.g. canvas)
// out of the output; they are irrelevant to the checks we run here.
const dom = new JSDOM(html, {
  runScripts: "outside-only",
  pretendToBeVisual: true,
  virtualConsole: new VirtualConsole(),
});
const { window } = dom;
window.eval(axe.source);

const results = await window.axe.run(window.document, {
  resultTypes: ["violations"],
  // jsdom has no layout or canvas, so RENDERED color-contrast cannot be computed
  // here. Contrast is instead checked against the documented CSS values and in the
  // manual review (docs/accessibility/ACR.md); disabling it keeps this run honest
  // and deterministic rather than silently meaningless.
  rules: { "color-contrast": { enabled: false } },
});

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
console.log(`axe: no violations in ${file} (static DOM; color-contrast checked separately).`);
