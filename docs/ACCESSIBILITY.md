# Accessibility statement and approach

**Last reviewed:** 2026-08-14
**Conformance target:** WCAG 2.2 Level AA, and conformance with the Revised Section 508
Standards (36 CFR Part 1194).
**Maintainer:** Chelsea Kelly-Reif (GitHub [@ChelseaKR](https://github.com/ChelseaKR)).

This is a living statement. It describes what nearmiss commits to, how that commitment is
tested, and how to tell us when we have fallen short. It is meant to hold up the same way the
statistics are meant to hold up: when a skeptical reviewer pushes back, the claims here should
survive scrutiny.

**If you use a screen reader, read this first.** No part of nearmiss has been tested by a human
using a screen reader. Two automated gates run on every change and both pass, but automated tooling
catches at best roughly half of real barriers, and one of the two gates cannot see the parts of the
studio that JavaScript builds. Section 6 states exactly what has and has not been checked. Nothing in
this document should be read as "a blind user has successfully used this," because as of the review
date above, to our knowledge, none has been asked to and none has reported back.

---

## 0. Scope: which surfaces this statement covers

The public site serves six HTML documents across seven routes. The repository also keeps three
source-only surfaces that are exercised by the accessibility gates but are **not** deployed.

| Surface | Route(s) on the live site | Per-criterion ACR coverage |
| --- | --- | --- |
| Evidence-to-action gateway (`index.html`) | `/` | **Not covered** |
| Error page (`404.html`) | `/404.html` | **Not covered** |
| Legacy redirect stub (`web/index.html`) | `/web/index.html` | **Not covered** |
| Nationwide FARS evidence studio (`web/us-coverage.html`) | `/fars/national/`, `/web/us-coverage.html` | **Not covered** — explicitly excluded by the ACR |
| Studio (`web/studio.html`) | `/studio/` | **Not covered** |
| Decision dossier sample (`web/dossier.html`) | `/dossier/` | **Not covered** |
| Davis synthetic methods lab (`web/davis-demo.html`) | not deployed — source/CI fixture | This is the surface the ACR's tables evaluate |
| Submission prototype (`web/submit.html`) | not deployed — source/CI fixture | **Not covered** |
| Embed fixture (`web/embed.html`) | not deployed — source/CI fixture | **Not covered** |

Two things follow from that table, and both are stated here rather than left to be discovered:

1. **No page the public can load has per-criterion ACR coverage.** The
   [ACR](accessibility/ACR.md) evaluates the former `index.html` + `app.js` + `style.css` map/table
   surface, retained source-only as `davis-demo.html`. Extending the ACR to the deployed pages
   requires evaluating them, which has not been done; a row invented without an evaluation would be
   the exact failure this project exists to refuse. The honest position is the gap, named.
2. **The published advocacy brief and data card are text, not web pages.** `nearmiss brief` renders
   Markdown and plain text (`src/nearmiss/brief.py`); there is no HTML brief anywhere in `web/`, and
   no automated accessibility gate runs against a brief.

Sections 3, 4, 5, and 7 describe mechanisms in the `web/` sources, including the source-only
surfaces. Where a mechanism belongs to a surface the public cannot load, that is said in place.

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

The nationwide FARS evidence studio applies the same rule to a different measure. Its selected-year
map, matrix, rank, mode-comparison plot, state comparison, inspector, and complete ledger are derived
from one exact reviewed annual state-by-mode count artifact; the five-year profile reads the five
separately pinned annual artifacts. The semantic matrix, comparison table, five-year profile table,
and complete ledger provide the state, involved mode, published count, and publication status without
requiring the SVG views. A non-published value is always written as **suppressed or zero**, never
silently converted to zero.

The national SVG map states and mode-comparison plot points are implemented as named `role="button"`
controls with a single roving tab stop, arrow/Home/End navigation, and Enter/Space activation; the
state and mode selectors and the table controls provide native-HTML paths to the same evidence. The
automated gates and a targeted rendered-browser keyboard and 390×844 reflow pass are green. These are
not a completed conformance finding: human NVDA/VoiceOver review and the 200% zoom pass remain pending
and are tracked in
[`docs/audits/2026-07-16-national-evidence-studio-a11y.md`](audits/2026-07-16-national-evidence-studio-a11y.md).
That record uses the solo-maintainer policy in
[`ADR 0012`](adr/0012-solo-maintainer-provisional-review-attestation.md) to permit a bounded public
preview with owner-accepted residual risk. It does not convert any pending check into a pass.

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

> **Not a deployed surface.** `web/submit.html` is a source-only prototype: it runs through the
> structural and axe gates, and it is **not** part of the published artifact (see section 0). The
> commitments below describe what that prototype implements and what any deployed form would have to
> implement; they are not a statement about a form the public can currently use.

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

Localization is **partially delivered** (see Localizability in the README). What ships publicly
today: the nationwide FARS studio is **bilingual (English/Spanish)**. The source-only local methods
and submission prototypes remain automated accessibility targets but are not part of the production
artifact. The hazard-report issue form is also bilingual,
[`schema/report.schema.json`](../schema/report.schema.json) carries an optional BCP-47 `language`
field, and the advocacy brief renders in English or Spanish (`nearmiss brief … --lang es`, with
per-language bundles in `src/nearmiss/i18n.py`). What is **not yet delivered**: languages beyond
English/Spanish and deeper localization of the data-driven prose (e.g. the bias note). The goal is that a contributor is
not forced into English to report a hazard on their own street; we are part of the way there.

---

## 6. Testing: what has been checked, and by what

A conformance claim needs two layers. **One of them runs. The other has never been performed.** This
section separates them, because the difference is the whole of what a reader needs to know.

### 6.1 What runs today (automated)

Two automated gates run locally and in CI on every pull request, and both are merge-blocking.

- **Structural gate** — [`tools/a11y_check.py`](../tools/a11y_check.py), part of `make verify` and
  `make accessibility`. Dependency-free, and checks the page-level foundations: a language, a title,
  landmarks and a heading, labeled data tables (`<caption>`, `<th scope>`), a skip link, and image
  alternatives. It confirms the scaffolding is present; it says nothing about how the page behaves.
- **axe-core in jsdom** — `make axe` → [`web/package.json`](../web/package.json) →
  [`web/axe_check.mjs`](../web/axe_check.mjs). It runs against **nine files**: `index.html`,
  `404.html`, `web/index.html`, `web/davis-demo.html`, `web/submit.html`, `web/embed.html`,
  `web/us-coverage.html`, `web/studio.html`, and `web/dossier.html`. Every one currently passes with
  no violations.

Three limits on the axe run, stated because they are easy to miss and they matter:

1. **It is a static-DOM scan, not a rendered-browser one.** `axe_check.mjs` parses each file's
   shipped HTML into jsdom with `runScripts: "outside-only"` — page scripts do not execute. Any view
   built at runtime by JavaScript, including the studio's national map, its state-by-mode matrix, and
   every data row in it, is **not in the DOM this scan inspects**. What axe checks there is the
   static shell.
2. **Colour contrast is switched off in this run.** jsdom has no layout and no canvas, so rendered
   contrast cannot be computed; enabling the rule would produce a meaningless result rather than a
   real one. Contrast is instead reasoned about from the documented CSS tokens, and a measured pass
   against the rendered page has not been performed.
3. **Automated tooling catches at best roughly half of real barriers**, even on the DOM it does see.

One narrower gate does exercise a JavaScript-populated DOM: the national studio's consumer contract
([`web/us_coverage_check.mjs`](../web/us_coverage_check.mjs), run by `make web-check`) drives the
studio's views in jsdom and runs axe against the populated result. That is still jsdom, still without
the contrast rule, and still not a browser.

There are **no brief pages** in any of these scans, and there never have been: `nearmiss brief`
emits Markdown and plain text (`src/nearmiss/brief.py`), not HTML.

### 6.2 What has never been performed (manual screen-reader review)

**No manual screen-reader testing has been performed.** Not on the studio, not on the gateway, not
on the source-only Davis map and table, not on any release. This is the same sentence the
[ACR](accessibility/ACR.md) carries, and where this statement and the ACR ever disagree, **the ACR
is the source of truth**.

The evidence for that, in the project's own records:

- [`docs/accessibility/ACR.md`](accessibility/ACR.md) — "No manual screen-reader testing has been
  performed"; every per-criterion verdict that depends on it is marked *(target)*, not a finding.
- [`docs/audits/2026-07-16-national-evidence-studio-a11y.md`](audits/2026-07-16-national-evidence-studio-a11y.md)
  — NVDA + Firefox, VoiceOver + Safari (macOS), and VoiceOver + Safari (iOS) are each recorded as
  **Not performed**, with "no human screen-reader evidence"; actual browser 200% zoom is likewise
  **Not performed**.
- [`docs/audits/`](audits/) holds two audit artifacts and a README. Neither artifact is a manual
  screen-reader review, because none has happened.

The required matrix is **NVDA** (Firefox, on Windows) and **VoiceOver** (Safari, on macOS and iOS).
Those checks are **outstanding**. When they are performed, these are the journeys they will exercise
— the list is a commitment, not a record:

- read the ranked findings from the **table** end to end and confirm rates, intervals, and
  significance flags are announced;
- operate **column sorting** by keyboard and confirm the new order and sort state are announced;
- traverse the nationwide **state map and mode-comparison plot** without a pointer, activate a state
  with Enter and Space, and confirm focus remains visible and stable after linked views redraw;
- read the nationwide **matrix, comparison table, five-year profile, and complete ledger**, and
  confirm that their counts and publication-status text provide the information in the visual views;
- confirm **no information is lost** when color is removed (grayscale / forced-colors pass);
- confirm the **gateway, studio, and dossier** pages are navigable and readable end to end, since
  those are the pages the public actually lands on.

Each performed pass will be logged in [`docs/audits/`](audits/) with the exact assistive-technology
and browser versions, the date, the flows exercised, and what was found — the same record any other
audit here carries. Keyboard-only testing (no pointer) is part of a manual pass.

### 6.3 The one thing that is neither

For the nationwide evidence studio, a targeted **in-app browser** keyboard and 390×844
narrow-viewport pass is recorded in the 2026-07-16 review, along with CSS-viewport proxies standing
in for 200% and 400% zoom. Those found and closed six real defects, and they are recorded as what
they are: automated and simulated evidence, explicitly not a conformance result and explicitly not a
screen-reader result. While this project has one accountable maintainer,
[ADR 0012](adr/0012-solo-maintainer-provisional-review-attestation.md) allows that evidence plus an
explicit, expiring owner attestation to provisionally satisfy the REVIEW-GATE for a time-bounded
public preview. The audit must identify the exact evidence, the unperformed checks, the residual
risk, the rollback, and the expiry. It converts nothing pending into a pass, and the human work
stays open.

---

## 7. Accessibility is a merge-blocking CI gate

Accessibility is enforced the same way lint, types, tests, and security are enforced: as a gate
that blocks the merge.

- The **axe** automated pass is a required status check. A new color-only legend, an unlabeled
  field, or a table that loses its header semantics **fails the build**, and the pull request
  cannot merge until it is fixed.
- **A contrast regression does not.** This list said it did until 2026-08-28, and it could not:
  `color-contrast` is disabled in every axe run this repository performs (`web/axe_check.mjs`
  and `web/us_coverage_check.mjs`, both `rules: { "color-contrast": { enabled: false } }`),
  because jsdom has no layout or canvas to compute rendered contrast against, and no other
  test computes it. § 6.1 already said so plainly; this section contradicted it. Contrast is
  reasoned about from the documented CSS tokens (`docs/BRAND.md`) and is a **manual** item, not
  a gate. `tests/test_accessibility_claims.py::test_no_document_claims_contrast_is_gated_while_the_rule_is_off`
  now fails if this claim comes back while the rule stays off — and equally, if the rule is ever
  enabled, that is the moment to say so here.
- The gate sits alongside the other CI gates already committed to in the README — ruff, mypy
  `--strict`, pytest, security (pip-audit, gitleaks, CodeQL), pinned and hashed deps — so an
  accessibility regression is exactly as much of a blocker as a failing test or a leaked secret.
- The list/table-equivalence assertion (the map and the non-visual view are built from one
  source) is a normal test in the suite, so the equivalent view cannot silently rot.

Manual screen-reader review is **not** fully automatable and therefore is not a per-PR status
check; it is a stable-release and conformance gate to be recorded in `docs/audits/` — a gate that
has not yet been exercised (section 6.2), so no release to date has passed it. Automated
accessibility checks block every merge. A one-person, explicitly labeled public preview may proceed
only through ADR 0012's provisional REVIEW disposition: all AUTO-GATEs stay mandatory; a dated
artifact records exact synthetic/browser evidence, checks not performed, owner-accepted residual
risk, rollback, and expiry. That disposition is neither a manual pass nor permission to claim WCAG,
Section 508, or ACR conformance.

---

## 8. Known limitations

Honesty about limits is a hard rule for the statistics; it applies here too.

- A web map is inherently a spatial, visual artifact. We meet the bar by providing a complete
  non-visual equivalent (section 3), not by claiming the map graphic is itself a full
  experience for a non-visual user. The **table is the equivalent of record**; if the two ever
  disagree, the table is correct and the map is the bug.
- nearmiss is maintained by **one person**. There is no in-house accessibility team and no paid
  external audit. The current mitigations are the automated gates, a provisional review record that
  keeps unperformed NVDA/VoiceOver checks visible, an honest ACR, and a fast path for users to report
  barriers (section 10). Reports
  from real assistive-technology users are weighted heavily and are the most valuable kind of
  feedback this project can get.
- The required manual matrix is NVDA + Firefox and VoiceOver + Safari, and **those checks have not
  been performed on any surface** — not the national studio, not the gateway, not the source-only
  Davis map and table (section 6.2). JAWS, TalkBack, and other combinations are not in a cycle
  either; barriers reported in any of them are still triaged and fixed, and any divergence is
  recorded in the ACR rather than hidden.
- **No page the public can load carries per-criterion ACR coverage** (section 0). The ACR evaluates
  the source-only `davis-demo.html` surface. Widening it is real evaluation work, not a documentation
  edit, so the gap is named rather than papered over with rows nobody earned.

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

**Intended cadence:** the ACR is an audit artifact, to be re-evaluated and re-committed on each
release — the same audit-as-artifact discipline applied to the statistics, where every published
number records its method and source. A release whose accessibility behavior changed but whose ACR
did not is a defect.

**Actual state, stated plainly:** that cadence is a commitment this project has not yet kept. The
ACR carries a **report date of 2026-06-17** and has not been re-issued for any tagged release. It
therefore predates every surface the public site now serves. The ACR says so in its own banner; this
statement says so too, so a reader does not have to click through to find it out.

The ACR carries its own evaluation date, the methods actually used, the checks still outstanding, and
the version of the site evaluated, so a city reviewer can see exactly what was tested and when. A
provisional public preview does not alter an ACR row or count a planned manual method as performed.

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
acknowledge a report within a few days, to ship the fix in the normal release cycle with the change
noted, and to update the ACR to match — a cadence section 9 records as not yet kept, so read it as
the commitment it is. If a barrier blocks you from getting a finding out of
the map entirely, tell us that — the non-visual equivalent failing is the most serious kind of
bug this project can have.
