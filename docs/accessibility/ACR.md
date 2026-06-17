# Accessibility Conformance Report (ACR)

## Voluntary Product Accessibility Template (VPAT) Version 2.5 — Revised Section 508 Edition

> **Status at v0.1.0 — implementation exists, passes the structural gate, and now passes an automated
> axe-core run; the manual screen-reader review (NVDA + VoiceOver) is still pending, so per-criterion
> verdicts that depend on assistive-technology testing remain a target.** An accessible implementation
> **exists**: the framework-free `web/` UI (`index.html` + `app.js` + `style.css`) presents a
> supplementary SVG map paired with an **authoritative sortable data table** as the non-visual
> equivalent; significance and confidence are stated in **text, not color**; it provides a skip link and
> semantic `<th scope>` headers. Two automated gates now run: the committed **structural** gate
> (`tools/a11y_check.py`, part of `make verify`) **and** a deeper **axe-core** run in jsdom
> (`make axe` → `web/package.json` → `tools/axe_check.mjs`), which the current page **passes** with no
> violations. On the strength of that real work, several rows below have moved from *target* toward
> **Supports** — specifically those genuinely backed by the shipped DOM (the semantic data table for
> 1.3.1 / 4.1.2, the sticky-column reflow for 1.4.10, and the sort `aria-live` region for the
> status-message aspect of 4.1.3). However, the **manual screen-reader review has not yet been
> performed**: full manual NVDA (Windows/Firefox) and VoiceOver (macOS/Safari) verification is still
> outstanding, and every verdict that depends on it is still stated as a **target**, not a verified
> finding. **No manual screen-reader testing has been performed.** Each entry is to be re-evaluated
> against the implementation and the ACR re-committed on each release.

This report uses the ITI VPAT 2.5 (Rev 508) template structure to document the accessibility
conformance of the `nearmiss` accessible web map and its list/table equivalent against
the Revised Section 508 Standards (36 CFR Part 1194), which incorporate WCAG 2.0 Level A and AA by
reference. The project targets the higher bar of **WCAG 2.2 Level AA**, so this report also covers the
WCAG 2.1 and 2.2 success criteria that 508 does not yet require. Where a 2.2 criterion is reported, it is
marked as targeted beyond the baseline 508 obligation.

`nearmiss` is a community advocacy project, not federal ICT, so Section 508 does not legally apply to it.
This ACR is published voluntarily because the audience includes disabled road users — among the most
endangered people on bad streets — and because an advocacy artifact should hold up when it lands in front
of a city that audits to 508. The implementation now exists, passes the structural gate, and passes an
automated axe-core run; publishing the per-criterion status — distinguishing what is genuinely backed
from what still awaits manual screen-reader review — is a deliberate commitment to be held to that bar,
not a claim that the manual evaluation has been completed.

---

## Product / report information

| Field | Value |
| --- | --- |
| **Name of product / version** | nearmiss — accessible map and list/table view (framework-free `web/` UI, served by `src/nearmiss/server.py`) · v0.1.0 |
| **Report date** | 2026-06-17 |
| **Product description** | A framework-free, read-only web interface over the published nearmiss dataset. It presents exposure-normalized near-miss risk surfaces — kernel-density intensity and Getis-Ord Gi\* significant clusters — as a supplementary SVG map, paired with an authoritative sortable list and data table that carry the same ranked locations (real Davis street-block names, e.g. "5th St (C–D)"), rates, confidence intervals, sample sizes (n), and significance flags. It reads only the open, aggregated, minimum-occupancy public artifacts; it never exposes a precise raw report. |
| **Contact information** | Chelsea Kelly-Reif, maintainer — GitHub [@ChelseaKR](https://github.com/ChelseaKR); issues at `github.com/ChelseaKR/nearmiss` (public, pre-1.0 beta) |
| **Notes** | The accessible implementation exists and passes two automated gates: the committed structural gate (`tools/a11y_check.py`, part of `make verify`) and a deeper axe-core run in jsdom (`make axe`, also run in CI). The remaining outstanding work is the **manual NVDA and VoiceOver review**. Rows genuinely backed by the shipped DOM and confirmed by axe are reported as *Supports*; rows whose verdict still depends on manual screen-reader testing remain a *target*. Some criteria are reported as *Partially Supports* with honest remarks describing the anticipated gap and its remediation status. This ACR is to be re-evaluated against the implementation and re-committed on each release. |
| **Evaluation methods used** | See *Evaluation methods* below. |

---

## Applicable standards / guidelines

This report covers the following accessibility standards and guidelines.

| Standard / guideline | Included in report |
| --- | --- |
| Web Content Accessibility Guidelines (WCAG) 2.0 — Level A | Yes (Table 1) |
| Web Content Accessibility Guidelines (WCAG) 2.0 — Level AA | Yes (Table 1) |
| Web Content Accessibility Guidelines (WCAG) 2.1 — Level A & AA | Yes (Table 1) |
| Web Content Accessibility Guidelines (WCAG) 2.2 — Level A & AA | Yes (Table 1) — targeted beyond the 508 baseline |
| Revised Section 508 — Chapter 3, Functional Performance Criteria (FPC) | Yes |
| Revised Section 508 — Chapter 4, Hardware | Not applicable — nearmiss ships no hardware |
| Revised Section 508 — Chapter 5, Software | Yes |
| Revised Section 508 — Chapter 6, Support Documentation and Services | Yes |

---

## Evaluation methods

An implementation exists at v0.1.0 and two automated accessibility gates already run against it — a
**structural** gate and a deeper **axe-core** run; the **manual screen-reader review has not yet been
performed**. This section records the combined evaluation method, distinguishing what is in place from
what is still outstanding. The `web/` interface served by `src/nearmiss/server.py` runs against published
fixture data so that the evaluation is reproducible.

- **Structural gate — `tools/a11y_check.py` (in place).** A committed structural check verifies the
  page-level accessibility scaffolding of the `web/` UI — skip link, semantic `<th scope>` table
  headers, the authoritative data table as the non-visual equivalent, and significance/confidence
  stated in text rather than color. It runs as part of `make verify` and the current implementation
  **passes** it. This gate is **structural only**: it confirms the scaffolding is present, not that the
  interface is conformant under assistive technology.
- **Automated testing — axe-core (in place).** A real automated accessibility run is now wired:
  `make axe` (`web/package.json` → `tools/axe_check.mjs`) loads the static page in **jsdom** and runs
  **axe-core**, failing on any violation; it also runs in CI. The current page **passes with no
  violations** against the static DOM. This complements the structural gate but, like all automated
  scanning, is **necessary but not sufficient** — it inspects a static DOM in jsdom (no browser, no live
  assistive technology) and cannot replace manual screen-reader testing.
- **Manual screen-reader testing — NVDA (Windows / Firefox) (outstanding — not yet performed).** Planned
  full keyboard-only operation of every view: tab order, focus management, programmatic
  name/role/value of controls, table semantics (row/column headers and announcements), the map's
  text/data alternative, legend semantics, and form labels and error messages.
- **Manual screen-reader testing — VoiceOver (macOS / Safari) (outstanding — not yet performed).** Planned
  independent verification of the same flows under a second screen reader and browser, with attention to
  rotor navigation of headings, landmarks, tables, and links, and to announcement of dynamic updates
  (sort changes) via the live region.
- **Manual keyboard testing (outstanding — not yet performed).** Planned keyboard-only traversal of all
  interactive elements with no pointer: reachability, operability, visible focus, focus-not-obscured,
  and absence of keyboard traps.
- **Manual contrast and non-text-contrast inspection (outstanding — not yet performed).** Text and
  UI-component/graphical contrast to be measured against the published map and legend color tokens.

The map is an inherently visual artifact. Throughout this report, the **list and data-table view is the
conforming mechanism** that makes the map's visual-only content perceivable and operable without vision;
the `web/` UI implements it as the authoritative sortable data table. Every finding the map conveys
graphically — ranked location, rate, confidence interval, n, and statistical-significance flag — is
present as text in the equivalent view. The table is real `<table>` markup with `<th scope="col">` and
`<th scope="row">` headers, an `aria-sort` state on the active column, a sticky name column, and a
polite `aria-live` region that announces sort changes. Whether the dynamic announcements and table
navigation behave correctly *under live assistive technology* remains to be confirmed by the outstanding
manual NVDA/VoiceOver review.

---

## Conformance level (terms) legend

The terms used to describe conformance for each criterion are defined as follows. At v0.1.0 the
interface exists, passes the structural gate, and passes an automated axe-core run. Where a term is
genuinely backed by the shipped DOM and confirmed by axe, it is asserted directly; where it still
depends on manual NVDA/VoiceOver testing, it is marked **(target)**, because that manual review has not
yet been performed. All entries are to be re-asserted against the full evaluation on each release.

| Term | Definition |
| --- | --- |
| **Supports** | The functionality of the product meets the criterion without known defects, or meets it with equivalent facilitation. Where marked *(target)*, the verdict still awaits manual screen-reader confirmation. |
| **Partially Supports** | Some functionality of the product does not, or is anticipated not to, meet the criterion. |
| **Does Not Support** | The majority of product functionality is not designed to meet the criterion. |
| **Not Applicable** | The criterion is not relevant to the product. |
| **Not Evaluated** | The product has not been evaluated against the criterion. This term may be used only in the WCAG 2.x Level AAA table. |

---

## Table 1 — Success Criteria, Level A & AA (WCAG 2.0 / 2.1 / 2.2)

The **Conformance level** column below states either a verdict genuinely backed by the shipped DOM (and
confirmed by the axe-core run) or, where marked **(target)**, an intended conformance still awaiting the
outstanding manual NVDA/VoiceOver review. Notes apply to all rows: "Supports via equivalent
facilitation" means the map's visual-only content is made conforming by the accessible list and
data-table view, which carries the same locations, rates, intervals, n, and significance flags.

### Level A

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.1.1 Non-text Content** (Level A) | Supports (target) | The supplementary SVG map is exposed as `role="img"` with an `aria-labelledby` description and points to the equivalent data table; significant segments carry an in-`<title>` text label, and the map is drawn with thickness and dash **pattern**, not color alone. Legend swatches have text labels; no information is in the image alone. The axe-core run reports no image-alternative violations; correct announcement of the SVG and its per-segment titles under a screen reader is the remaining manual-review item. |
| **1.3.1 Info and Relationships** (Level A) | Supports | The data table uses real `<table>` semantics with `<th scope="col">` column headers and a `<th scope="row">` row header per segment; the page is structured with `header`/`main`/`footer` landmarks, `aria-labelledby` sections, and a logical heading hierarchy. Ranking, rate, interval, n, confidence, hotspot, and quality flags are individually labeled columns. The axe-core run reports no structure/relationship violations. Rotor/table-navigation behavior under NVDA/VoiceOver is still to be confirmed manually. |
| **1.4.1 Use of Color** (Level A) | Supports | Risk and statistical significance are never conveyed by color alone. Significant Gi\* clusters carry an explicit text marker ("★ Significant") and a dashed/thicker line **pattern** in addition to hue; the table states significance and confidence in words and exposes rate, interval, and n numerically. Hard rule 2 (no estimate without an interval) is honored in the non-color encoding. |
| **2.1.1 Keyboard** (Level A) | Partially Supports (target) | Browsing, sorting, and reading every finding are fully keyboard-operable through the list and table (native `<button>` sort controls, a focusable scroll region). The supplementary map carries no interactive per-feature controls — its content is mirrored in the keyboard-accessible table — so there is no map-only keyboard path to strand a user. No-keyboard-trap conformance and full focus behavior are to be verified under NVDA and VoiceOver. |
| **3.3.2 Labels or Instructions** (Level A) | Supports (target) | The current read-only UI presents no report-entry form; the table's sort controls are labeled `<button>` elements whose column meaning is given by the `<th scope="col">` text, and inline "How to read this" instructions explain rate, CI, confidence, and hotspot. When the report-entry form ships, every input is specified to have a visible, programmatically associated label with `aria-describedby` hints. Manual screen-reader confirmation of control labeling is pending. |
| **4.1.2 Name, Role, Value** (Level A) | Supports (target) | Native HTML controls (sort `<button>`s, links, table headers, the focusable `role="region"` scroll container) expose correct name and role; the active sort column exposes `aria-sort="ascending"`/`"descending"`, updated in `app.js` on every sort. The axe-core run reports no name/role/value violations on the static DOM. Final confirmation that NVDA and VoiceOver announce the `aria-sort` state and table headers correctly is the remaining manual item, hence *(target)*. |

### Level AA

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.4.3 Contrast (Minimum)** (Level AA) | Supports (target) | Body text, table content, labels, and the demo/provenance note use high-contrast tokens (`--fg #15202b` on white; `--accent #0b4f9c` and the note colors chosen ≥ 4.5:1) on solid backgrounds rather than text over imagery. The axe-core run reports no color-contrast violations on the static DOM; a manual contrast pass against the rendered page and the live map/legend tokens is still planned, hence *(target)*. |
| **1.4.11 Non-text Contrast** (Level AA) | Partially Supports (target) | UI component boundaries (sort-button focus rings, the table border, the focus indicator) target 3:1, and the map's significant-cluster encoding is a dashed/thicker **pattern**, not a thin color cue. One anticipated open item is non-text contrast of certain map strokes over the schematic basemap at some scales; the equivalent table conveys the same values as text and numerals. A manual non-text-contrast measurement is planned. |
| **2.4.7 Focus Visible** (Level AA) | Supports (target) | A visible 3px `outline` with offset is applied to links, buttons, and the focusable table scroll region via `:focus-visible`; the default indicator is not suppressed. Confirmation by keyboard-only traversal under both screen readers is the remaining manual item. |
| **2.5.8 Target Size (Minimum)** (Level AA, WCAG 2.2) | Supports (target) | Targeted beyond the 508 baseline. The sort-control `<button>`s set `min-height: 24px` and `min-width: 24px` with padding and spacing, meeting the 24×24 CSS-pixel minimum. A manual check at the rendered sizes across viewports is still planned. |

### Selected additional Level A & AA criteria covered

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.4.4 Resize Text** (Level AA) | Supports (target) | Content uses relative units (`rem`/`em`, `system-ui` base) and reflows; the layout remains usable at 200% zoom. A manual zoom pass is still planned to confirm no loss of content or function. |
| **1.4.10 Reflow** (Level AA) | Supports | The layout reflows without loss of content or function at narrow widths / 200% zoom: the `<main>` is width-capped and single-column, and the wide data table is wrapped in a focusable `role="region"` (`aria-label="Ranked segments table (scrollable)"`) that scrolls horizontally only when columns cannot collapse further — the permitted exception for tabular data. The **segment-name column is sticky** (`th[scope="row"]` is `position: sticky; left: 0`) and the header row is sticky, so the row identity and column headers stay visible while the table scrolls at 200% zoom. The axe-core run reports no related violations. |
| **2.1.2 No Keyboard Trap** (Level A) | Supports (target) | Focus moves through the sort buttons and the scrollable table region with standard keys and is not trapped; to be verified manually under NVDA and VoiceOver. |
| **2.4.3 Focus Order** (Level A) | Supports (target) | Focus order follows the reading and operation order: skip link → header → map → table controls → table region. To be confirmed manually under both screen readers. |
| **2.4.6 Headings and Labels** (Level AA) | Supports | Headings and labels are descriptive and honest — the lede states "Raw counts are report volume, not danger" (hard rule 1), and the "How to read this" section labels each measure so the heading itself prevents a misleading reading. Confirmed structurally and by axe. |
| **3.2.2 On Input** (Level A) | Supports (target) | Sorting a column re-renders the table and map in place and triggers no unexpected context change; the result is announced via a polite live region (see 4.1.3). Manual confirmation under assistive technology is pending. |
| **3.3.1 Error Identification** (Level A) | Supports | The read-only UI has no report-entry form to validate; the one runtime failure path (data could not load) renders a text message in the table caption, the map caption, and a table row — identified in words, not by color. (When the report-entry form ships, field-level error identification will be added and re-evaluated.) |
| **4.1.3 Status Messages** (Level AA) | Supports (target) | Sorting announces the new order through a visually-hidden `aria-live="polite"` region (`#sort-status`), populated in `app.js` with the column and direction on every sort — this status-message mechanism is genuinely present and passes axe. The remaining *(target)* qualifier is solely that announcement timing/coalescing under live NVDA and VoiceOver has not yet been manually verified; no message is dropped in the DOM, only possibly delayed by the AT, and the re-rendered table is itself readable. |

---

## Revised Section 508 Report

### Chapter 3 — Functional Performance Criteria (FPC)

The Functional Performance Criteria apply where Chapter 5 (Software) does not fully address a feature, or
as an overall check that the product is usable by people with the listed disabilities. The list and
data-table equivalent is the primary mechanism by which the visual map satisfies these criteria. Verdicts
genuinely backed by the shipped DOM are asserted directly; those still depending on manual
NVDA/VoiceOver review are marked **(target)**.

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **302.1 Without Vision** | Supports (target) | The entire analysis is reachable without sight: the accessible list and data table convey every ranked location (real Davis block names), rate, confidence interval, n, and significance flag in text, with real table semantics and a sort live region. The structure and semantics are confirmed by axe; correct announcement under NVDA and VoiceOver is the remaining manual item. The map is a redundant visual rendering, not the sole carrier of any finding. |
| **302.2 With Limited Vision** | Partially Supports (target) | Text and UI contrast target WCAG AA (no axe contrast violations); content reflows and remains usable at 200% zoom, with a sticky name column and sticky headers; the list/table is the high-contrast path. The anticipated open item is non-text contrast of certain map strokes over the schematic basemap at some scales (see 1.4.11); the text/numeric equivalent fully conveys those values. A manual low-vision pass is still planned. |
| **302.3 Without Perception of Color** | Supports | Risk and significance are encoded with text labels and a dashed/thicker line pattern in addition to color (see 1.4.1); the list/table is fully color-independent. Confirmed structurally and by axe. |
| **302.4 Without Hearing** | Supports — no audio | The product presents no audio content and conveys no information through sound; nothing is lost without hearing. |
| **302.5 With Limited Hearing** | Supports — no audio | Not relevant beyond 302.4 — there is no audio to perceive. |
| **302.6 Without Speech** | Supports | No operation of the product requires speech input. |
| **302.7 With Limited Manipulation** | Supports (target) | All functionality is operable by keyboard alone without simultaneous or path-based gestures; sort targets meet the 24px minimum with spacing (see 2.5.8). There is no interactive map widget to require fine pointer control — the map mirrors the keyboard-accessible table. Manual keyboard verification under both screen readers is pending. |
| **302.8 With Limited Reach and Strength** | Supports (target) | No functionality requires reach, force, or a sustained physical action; interaction is single, discrete keyboard or pointer actions. Manual confirmation is pending. |
| **302.9 With Limited Language, Cognitive, and Learning Abilities** | Supports | Findings are written in plain language for a city-council audience; legends and headings are honest and explicit ("report volume, not danger"); statistical uncertainty is stated in words alongside the numbers (confidence labels, "exposure unknown"). Interface and brief strings live in per-language bundles (`src/nearmiss/i18n.py`), and the brief can render in English or Spanish (`nearmiss brief --lang es`). |

### Chapter 5 — Software

The nearmiss web interface is content rendered in a user-supplied web browser; it is authored as
standard web content using HTML, CSS, and unframework'd JavaScript. Accordingly, conformance
is governed primarily by 502.2 (incorporation of WCAG via 504/E207) and the criteria below; several
Chapter 5 sections that address platform software and assistive-technology authoring do not apply to a
read-only web page. Verdicts genuinely backed by the shipped DOM are asserted directly; those still
depending on manual NVDA/VoiceOver review are marked **(target)**.

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **501.1 Scope — Incorporation of WCAG 2.0 AA** | Supports (target) | The web content conforms per Table 1 (WCAG A/AA), with the noted *Partially Supports* items and the manual-review *(target)* qualifiers. The project additionally targets WCAG 2.2 AA. |
| **502.2.1 User Control of Accessibility Features** | Not Applicable | nearmiss is web content, not a platform or assistive technology; it does not disrupt platform accessibility features and exposes none of its own to override. |
| **502.2.2 No Disruption of Accessibility Features** | Supports (target) | The interface uses native semantics and standard ARIA; it does not override or disable browser or OS accessibility features (zoom, high-contrast, screen-reader navigation) and respects `prefers-reduced-motion`. To be confirmed under NVDA and VoiceOver. |
| **502.3 Accessibility Services** | Not Applicable | The product is not a platform and exposes no accessibility-services API; it relies on the browser's accessibility tree, which it populates with native semantics (see 4.1.2). |
| **503.2 User Preferences** | Supports (target) | The interface honors browser and OS user preferences — text size, zoom, reduced motion, and color/contrast settings — because it is built on standard reflowable web content with relative units and respects `prefers-reduced-motion`. Manual confirmation is pending. |
| **503.4 Authoring Tools** | Not Applicable | nearmiss does not author content for others; it renders a published dataset read-only. |
| **504.2 Content Creation or Editing (Authoring Tools)** | Not Applicable | The product is not an authoring tool. |
| **E207.2 WCAG Conformance (Software with a user interface)** | Partially Supports (target) | The user interface meets WCAG 2.0/2.1 Level A and AA except for the anticipated items noted in Table 1 (2.1.1, 1.4.11, the 2.5.8 spacing exception), each with a specified text/data equivalent and a planned remediation item; the remaining manual screen-reader review keeps several otherwise-Supports rows marked *(target)*. |

### Chapter 6 — Support Documentation and Services

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **602.2 Accessibility and Compatibility Features (documentation)** | Supports | Project documentation describes the accessibility features and the non-visual list/table equivalent: the README's "Accessibility and Section 508 conformance" section, the methodology doc, the data card (`docs/DATA-CARD.md`), and this ACR explain how to reach every finding without vision and how the equivalent view works. |
| **602.3 Electronic Support Documentation** | Supports | All support documentation is provided as accessible electronic content — Markdown and rendered HTML that themselves conform to WCAG 2.0 AA: real headings, list and table semantics, descriptive link text, and no information by color alone. This ACR and the README are written as lint-clean Markdown. |
| **602.4 Alternate Formats for Non-Electronic Support Documentation** | Not Applicable | There is no non-electronic (printed) support documentation; all documentation is electronic and accessible. |
| **603.2 Information on Accessibility and Compatibility Features (support services)** | Supports | Support is provided through the public GitHub repository. Accessibility issues can be filed via issue templates, and the maintainer treats accessibility regressions as merge-blocking — the structural gate is part of `make verify` and the axe-core run is wired via `make axe` and CI; this ACR names the contact and the standards targeted. |
| **603.3 Accommodations for Communication Needs (support services)** | Partially Supports | The single-maintainer project offers support through GitHub issues and email, which are text-based and screen-reader accessible. It cannot guarantee alternative real-time channels (e.g., phone or video relay) given its independent, unfunded status; this limitation is stated honestly rather than overclaimed. |

---

## Legal disclaimer

This Accessibility Conformance Report is provided by the nearmiss maintainer for informational purposes
and, at v0.1.0, represents a good-faith record of the conformance work completed to date together with a
good-faith **target** for the work that remains. The accessible implementation exists and passes two
committed automated gates — the structural gate (`tools/a11y_check.py`, part of `make verify`) and an
axe-core run in jsdom (`make axe` → `web/package.json` → `tools/axe_check.mjs`, also run in CI) — with no
axe violations on the static DOM. The remaining outstanding evaluation is the **manual NVDA and VoiceOver
screen-reader review**, which has **not** yet been performed; per-criterion verdicts that depend on it are
marked *(target)* rather than presented as a record of manual testing. nearmiss is an independent personal
open-source project licensed under Apache-2.0, unaffiliated with any employer or client, and contains no
proprietary or client material. It is not federal ICT and is under no legal obligation to conform to
Section 508; conformance is pursued voluntarily. Conformance is to be evaluated against the implementation
and this report regenerated and re-committed on each release. The structural and axe gates run today; the
committed manual NVDA/VoiceOver review notes in `docs/audits/` remain outstanding, so the *(target)*
claims here are to be verified against that deeper review — not yet a completed manual audit.
