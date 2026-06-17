# Accessibility Conformance Report (ACR)

## Voluntary Product Accessibility Template (VPAT) Version 2.5 — Revised Section 508 Edition

> **Status at v0.1.0 — pre-implementation conformance target, not a tested result.** This is a
> documentation-stage / specification release. The `web/` UI and `src/nearmiss/server.py` server
> described below do **not exist yet**; no implementation has been evaluated against any criterion. This
> document records the **conformance target** the project commits to, and the **evaluation method that
> will be applied** (axe-core automated scanning plus manual NVDA and VoiceOver screen-reader testing)
> once the web UI and server are built across the roadmap. Every per-criterion entry in the tables below
> states the **intended/targeted** conformance, not a verified finding. Each entry is to be re-verified
> against the real implementation and the ACR re-committed on each release; until that happens, treat all
> "Supports" / "Partially Supports" verdicts as design intent.

This report uses the ITI VPAT 2.5 (Rev 508) template structure to document the accessibility
conformance **target** of the planned `nearmiss` accessible web map and its list/table equivalent against
the Revised Section 508 Standards (36 CFR Part 1194), which incorporate WCAG 2.0 Level A and AA by
reference. The project targets the higher bar of **WCAG 2.2 Level AA**, so this report also covers the
WCAG 2.1 and 2.2 success criteria that 508 does not yet require. Where a 2.2 criterion is reported, it is
marked as targeted beyond the baseline 508 obligation.

`nearmiss` is a community advocacy project, not federal ICT, so Section 508 does not legally apply to it.
This ACR is published voluntarily because the audience includes disabled road users — among the most
endangered people on bad streets — and because an advocacy artifact should hold up when it lands in front
of a city that audits to 508. Publishing the target up front, before the code exists, is a deliberate
design commitment rather than a record of work performed.

---

## Product / report information

| Field | Value |
| --- | --- |
| **Name of product / version** | nearmiss — accessible map and list/table view (planned `web/` UI to be served by `src/nearmiss/server.py`) · v0.1.0 (documentation-stage) |
| **Report date** | 2026-06-16 |
| **Product description** | A planned framework-free, read-only web interface over the published nearmiss dataset. It is designed to present exposure-normalized near-miss risk surfaces — kernel-density intensity and Getis-Ord Gi\* significant clusters — as an interactive map, paired with an equivalent sortable list and data table that carry the same ranked locations, rates, confidence intervals, sample sizes (n), and significance flags. It is intended to read only the open, aggregated, jittered published artifacts; it is designed never to expose a precise raw report. |
| **Contact information** | Chelsea Kelly-Reif, maintainer — GitHub [@ChelseaKR](https://github.com/ChelseaKR); issues at `github.com/ChelseaKR/nearmiss` (private during development) |
| **Notes** | Documentation-stage target. Some criteria are reported as *Partially Supports* with honest remarks describing the gap the design anticipates and its intended remediation status. Accessibility is specified as a merge-blocking CI gate (`make accessibility`); this ACR is to be regenerated and re-committed against the real implementation on each release. |
| **Evaluation methods to be used** | See *Evaluation methods* below. |

---

## Applicable standards / guidelines

This report covers the following accessibility standards and guidelines as conformance targets.

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

No implementation has been evaluated at v0.1.0. This section records the combined automated and manual
evaluation method that **will be applied** to the planned `web/` interface served by
`src/nearmiss/server.py`, run against published fixture data so that the evaluation will be reproducible
once the code and fixtures exist.

- **Automated testing — axe.** Automated accessibility scanning with axe-core is planned across the map
  view, the list view, the data table, the report form, the hotspot legends, and every chart. axe is
  intended to run both interactively during development and as part of the merge-blocking CI accessibility
  gate (`make accessibility`); a new violation is designed to fail the build. Automated coverage is
  treated as necessary but not sufficient.
- **Manual screen-reader testing — NVDA (Windows / Firefox).** Planned full keyboard-only operation of
  every view: tab order, focus management, programmatic name/role/value of controls, table semantics
  (row/column headers and announcements), the map's text/data alternative, legend semantics, and form
  labels and error messages.
- **Manual screen-reader testing — VoiceOver (macOS / Safari).** Planned independent verification of the
  same flows under a second screen reader and browser, with attention to rotor navigation of headings,
  landmarks, tables, and links, and to announcement of dynamic updates (filter/sort changes) via live
  regions.
- **Manual keyboard testing.** Planned keyboard-only traversal of all interactive elements with no
  pointer: reachability, operability, visible focus, focus-not-obscured, and absence of keyboard traps.
- **Manual contrast and non-text-contrast inspection.** Text and UI-component/graphical contrast to be
  measured against the published map and legend color tokens.

The map is an inherently visual artifact. Throughout this report, the **list and data-table view is the
intended conforming mechanism** that is designed to make the map's visual-only content perceivable and
operable without vision. Every finding the map conveys graphically — ranked location, rate, confidence
interval, n, and statistical-significance flag — is specified to be present as text in the equivalent
view.

---

## Conformance level (terms) legend

The terms used to describe the **targeted** conformance for each criterion are defined as follows. At
v0.1.0 these terms express design intent for an unbuilt interface, not a tested verdict; they will be
re-asserted against the real implementation on each release.

| Term | Definition |
| --- | --- |
| **Supports** | The functionality of the product is designed so that at least one method meets the criterion without known defects, or meets it with equivalent facilitation (to be verified against the implementation). |
| **Partially Supports** | Some functionality of the product is anticipated not to meet the criterion. |
| **Does Not Support** | The majority of product functionality is not designed to meet the criterion. |
| **Not Applicable** | The criterion is not relevant to the product. |
| **Not Evaluated** | The product has not been evaluated against the criterion. This term may be used only in the WCAG 2.x Level AAA table. |

---

## Table 1 — Success Criteria, Level A & AA (WCAG 2.0 / 2.1 / 2.2)

The **Conformance level** column below states the **targeted/intended** conformance for the planned
interface, not a tested result; it is to be re-verified against the real implementation each release.
Notes apply to all rows: "Supports via equivalent facilitation" means the map's visual-only content is
designed to be made conforming by the accessible list and data-table view, which is specified to carry
the same locations, rates, intervals, n, and significance flags.

### Level A

| Criteria | Targeted conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.1.1 Non-text Content** (Level A) | Supports (target) | Map tiles and the KDE/Gi\* surfaces are designed as decorative duplicates of data available in the list/table; the map container is to expose a text description and point to the equivalent data view. Charts are to carry text alternatives summarizing the same numbers. Legend swatches are specified to have text labels; no information is to be in the image alone. Icon-only controls are to have accessible names. |
| **1.3.1 Info and Relationships** (Level A) | Supports (target) | The data table is designed to use real `<table>` semantics with `<th scope>` row/column headers; views are to be structured with landmarks and a logical heading hierarchy; the report form is to use programmatically associated `<label>`s, `fieldset`/`legend` for grouped inputs, and `aria-describedby` for hint and error text. Ranking, rate, interval, n, and significance are to be individually labeled columns. |
| **1.4.1 Use of Color** (Level A) | Supports (target) | Risk level and statistical significance are designed never to be conveyed by color alone. Significant Gi\* clusters are to carry a text label and a distinct fill pattern in addition to hue; the list/table is to state significance as text ("significant hot spot, 95%") and expose rate, interval, and n numerically. Hard rule 2 (no estimate without an interval) is to be honored in the non-color encoding. |
| **2.1.1 Keyboard** (Level A) | Partially Supports (target) | The design intends all primary functionality — browsing, sorting, filtering, reading every finding — to be fully keyboard-operable through the list and table, and the form to be fully keyboard-operable. The interactive map's pan/zoom is intended to be keyboard-operable, but keyboard selection of an individual map feature ("activate this segment") is an anticipated hardening item; the equivalent data view is specified to provide full keyboard access to every segment and its statistics in the interim. No-keyboard-trap conformance is to be verified under NVDA and VoiceOver. |
| **3.3.2 Labels or Instructions** (Level A) | Supports (target) | Every report-form input is to have a visible, programmatically associated label; required fields are to be marked in text (not by color or asterisk alone) and via `aria-required`; instructions for location, time, mode, and hazard type are to be provided inline and associated with their controls via `aria-describedby`. Table sort controls are to be labeled with their current sort state. |
| **4.1.2 Name, Role, Value** (Level A) | Partially Supports (target) | Native HTML controls (buttons, links, selects, table headers, form fields) are designed to expose correct name, role, and value to NVDA and VoiceOver. Custom composite widgets — the sortable column headers and the filter disclosure — are to expose name/role/state via ARIA, to be verified manually. One anticipated gap: the map feature-popup will need robust state announcement when opened via keyboard; the design tracks this against the equivalent data view, which is specified to announce the same content correctly. |

### Level AA

| Criteria | Targeted conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.4.3 Contrast (Minimum)** (Level AA) | Supports (target) | All body text, table content, labels, and legend text are to meet at least 4.5:1 against their background; large headings at least 3:1. The published map/legend color tokens are to be chosen and measured to pass; the list/table view is designed to use high-contrast text on solid backgrounds rather than text over imagery. |
| **1.4.11 Non-text Contrast** (Level AA) | Partially Supports (target) | UI component boundaries (form controls, buttons, focus indicators, table sort affordances) and the legend's graphical significance pattern are to meet 3:1 against adjacent colors. One anticipated open item is contrast of certain KDE intensity bands where they overlap busy basemap tiles at some zoom levels; the equivalent data table is specified to convey the same intensity values as text and numerals, and a basemap-dim option is planned as remediation. |
| **2.4.7 Focus Visible** (Level AA) | Supports (target) | A visible focus indicator with sufficient contrast is to be present on every interactive element across map, list, table, and form, to be verified by keyboard-only traversal under both screen readers. The default indicator is not to be suppressed; a custom high-contrast outline is to be applied where needed. |
| **2.5.8 Target Size (Minimum)** (Level AA, WCAG 2.2) | Supports (target) | Targeted beyond the 508 baseline. Interactive targets in the list, table sort controls, filters, and form controls are to be at least 24×24 CSS pixels, with adequate spacing; touch targets in the mobile-first report form are to be sized generously because reports are made from the roadside. Closely spaced map controls that fall below 24px are to be paralleled by larger equivalents in the list/table toolbar (the spacing/equivalent exception). |

### Selected additional Level A & AA criteria covered

| Criteria | Targeted conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.4.4 Resize Text** (Level AA) | Supports (target) | Content is to reflow and remain usable at 200% zoom; layout is to use relative units, and the list/table view is to reflow to a single column without loss of content or function. |
| **1.4.10 Reflow** (Level AA) | Supports (target) | No horizontal scrolling at 320 CSS px width / 400% zoom is targeted for the list, table, and form. The wide data table is to reflow responsively and expose a horizontal-scroll region with an accessible name where columns cannot collapse further, which is permitted for tabular data. |
| **2.1.2 No Keyboard Trap** (Level A) | Supports (target) | To be verified manually under NVDA and VoiceOver; focus is designed to always move away from the map, popups, and form controls using standard keys. |
| **2.4.3 Focus Order** (Level A) | Supports (target) | Focus order is designed to follow reading and operation order across map, list, table, and form; opening a filter or popup is not to strand focus. |
| **2.4.6 Headings and Labels** (Level AA) | Supports (target) | Headings and labels are to be descriptive and honest — for example "Report volume (not danger)" labels raw-count views, per hard rule 1, so the heading itself prevents a misleading reading. |
| **3.2.2 On Input** (Level A) | Supports (target) | Changing a filter or sort is not to trigger an unexpected context change; updates are to be applied predictably and announced via a polite live region. |
| **3.3.1 Error Identification** (Level A) | Supports (target) | Report-form errors are to be identified in text, associated with the offending field, and announced; the error is to name the problem (e.g., missing location) rather than relying on color. |
| **4.1.3 Status Messages** (Level AA) | Partially Supports (target) | Filter/sort result counts and form-submission status are to be announced via `aria-live` regions and verified under NVDA. Under VoiceOver/Safari, rapid successive status updates are an anticipated coalescing risk; the design intends no message to be lost, only possibly delayed, and the updated table content is itself readable. Remediation is planned. |

---

## Revised Section 508 Report

### Chapter 3 — Functional Performance Criteria (FPC)

The Functional Performance Criteria apply where Chapter 5 (Software) does not fully address a feature, or
as an overall check that the product is usable by people with the listed disabilities. The list and
data-table equivalent is the intended primary mechanism by which the visual map is designed to satisfy
these criteria. Verdicts below are targets for the unbuilt interface.

| Criteria | Targeted conformance level | Remarks and explanations |
| --- | --- | --- |
| **302.1 Without Vision** | Supports (target) | The entire analysis is designed to be reachable without sight: the accessible list and data table are to convey every ranked location, rate, confidence interval, n, and significance flag in text, with proper table semantics to be verified under NVDA and VoiceOver. The map is treated as a redundant visual rendering of this data, not as the sole carrier of any finding. |
| **302.2 With Limited Vision** | Partially Supports (target) | Text and UI contrast are to meet WCAG AA; content is to reflow and remain usable at 200%/400% zoom; the list/table is the intended high-contrast path. The anticipated open item is non-text contrast of certain KDE intensity bands over busy basemap tiles at some zoom levels (see 1.4.11); the text/numeric equivalent is specified to fully convey those values, and a basemap-dim control is planned. |
| **302.3 Without Perception of Color** | Supports (target) | Risk and significance are to be encoded with text labels and patterns in addition to color (see 1.4.1); the list/table is designed to be fully color-independent. |
| **302.4 Without Hearing** | Supports — no audio (target) | The product is designed to present no audio content and convey no information through sound; nothing is lost without hearing. |
| **302.5 With Limited Hearing** | Supports — no audio (target) | Not relevant beyond 302.4 — there is to be no audio to perceive. |
| **302.6 Without Speech** | Supports (target) | No operation of the product is to require speech input. |
| **302.7 With Limited Manipulation** | Partially Supports (target) | All functionality is designed to be operable by keyboard alone without simultaneous or path-based gestures; targets in the list, table, and form are to meet the 24px minimum size with spacing (see 2.5.8). The anticipated gap is keyboard selection of an individual map feature (see 2.1.1); the equivalent data view is specified to provide single-action access to every segment in the interim. |
| **302.8 With Limited Reach and Strength** | Supports (target) | No functionality is to require reach, force, or a sustained physical action; interaction is designed as single, discrete keyboard or pointer actions, and the mobile report form is to use large, well-spaced controls. |
| **302.9 With Limited Language, Cognitive, and Learning Abilities** | Supports (target) | Findings are to be written in plain language for a city-council audience; legends and headings are to be honest and explicit ("report volume, not danger"); the report form is to ask plain questions with inline instructions; statistical uncertainty is to be stated in words alongside the numbers. Interface and form strings are planned to live in per-language bundles, and the report form is intended to be bilingual where the community is. |

### Chapter 5 — Software

The planned nearmiss web interface is content rendered in a user-supplied web browser; it is to be
authored as standard web content using HTML, CSS, and unframework'd JavaScript. Accordingly, conformance
is governed primarily by 502.2 (incorporation of WCAG via 504/E207) and the criteria below; several
Chapter 5 sections that address platform software and assistive-technology authoring do not apply to a
read-only web page. Verdicts below are targets for the unbuilt interface.

| Criteria | Targeted conformance level | Remarks and explanations |
| --- | --- | --- |
| **501.1 Scope — Incorporation of WCAG 2.0 AA** | Supports (target) | The web content is designed to conform per Table 1 (WCAG A/AA), with the noted anticipated *Partially Supports* items. The project additionally targets WCAG 2.2 AA. |
| **502.2.1 User Control of Accessibility Features** | Not Applicable | nearmiss is web content, not a platform or assistive technology; it is not to disrupt platform accessibility features and exposes none of its own to override. |
| **502.2.2 No Disruption of Accessibility Features** | Supports (target) | The interface is to use native semantics and standard ARIA; it is designed not to override or disable browser or OS accessibility features (zoom, high-contrast, screen-reader navigation), to be verified under NVDA and VoiceOver. |
| **502.3 Accessibility Services** | Not Applicable | The product is not a platform and exposes no accessibility-services API; it is to rely on the browser's accessibility tree, which it is designed to populate correctly (see 4.1.2). |
| **503.2 User Preferences** | Supports (target) | The interface is to honor browser and OS user preferences — text size, zoom, reduced motion, and color/contrast settings — because it is to be built on standard reflowable web content with relative units and is to respect `prefers-reduced-motion`. |
| **503.4 Authoring Tools** | Not Applicable | nearmiss does not author content for others; it is to render a published dataset read-only. |
| **504.2 Content Creation or Editing (Authoring Tools)** | Not Applicable | The product is not an authoring tool. |
| **E207.2 WCAG Conformance (Software with a user interface)** | Partially Supports (target) | The user interface is designed to meet WCAG 2.0/2.1 Level A and AA except for the anticipated items noted in Table 1 (2.1.1, 1.4.11, 4.1.2, 4.1.3, 2.5.8 exception), each with a specified text/data equivalent and a planned remediation item. |

### Chapter 6 — Support Documentation and Services

| Criteria | Targeted conformance level | Remarks and explanations |
| --- | --- | --- |
| **602.2 Accessibility and Compatibility Features (documentation)** | Supports (target) | Project documentation is designed to describe the accessibility features and the non-visual list/table equivalent: the README's "Accessibility and Section 508 conformance" section, the methodology doc, and this ACR explain how to reach every finding without vision and how the equivalent view is intended to work. |
| **602.3 Electronic Support Documentation** | Supports (target) | All support documentation is provided as accessible electronic content — Markdown and rendered HTML that themselves are intended to conform to WCAG 2.0 AA: real headings, list and table semantics, descriptive link text, and no information by color alone. This ACR and the README are written as lint-clean Markdown. |
| **602.4 Alternate Formats for Non-Electronic Support Documentation** | Not Applicable | There is no non-electronic (printed) support documentation; all documentation is electronic and accessible. |
| **603.2 Information on Accessibility and Compatibility Features (support services)** | Supports (target) | Support is provided through the GitHub repository (private during development). Accessibility issues can be filed via issue templates, and the maintainer treats accessibility regressions as merge-blocking; this ACR names the contact and the standards targeted. |
| **603.3 Accommodations for Communication Needs (support services)** | Partially Supports (target) | The single-maintainer project offers support through GitHub issues and email, which are text-based and screen-reader accessible. It cannot guarantee alternative real-time channels (e.g., phone or video relay) given its independent, unfunded status; this limitation is stated honestly rather than overclaimed. |

---

## Legal disclaimer

This Accessibility Conformance Report is provided by the nearmiss maintainer for informational purposes
and, at v0.1.0, represents a good-faith, design-stage conformance **target** for a product that has not
yet been implemented or evaluated — not a record of testing performed. nearmiss is an independent personal
open-source project licensed under Apache-2.0, unaffiliated with any employer or client, and contains no
proprietary or client material. It is not federal ICT and is under no legal obligation to conform to
Section 508; conformance is pursued voluntarily. Once the web UI and server exist, conformance is to be
evaluated against the real implementation and this report regenerated and re-committed on each release. The
accessibility CI gate (`make accessibility`: axe plus committed manual NVDA/VoiceOver review notes in
`docs/audits/`) is specified to be merge-blocking, so the claims here are intended to be tied to checks
that run once the implementation lands — not to remain aspiration.
