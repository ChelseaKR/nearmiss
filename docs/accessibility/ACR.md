# Accessibility Conformance Report (ACR)

## Voluntary Product Accessibility Template (VPAT) Version 2.5 — Revised Section 508 Edition

This report uses the ITI VPAT 2.5 (Rev 508) template structure to document the accessibility
conformance of the `nearmiss` accessible web map and its list/table equivalent against the Revised
Section 508 Standards (36 CFR Part 1194), which incorporate WCAG 2.0 Level A and AA by reference. The
project targets the higher bar of **WCAG 2.2 Level AA**, so this report also evaluates the WCAG 2.1 and
2.2 success criteria that 508 does not yet require. Where a 2.2 criterion is reported, it is marked as
evaluated beyond the baseline 508 obligation.

`nearmiss` is a community advocacy project, not federal ICT, so Section 508 does not legally apply to it.
This ACR is published voluntarily because the audience includes disabled road users — among the most
endangered people on bad streets — and because an advocacy artifact should hold up when it lands in front
of a city that audits to 508.

---

## Product / report information

| Field | Value |
| --- | --- |
| **Name of product / version** | nearmiss — accessible map and list/table view (`web/` UI served by `src/nearmiss/server.py`) · v0.x (beta) |
| **Report date** | 2026-06-16 |
| **Product description** | A framework-free, read-only web interface over the published nearmiss dataset. It presents exposure-normalized near-miss risk surfaces — kernel-density intensity and Getis-Ord Gi\* significant clusters — as an interactive map, paired with an equivalent sortable list and data table that carry the same ranked locations, rates, confidence intervals, sample sizes (n), and significance flags. It reads only the open, aggregated, jittered published artifacts; it never exposes a precise raw report. |
| **Contact information** | Chelsea Kelly-Reif, maintainer — GitHub [@ChelseaKR](https://github.com/ChelseaKR); issues at `github.com/ChelseaKR/nearmiss` (private during development) |
| **Notes** | Beta. Some criteria are reported as *Partially Supports* with honest remarks describing the known gap and its remediation status. Accessibility is a merge-blocking CI gate; this ACR is regenerated and re-committed on each release. |
| **Evaluation methods used** | See *Evaluation methods* below. |

---

## Applicable standards / guidelines

This report covers the following accessibility standards and guidelines.

| Standard / guideline | Included in report |
| --- | --- |
| Web Content Accessibility Guidelines (WCAG) 2.0 — Level A | Yes (Table 1) |
| Web Content Accessibility Guidelines (WCAG) 2.0 — Level AA | Yes (Table 1) |
| Web Content Accessibility Guidelines (WCAG) 2.1 — Level A & AA | Yes (Table 1) |
| Web Content Accessibility Guidelines (WCAG) 2.2 — Level A & AA | Yes (Table 1) — evaluated beyond the 508 baseline |
| Revised Section 508 — Chapter 3, Functional Performance Criteria (FPC) | Yes |
| Revised Section 508 — Chapter 4, Hardware | Not applicable — nearmiss ships no hardware |
| Revised Section 508 — Chapter 5, Software | Yes |
| Revised Section 508 — Chapter 6, Support Documentation and Services | Yes |

---

## Evaluation methods

This conformance report is based on a combined automated and manual evaluation of the `web/` interface
served by `src/nearmiss/server.py`, run against published fixture data so the evaluation is reproducible.

- **Automated testing — axe.** Automated accessibility scanning with axe-core across the map view, the
  list view, the data table, the report form, the hotspot legends, and every chart. axe runs both
  interactively during development and as part of the merge-blocking CI accessibility gate; a new
  violation fails the build. Automated coverage is treated as necessary but not sufficient.
- **Manual screen-reader testing — NVDA (Windows / Firefox).** Full keyboard-only operation of every
  view: tab order, focus management, programmatic name/role/value of controls, table semantics
  (row/column headers and announcements), the map's text/data alternative, legend semantics, and form
  labels and error messages.
- **Manual screen-reader testing — VoiceOver (macOS / Safari).** Independent verification of the same
  flows under a second screen reader and browser, with attention to rotor navigation of headings,
  landmarks, tables, and links, and to announcement of dynamic updates (filter/sort changes) via live
  regions.
- **Manual keyboard testing.** Keyboard-only traversal of all interactive elements with no pointer:
  reachability, operability, visible focus, focus-not-obscured, and absence of keyboard traps.
- **Manual contrast and non-text-contrast inspection.** Text and UI-component/graphical contrast measured
  against the published map and legend color tokens.

The map is an inherently visual artifact. Throughout this report, the **list and data-table view is the
conforming mechanism** that makes the map's visual-only content perceivable and operable without vision.
Every finding the map conveys graphically — ranked location, rate, confidence interval, n, and
statistical-significance flag — is present as text in the equivalent view.

---

## Conformance level (terms) legend

The terms used to describe conformance for each criterion are defined as follows.

| Term | Definition |
| --- | --- |
| **Supports** | The functionality of the product has at least one method that meets the criterion without known defects, or meets it with equivalent facilitation. |
| **Partially Supports** | Some functionality of the product does not meet the criterion. |
| **Does Not Support** | The majority of product functionality does not meet the criterion. |
| **Not Applicable** | The criterion is not relevant to the product. |
| **Not Evaluated** | The product has not been evaluated against the criterion. This term may be used only in the WCAG 2.x Level AAA table. |

---

## Table 1 — Success Criteria, Level A & AA (WCAG 2.0 / 2.1 / 2.2)

Notes apply to all rows: "Supports via equivalent facilitation" means the map's visual-only content is
made conforming by the accessible list and data-table view, which carries the same locations, rates,
intervals, n, and significance flags.

### Level A

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.1.1 Non-text Content** (Level A) | Supports | Map tiles and the KDE/Gi\* surfaces are decorative duplicates of data available in the list/table; the map container exposes a text description and points to the equivalent data view. Charts carry text alternatives summarizing the same numbers. Legend swatches have text labels; no information is in the image alone. Icon-only controls have accessible names. |
| **1.3.1 Info and Relationships** (Level A) | Supports | The data table uses real `<table>` semantics with `<th scope>` row/column headers; views are structured with landmarks and a logical heading hierarchy; the report form uses programmatically associated `<label>`s, `fieldset`/`legend` for grouped inputs, and `aria-describedby` for hint and error text. Ranking, rate, interval, n, and significance are individually labeled columns. |
| **1.4.1 Use of Color** (Level A) | Supports | Risk level and statistical significance are never conveyed by color alone. Significant Gi\* clusters carry a text label and a distinct fill pattern in addition to hue; the list/table states significance as text ("significant hot spot, 95%") and exposes rate, interval, and n numerically. Hard rule 2 (no estimate without an interval) is honored in the non-color encoding. |
| **2.1.1 Keyboard** (Level A) | Partially Supports | All primary functionality — browsing, sorting, filtering, reading every finding — is fully keyboard-operable through the list and table, and the form is fully keyboard-operable. The interactive map's pan/zoom is keyboard-operable, but keyboard selection of an individual map feature ("activate this segment") is still being hardened in beta; the equivalent data view provides full keyboard access to every segment and its statistics in the interim. No keyboard traps were found under NVDA or VoiceOver. |
| **3.3.2 Labels or Instructions** (Level A) | Supports | Every report-form input has a visible, programmatically associated label; required fields are marked in text (not by color or asterisk alone) and via `aria-required`; instructions for location, time, mode, and hazard type are provided inline and associated with their controls via `aria-describedby`. Table sort controls are labeled with their current sort state. |
| **4.1.2 Name, Role, Value** (Level A) | Partially Supports | Native HTML controls (buttons, links, selects, table headers, form fields) expose correct name, role, and value to NVDA and VoiceOver. Custom composite widgets — the sortable column headers and the filter disclosure — expose name/role/state via ARIA and were verified manually. One known beta gap: the map feature-popup needs more robust state announcement when opened via keyboard; tracked and remediated against the equivalent data view, which announces the same content correctly. |

### Level AA

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.4.3 Contrast (Minimum)** (Level AA) | Supports | All body text, table content, labels, and legend text meet at least 4.5:1 against their background; large headings meet at least 3:1. The published map/legend color tokens were chosen and measured to pass; the list/table view uses high-contrast text on solid backgrounds rather than text over imagery. |
| **1.4.11 Non-text Contrast** (Level AA) | Partially Supports | UI component boundaries (form controls, buttons, focus indicators, table sort affordances) and the legend's graphical significance pattern meet 3:1 against adjacent colors. The one open item in beta is contrast of certain KDE intensity bands where they overlap busy basemap tiles at some zoom levels; the equivalent data table conveys the same intensity values as text and numerals, and a basemap-dim option is in remediation. |
| **2.4.7 Focus Visible** (Level AA) | Supports | A visible focus indicator with sufficient contrast is present on every interactive element across map, list, table, and form, verified by keyboard-only traversal under both screen readers. The default indicator is not suppressed; a custom high-contrast outline is applied where needed. |
| **2.5.8 Target Size (Minimum)** (Level AA, WCAG 2.2) | Supports | Evaluated beyond the 508 baseline. Interactive targets in the list, table sort controls, filters, and form controls are at least 24×24 CSS pixels, with adequate spacing; touch targets in the mobile-first report form are sized generously because reports are made from the roadside. Closely spaced map controls that fall below 24px are paralleled by larger equivalents in the list/table toolbar (the spacing/equivalent exception). |

### Selected additional Level A & AA criteria evaluated

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **1.4.4 Resize Text** (Level AA) | Supports | Content reflows and remains usable at 200% zoom; layout uses relative units, and the list/table view reflows to a single column without loss of content or function. |
| **1.4.10 Reflow** (Level AA) | Supports | No horizontal scrolling at 320 CSS px width / 400% zoom for the list, table, and form. The wide data table reflows responsively and exposes a horizontal-scroll region with an accessible name where columns cannot collapse further, which is permitted for tabular data. |
| **2.1.2 No Keyboard Trap** (Level A) | Supports | Verified manually under NVDA and VoiceOver; focus can always move away from the map, popups, and form controls using standard keys. |
| **2.4.3 Focus Order** (Level A) | Supports | Focus order follows reading and operation order across map, list, table, and form; opening a filter or popup does not strand focus. |
| **2.4.6 Headings and Labels** (Level AA) | Supports | Headings and labels are descriptive and honest — for example "Report volume (not danger)" labels raw-count views, per hard rule 1, so the heading itself prevents a misleading reading. |
| **3.2.2 On Input** (Level A) | Supports | Changing a filter or sort does not trigger an unexpected context change; updates are applied predictably and announced via a polite live region. |
| **3.3.1 Error Identification** (Level A) | Supports | Report-form errors are identified in text, associated with the offending field, and announced; the error names the problem (e.g., missing location) rather than relying on color. |
| **4.1.3 Status Messages** (Level AA) | Partially Supports | Filter/sort result counts and form-submission status are announced via `aria-live` regions and verified under NVDA. Under VoiceOver/Safari, some rapid successive status updates are coalesced; messages are not lost but can be delayed. Remediation in progress; no information is unavailable, as the updated table content is itself readable. |

---

## Revised Section 508 Report

### Chapter 3 — Functional Performance Criteria (FPC)

The Functional Performance Criteria apply where Chapter 5 (Software) does not fully address a feature, or
as an overall check that the product is usable by people with the listed disabilities. The list and
data-table equivalent is the primary mechanism by which the visual map satisfies these criteria.

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **302.1 Without Vision** | Supports | The entire analysis is reachable without sight: the accessible list and data table convey every ranked location, rate, confidence interval, n, and significance flag in text, with proper table semantics verified under NVDA and VoiceOver. The map is treated as a redundant visual rendering of this data, not as the sole carrier of any finding. |
| **302.2 With Limited Vision** | Partially Supports | Text and UI contrast meet WCAG AA; content reflows and remains usable at 200%/400% zoom; the list/table is the high-contrast path. The open item is non-text contrast of certain KDE intensity bands over busy basemap tiles at some zoom levels (see 1.4.11); the text/numeric equivalent fully conveys those values, and a basemap-dim control is in remediation. |
| **302.3 Without Perception of Color** | Supports | Risk and significance are encoded with text labels and patterns in addition to color (see 1.4.1); the list/table is fully color-independent. |
| **302.4 Without Hearing** | Supports (no audio) | The product presents no audio content and conveys no information through sound; nothing is lost without hearing. |
| **302.5 With Limited Hearing** | Supports (no audio) | Not relevant beyond 302.4 — there is no audio to perceive. |
| **302.6 Without Speech** | Supports | No operation of the product requires speech input. |
| **302.7 With Limited Manipulation** | Partially Supports | All functionality is operable by keyboard alone without simultaneous or path-based gestures; targets in the list, table, and form meet the 24px minimum size with spacing (see 2.5.8). The beta gap is keyboard selection of an individual map feature (see 2.1.1); the equivalent data view provides single-action access to every segment in the interim. |
| **302.8 With Limited Reach and Strength** | Supports | No functionality requires reach, force, or a sustained physical action; interaction is single, discrete keyboard or pointer actions, and the mobile report form uses large, well-spaced controls. |
| **302.9 With Limited Language, Cognitive, and Learning Abilities** | Supports | Findings are written in plain language for a city-council audience; legends and headings are honest and explicit ("report volume, not danger"); the report form asks plain questions with inline instructions; statistical uncertainty is stated in words alongside the numbers. Interface and form strings live in per-language bundles, and the report form is bilingual where the community is. |

### Chapter 5 — Software

The nearmiss web interface is content rendered in a user-supplied web browser; it is authored as standard
web content using HTML, CSS, and unframework'd JavaScript. Accordingly, conformance is governed primarily
by 502.2 (incorporation of WCAG via 504/E207) and the criteria below; several Chapter 5 sections that
address platform software and assistive-technology authoring do not apply to a read-only web page.

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **501.1 Scope — Incorporation of WCAG 2.0 AA** | Supports | The web content conforms per Table 1 (WCAG A/AA), with the noted beta *Partially Supports* items. The project additionally targets WCAG 2.2 AA. |
| **502.2.1 User Control of Accessibility Features** | Not Applicable | nearmiss is web content, not a platform or assistive technology; it does not disrupt platform accessibility features and exposes none of its own to override. |
| **502.2.2 No Disruption of Accessibility Features** | Supports | The interface uses native semantics and standard ARIA; it does not override or disable browser or OS accessibility features (zoom, high-contrast, screen-reader navigation), verified under NVDA and VoiceOver. |
| **502.3 Accessibility Services** | Not Applicable | The product is not a platform and exposes no accessibility-services API; it relies on the browser's accessibility tree, which it populates correctly (see 4.1.2). |
| **503.2 User Preferences** | Supports | The interface honors browser and OS user preferences — text size, zoom, reduced motion, and color/contrast settings — because it is built on standard reflowable web content with relative units and respects `prefers-reduced-motion`. |
| **503.4 Authoring Tools** | Not Applicable | nearmiss does not author content for others; it renders a published dataset read-only. |
| **504.2 Content Creation or Editing (Authoring Tools)** | Not Applicable | The product is not an authoring tool. |
| **E207.2 WCAG Conformance (Software with a user interface)** | Partially Supports | The user interface meets WCAG 2.0/2.1 Level A and AA except for the beta items noted in Table 1 (2.1.1, 1.4.11, 4.1.2, 4.1.3, 2.5.8 exception), each with a working text/data equivalent and an open remediation item. |

### Chapter 6 — Support Documentation and Services

| Criteria | Conformance level | Remarks and explanations |
| --- | --- | --- |
| **602.2 Accessibility and Compatibility Features (documentation)** | Supports | Project documentation describes the accessibility features and the non-visual list/table equivalent: the README's "Accessibility and Section 508 conformance" section, the methodology doc, and this ACR explain how to reach every finding without vision and how the equivalent view works. |
| **602.3 Electronic Support Documentation** | Supports | All support documentation is provided as accessible electronic content — Markdown and rendered HTML that themselves conform to WCAG 2.0 AA: real headings, list and table semantics, descriptive link text, and no information by color alone. This ACR and the README are lint-clean Markdown. |
| **602.4 Alternate Formats for Non-Electronic Support Documentation** | Not Applicable | There is no non-electronic (printed) support documentation; all documentation is electronic and accessible. |
| **603.2 Information on Accessibility and Compatibility Features (support services)** | Supports | Support is provided through the public GitHub repository. Accessibility issues can be filed via issue templates, and the maintainer treats accessibility regressions as merge-blocking; this ACR names the contact and the standards targeted. |
| **603.3 Accommodations for Communication Needs (support services)** | Partially Supports | The single-maintainer project offers support through GitHub issues and email, which are text-based and screen-reader accessible. It cannot guarantee alternative real-time channels (e.g., phone or video relay) given its independent, unfunded status; this limitation is stated honestly rather than overclaimed. |

---

## Legal disclaimer

This Accessibility Conformance Report is provided by the nearmiss maintainer for informational purposes
and represents a good-faith, evidence-based evaluation of a beta product against the standards listed
above. nearmiss is an independent personal open-source project licensed under Apache-2.0, unaffiliated
with any employer or client, and contains no proprietary or client material. It is not federal ICT and is
under no legal obligation to conform to Section 508; conformance is pursued voluntarily. Conformance is
re-evaluated and this report is regenerated and re-committed on each release. The accessibility CI gate
(axe plus committed manual NVDA/VoiceOver review notes in `docs/audits/`) is merge-blocking, so the claims
here are tied to checks that run, not to aspiration.
