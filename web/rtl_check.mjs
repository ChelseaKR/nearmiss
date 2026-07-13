// G10 RTL layout smoke: load the static page in jsdom with the document forced to
// right-to-left (dir="rtl") and fail if its inline or locally linked authored CSS
// carries direction-unsafe horizontal styles. This is the RTL companion to
// axe_check.mjs (structural a11y) and tools/a11y_check.py; like those it runs in
// jsdom with no browser, so it checks the *authored* DOM, not rendered geometry.
//
// nearmiss ships no RTL end-user locale today, but the brief's gettext seam makes
// locale N+1 (incl. Arabic/Hebrew/Farsi) a translate-only step — so this gate keeps
// the web shell honest now: physical left/right properties are a common thing
// that silently breaks when html[dir] flips. Use CSS logical
// properties (margin-inline-start, inset-inline-*, text-align: start/end) instead,
// which mirror automatically under [dir="rtl"].
//
// Lives in web/ so Node resolves web/node_modules (jsdom).
// Usage:  cd web && npm install && npm run rtl   (or: node web/rtl_check.mjs index.html)
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

const file = process.argv[2] || "index.html";
const html = readFileSync(file, "utf-8");

// A bare VirtualConsole keeps jsdom's "not implemented" notices out of the output.
const dom = new JSDOM(html, {
  runScripts: "outside-only",
  pretendToBeVisual: true,
  virtualConsole: new VirtualConsole(),
});
const { window } = dom;
const { document } = window;

// Force RTL, the way a right-to-left locale would.
document.documentElement.setAttribute("dir", "rtl");

// (1) The page parses and html[dir] is respected (it round-trips through the DOM).
if (!document.documentElement || !document.body) {
  console.error(`rtl: ${file} did not parse into a document with <html> and <body>.`);
  process.exit(1);
}
if (document.documentElement.getAttribute("dir") !== "rtl") {
  console.error(`rtl: html[dir] was not respected in ${file}.`);
  process.exit(1);
}

// (2) No element may pin itself to a physical side via an inline style — those do
// not mirror when the document direction flips. Logical properties are the fix.
// (CSS files are reviewed separately; jsdom has no layout to resolve them here, so
// this scan is scoped to inline styles, which are unambiguous in the static DOM.)
const UNSAFE = [
  /(?:^|[;\s])(?:margin|padding|border|inset)-(?:left|right)\s*:/i,
  /(?:^|[;\s])(?:left|right)\s*:/i,
  /(?:^|[;\s])float\s*:\s*(?:left|right)/i,
  /(?:^|[;\s])(?:text-align|clear)\s*:\s*(?:left|right)/i,
];

const violations = [];
for (const el of document.querySelectorAll("[style]")) {
  const style = el.getAttribute("style") || "";
  const hit = UNSAFE.find((re) => re.test(style));
  if (hit) {
    const where = el.id ? `#${el.id}` : el.tagName.toLowerCase();
    violations.push({ kind: "inline style", where, style: style.trim() });
  }
}

// (3) Scan authored, locally linked stylesheets too. Vendored third-party CSS
// (Leaflet) is excluded; it is upstream code and is isolated from our authored
// layout rules. Physical horizontal declarations in the site CSS are rejected.
const CSS_UNSAFE = [
  /(?:^|[;{\s])(?:margin|padding|border)-(?:left|right)(?:-[\w-]+)?\s*:/i,
  /(?:^|[;{\s])(?:left|right)\s*:/i,
  /(?:^|[;{\s])float\s*:\s*(?:left|right)\b/i,
  /(?:^|[;{\s])(?:text-align|clear)\s*:\s*(?:left|right)\b/i,
];

for (const link of document.querySelectorAll('link[rel~="stylesheet"][href]')) {
  const href = link.getAttribute("href") || "";
  const clean = href.split(/[?#]/, 1)[0];
  if (!clean || /^(?:[a-z]+:|\/\/|\/)/i.test(clean) || clean.split("/").includes("vendor")) {
    continue;
  }
  const cssPath = resolve(dirname(file), clean);
  const css = readFileSync(cssPath, "utf-8").replace(/\/\*[\s\S]*?\*\//g, (comment) =>
    comment.replace(/[^\n]/g, " ")
  );
  css.split(/\r?\n/).forEach((line, index) => {
    if (CSS_UNSAFE.some((re) => re.test(line))) {
      violations.push({
        kind: "linked CSS",
        where: `${clean}:${index + 1}`,
        style: line.trim(),
      });
    }
  });
}

if (violations.length > 0) {
  for (const v of violations) {
    console.log(`rtl: direction-unsafe ${v.kind} at ${v.where} — "${v.style}"`);
    console.log(`     use a CSS logical property (e.g. margin-inline-start, inset-inline-*, text-align: start/end).`);
  }
  console.log(`\nrtl: ${violations.length} direction-unsafe authored style(s) in ${file}.`);
  process.exit(1);
}
console.log(`rtl: ${file} parses under dir="rtl"; inline and linked authored CSS use direction-safe properties.`);
