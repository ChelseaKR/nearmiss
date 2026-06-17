# Accessibility statement and approach

**Last reviewed:** 2026-06-16
**Applies to:** the nearmiss web map and table view (`src/nearmiss/server.py` + `web/`),
the report form, and the published advocacy briefs and data card.
**Conformance target:** WCAG 2.2 Level AA, and conformance with the Revised Section 508
Standards (36 CFR Part 1194).
**Maintainer:** Chelsea Kelly-Reif (GitHub [@ChelseaKR](https://github.com/ChelseaKR)).

This is a living statement. It describes what nearmiss commits to, how that commitment is
tested, and how to tell us when we have fallen short. It is meant to hold up the same way the
statistics are meant to hold up: when a skeptical reviewer pushes back, the claims here should
survive scrutiny.

---

## 1. Conformance target

nearmiss targets **WCAG 2.2 Level AA** for all web content, and conformance with the **Revised
Section 508 Standards (36 CFR Part 1194)**.

The Revised 508 Standards incorporate **WCAG 2.0 Level A and AA** by reference for web content
(E205.4 / 508 Chapter 5) and add the **Functional Performance Criteria** of Chapter 3 — usable
without vision, with limited vision, without perception of color, without hearing, with limited
hearing, without speech, with limited manipulation and strength, and with limited reach and
cognition. We hold ourselves to WCAG **2.2** AA rather than the 2.0 baseline that 508
references, because 2.2 is the current standard and adds criteria (focus appearance, dragging
movements, target size, accessible authentication, consistent help, redundant entry) that
matter directly for a map and a report form used on a phone at the roadside.

Where this statement says "508 conformance," it means: WCAG 2.2 AA web content **plus** the
Chapter 3 Functional Performance Criteria **plus** the Chapter 6 support-documentation
requirements. The detailed criterion-by-criterion mapping lives in the Accessibility
Conformance Report at [`docs/accessibility/ACR.md`](accessibility/ACR.md) (see
[section 9](#9-the-acr-vpat-25-rev-508)).

---

## 2. Why a community project builds to a federal standard it is not legally bound by

nearmiss is an independent personal open-source project. It is not federal ICT, it is not
procured by a federal agency, and it is not a city service. Section 508 is, strictly, not
legally required here. Building to it anyway is a deliberate decision, for three reasons.

1. **The audience is disproportionately disabled.** A near-miss map exists for the people most
   endangered on bad streets. Disabled road users — people with low vision navigating a blind
   corner, wheelchair and mobility-device users forced into a travel lane by a blocked curb
   ramp, people who cannot sprint out of a door zone — absorb more of the risk and have fewer
   ways to avoid it. They are among the most likely people to be reading a map of where it is
   unsafe to travel, and to be filing the reports that build it. A safety tool that is itself
   inaccessible excludes exactly the users it claims to serve. That is not acceptable, and no
   exemption from a legal duty changes it.

2. **The standard agencies audit to is the credible standard.** nearmiss exists to put an
   honest analysis in front of cities, transportation departments, and councils. Those agencies
   are themselves bound by Section 508, and they assess procured and referenced ICT against it.
   When an advocate brings this analysis to a public hearing, "the dataset, the map, and the
   table all conform to the Revised 508 Standards, and here is the ACR" removes an entire class
   of objection and signals that the work was done to a professional bar. An advocacy artifact
   that the agency could not itself lawfully republish would undercut its own argument.

3. **Accessibility and statistical honesty are the same discipline.** The
   [five hard rules](../README.md#hard-rules-enforced-not-aspirational) refuse to let a pretty
   surface stand in for a defensible claim — no rate without a denominator, no estimate without
   an interval, bias named rather than hidden. Refusing to let a color-coded heat map stand in
   for a finding a blind user can actually read is the same refusal. A finding that only exists
   as a hue on a map does not exist for everyone, and a project whose whole premise is "do not
   lie with a map" cannot ship a map that silently excludes part of its audience.

Section 508 is the floor we choose. The Functional Performance Criteria — "can a person who
cannot see use this to get the same information?" — are the test we actually care about.

---

## 3. The non-visual equivalent of the map

The single most important accessibility commitment in nearmiss: **every finding on the map is
reachable, in full, without seeing the map.**

The map is one view of a published artifact, not the artifact itself. The same published
GeoJSON that draws the map also drives an accessible, sortable **list and table** view that
carries the identical content:

- the **ranked locations** (street segments / intersections), in the same order the map
  emphasizes;
- the **exposure-normalized rate** for each, never a raw count presented as risk (hard rule 1);
- the **confidence interval and n** for each rate (hard rule 2), so a small-sample segment
  reads as uncertain in the table exactly as it does on the map;
- the **statistical-significance flag** from the Getis-Ord Gi\* analysis (significant hot
  cluster / not significant / exposure unknown), in words, not as a swatch;
- the **reporting-bias caveats** (hard rule 3) attached to the view, so a screen-reader user
  is not handed a ranked list stripped of the warning that gives it meaning.

The table is a real `<table>` with a programmatic header row (`<th scope="col">`), associated
captions, and per-column sorting that is operable by keyboard and announced to assistive
technology (each sortable header exposes its sort state via `aria-sort`). The list/table view
is **not** a degraded fallback bolted on at the end; it is generated from the same data in the
same pipeline stage and is covered by the same merge gate. If a number can be read off the map,
it can be read off the table, and the test suite asserts that the two views are built from one
source so they cannot drift apart.

This is the Functional Performance Criterion "use without vision" made concrete: a person using
a screen reader gets the ranked locations, the rates, the intervals, and the significance — the
entire analysis — without the visual layer.

---

## 4. Never conveying risk or significance by color alone

WCAG 1.4.1 (Use of Color) is treated as a hard line, not a nicety, because color-only encoding
is exactly how a map lies to a colorblind reader and, more quietly, to everyone reading a
small phone screen in sunlight.

- **Risk level** (how dangerous a segment's rate is, relative to others) is encoded
  **redundantly**: a text label, a non-color visual pattern (hatching / texture / distinct
  marker shape), and only then a color from a checked, AA-contrast palette. The text label is
  the source of truth; the color is decoration on top of it.
- **Statistical significance** (the Gi\* hot-cluster result) is shown as **text and pattern**,
  never as "red means significant." A significant cluster is labeled in words and rendered with
  a distinct outline/pattern, so removing color entirely never removes the finding.
- **Uncertainty** (wide intervals, small n) is shown with text and visual treatment, not by a
  faded color a low-vision user cannot distinguish from a saturated one.
- Map legends, chart legends, and the table all state the encoding in words. Every chart in a
  brief is checked so that converting it to grayscale loses no information.

Contrast meets WCAG 1.4.3 (text) and 1.4.11 (non-text/UI components and graphical objects),
verified in the automated pass and spot-checked manually. Color is allowed to *reinforce* a
distinction; it is never allowed to be the *only* carrier of one.

---

## 5. The report form: keyboard operability, labels, and errors

The intake form (the contributor-facing front of `intake.py`) is the place where a real person,
often on a phone at the roadside, hands us a report. It is held to the same bar as the map.

- **Fully keyboard-operable.** Every control is reachable and operable with the keyboard alone,
  in a logical tab order, with a visible focus indicator that meets WCAG 2.2's focus-appearance
  requirement (2.4.11 / 2.4.13). There are no keyboard traps (2.1.2). Any pointer gesture has a
  keyboard- and single-pointer-operable alternative (2.5.1, 2.5.7); choosing a location never
  *requires* a drag on a map.
- **Programmatic labels.** Every field has a real, persistent `<label>` (placeholder text is
  never used as the only label), required fields are marked in text and via `aria-required`,
  and grouped controls (mode, hazard type, severity) use `<fieldset>`/`<legend>`. Labels and
  instructions meet 3.3.2.
- **Clear, specific errors.** Validation against
  [`schema/report.schema.json`](../schema/report.schema.json) surfaces as plain-language,
  field-associated error text (3.3.1, 3.3.3): which field, what is wrong, and how to fix it —
  never a color-only red border and never a generic "invalid input." Errors are associated with
  their field via `aria-describedby` and announced to assistive technology.
- **No needless re-entry.** Consistent with WCAG 2.2's Redundant Entry (3.3.7): information the
  contributor already provided in a session is not demanded again.
- **Target size and reach.** Interactive targets meet the 2.5.8 minimum, because this form is
  used one-handed on a phone, and that directly serves the "limited manipulation, reach, and
  strength" Functional Performance Criteria.
- **Privacy is accessible too.** The form is plain about what it collects and that no precise
  report coordinate is ever published — reports are aggregated to public street segments before
  anything is published (hard rule 4); that notice is part of the accessible content, not buried
  in fine print a screen reader skips.

Localization (per-language string bundles, a bilingual report form, and a language field in the
schema) is **planned, not yet delivered** (see Localizability in the README). Today the interface
and the report form are **English-only**: the form does not yet bundle its strings per language,
and [`schema/report.schema.json`](../schema/report.schema.json) has no language field. The goal is
that a contributor is not forced into English to report a hazard on their own street; we are not
there yet.

---

## 6. Testing: automated and manual

Conformance is verified, not asserted. Two layers, both required.

**Automated.** [axe-core](https://github.com/dequelabs/axe-core) runs against the rendered map,
table, report form, and brief pages in CI on every pull request. axe catches the machine-checkable
failures — missing labels, contrast violations, broken name/role/value, invalid ARIA, structural
problems — fast and on every change.

**Manual screen-reader review.** Automated tools catch at best roughly half of real barriers, so
nearmiss does not stop there. Each release is walked through with **NVDA** (Firefox, on Windows)
and **VoiceOver** (Safari, on macOS/iOS), exercising the journeys that matter:

- read the ranked findings from the **table** end to end and confirm rates, intervals, and
  significance flags are announced;
- operate **column sorting** by keyboard and confirm the new order and sort state are announced;
- complete the **report form** by keyboard and screen reader, including triggering and recovering
  from a validation error;
- confirm **no information is lost** when color is removed (grayscale / forced-colors pass).

Manual review is logged in [`docs/audits/`](audits/) so each release has a record of what was
checked, with what tool, and what was found. Keyboard-only testing (no pointer) is part of every
manual pass.

---

## 7. Accessibility is a merge-blocking CI gate

Accessibility is enforced the same way lint, types, tests, and security are enforced: as a gate
that blocks the merge.

- The **axe** automated pass is a required status check. A new color-only legend, an unlabeled
  field, a contrast regression, or a table that loses its header semantics **fails the build**,
  and the pull request cannot merge until it is fixed.
- The gate sits alongside the other CI gates already committed to in the README — ruff, mypy
  `--strict`, pytest, security (pip-audit, gitleaks, CodeQL), pinned and hashed deps — so an
  accessibility regression is exactly as much of a blocker as a failing test or a leaked secret.
- The list/table-equivalence assertion (the map and the non-visual view are built from one
  source) is a normal test in the suite, so the equivalent view cannot silently rot.

Manual screen-reader review is **not** fully automatable and therefore is not a per-PR status
check; it is a release-blocking step in the release checklist, recorded in `docs/audits/`. The
rule is simple: automated accessibility checks block every merge; manual screen-reader review
blocks every release.

---

## 8. Known limitations

Honesty about limits is a hard rule for the statistics; it applies here too.

- A web map is inherently a spatial, visual artifact. We meet the bar by providing a complete
  non-visual equivalent (section 3), not by claiming the map graphic is itself a full
  experience for a non-visual user. The **table is the equivalent of record**; if the two ever
  disagree, the table is correct and the map is the bug.
- nearmiss is maintained by **one person**. There is no in-house accessibility team and no paid
  external audit. The mitigations are the automated gate, documented manual NVDA/VoiceOver
  passes, an honest ACR, and a fast path for users to report barriers (section 10). Reports
  from real assistive-technology users are weighted heavily and are the most valuable kind of
  feedback this project can get.
- Manual review currently covers NVDA + Firefox and VoiceOver + Safari. JAWS, TalkBack, and
  other combinations are not yet in the regular cycle; barriers found there are still triaged
  and fixed, and any divergence is recorded in the ACR rather than hidden.

These limitations are stated in the ACR as well, so a reader of the formal report sees the same
caveats a reader of this statement sees.

---

## 9. The ACR (VPAT 2.5 (Rev 508))

A committed **Accessibility Conformance Report** lives at
[`docs/accessibility/ACR.md`](accessibility/ACR.md), authored on the **VPAT 2.5 (Rev 508)**
template. It contains the standard tables:

- **Table 1 — WCAG 2.x Report**, the Level A and Level AA success criteria, each marked
  Supports / Partially Supports / Does Not Support / Not Applicable, with remarks. nearmiss
  reports against WCAG **2.2** AA (a superset of the 2.0 A/AA that 508 references).
- **Table 2 — Revised Section 508 Report**, covering the Chapter 3 **Functional Performance
  Criteria**, Chapter 5 (Software), and Chapter 6 (Support Documentation and Services).

The ACR is treated as an **audit artifact, regenerated and re-committed on each release** — the
same audit-as-artifact discipline applied to the statistics, where every published number records
its method and source. A release whose accessibility behavior changed but whose ACR did not is a
defect. The ACR carries its own evaluation date, the methods used (axe + manual NVDA/VoiceOver),
and the version of the site evaluated, so a city reviewer can see exactly what was tested and when.

An ACR is a self-assessment by the maintainer, not a third-party certification, and it says so on
its face. Conformance claims in the ACR are scoped to the evaluated release.

---

## 10. Reporting an accessibility barrier

If any part of nearmiss is hard or impossible to use with your assistive technology, that is a
bug we want to fix, and your report is the most useful kind of feedback this project receives.

- **Open an issue** on the repository: <https://github.com/ChelseaKR/nearmiss/issues>. Please
  use the accessibility issue template if one is offered. You do **not** need to know the WCAG
  criterion or use any technical terms — "I use NVDA and I could not tell which streets were the
  dangerous ones from the table" is a perfect report.
- If you would rather not post in public, contact the maintainer through the GitHub profile at
  <https://github.com/ChelseaKR>.

**What helps us fix it faster** (all optional): the page or view, your browser and assistive
technology and their versions, what you were trying to do, and what happened instead.

**What to expect.** As a single-maintainer project there is no staffed support desk and no
contractual SLA, but accessibility barriers are triaged as high-priority defects: we aim to
acknowledge a report within a few days, and fixes ship in the normal release cycle with the
change noted and the ACR updated to match. If a barrier blocks you from getting a finding out of
the map entirely, tell us that — the non-visual equivalent failing is the most serious kind of
bug this project can have.
