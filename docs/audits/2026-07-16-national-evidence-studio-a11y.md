# National evidence studio accessibility review — 2026-07-16

**Kind:** pre-release accessibility component review
**Surface:** `web/us-coverage.html`, `web/us-coverage.js`, and
`web/us-coverage-studio.css`
**Release / commit:** pre-commit working tree; exact commit pending
**Target:** WCAG 2.2 Level AA and Revised Section 508 functional performance criteria
**Summary verdict:** **Incomplete — not a conformance result.** The structural and axe gates pass,
and a targeted rendered-browser keyboard and narrow-viewport review found no release defect. The
required human NVDA and VoiceOver reviews, an uninterrupted end-to-end keyboard pass, and the 200%
zoom check have not been performed.

This file is a pre-release checklist and evidence placeholder, not proof that a manual accessibility
audit occurred. A pending row must not be cited as a pass. Replace each pending row with the exact
environment, command or assistive-technology version, date, result, and findings only after the check
is actually performed.

## Evidence status

| Review layer | Environment / method | Status | Evidence |
| --- | --- | --- | --- |
| Source and DOM-contract inspection | Direct review of the pre-commit HTML, CSS, and JavaScript | Complete as implementation inspection only | Mechanisms listed below; no conformance verdict |
| Structural accessibility gate | `make verify PYTHON=.venv/bin/python` → `make accessibility` | **Pass** | `tools/a11y_check.py` passed `index.html`, `submit.html`, `embed.html`, and `us-coverage.html` |
| Automated axe scan | `make verify PYTHON=.venv/bin/python` → `npm run axe`; rendered studio contract also runs axe | **Pass** | No axe violations in the static national page or its rendered canonical-route DOM |
| Targeted desktop browser keyboard pass | In-app Chromium surface (version not exposed), 1280×720, 2026-07-16 | **Pass for the recorded flows** | Five linked views, roving focus, state activation, scatter redraw, comparison, brief save, deep links, and language switching verified; this was not an uninterrupted full-tab-order audit |
| Mobile / narrow-viewport pass | In-app Chromium surface (version not exposed), 390×844, 2026-07-16 | **Pass at the recorded viewport** | Single-column reflow, two-column view switcher, one-column filters, 306-row ledger, 24px control minimum, map keyboard selection, and no document-level horizontal overflow verified |
| 200% browser zoom | Browser zoom to be recorded | **Not performed** | The narrow-viewport pass is not being represented as a 200% zoom result |
| NVDA + Firefox | Windows, NVDA version, and Firefox version to be recorded | **Not performed** | No human screen-reader evidence |
| VoiceOver + Safari | macOS, VoiceOver version, and Safari version to be recorded | **Not performed** | No human screen-reader evidence |

## Implemented mechanisms observed in source

These observations combine source inspection with the targeted browser evidence above; they are not
screen-reader findings:

- The national SVG map uses one roving tab stop across 51 named `role="button"` state/DC groups.
  Arrow keys and Home/End move within the group; Enter and Space select. Each name contains the state,
  involved mode, and either its published count or its non-published status.
- Map selection redraws the linked views and restores focus to the selected state. ArrowRight from
  Alabama moved focus to Alaska, and Enter selected Alaska while retaining `map:AK` focus and loading
  its exact 2020–2024 profile.
- Matrix cells, rank rows, and published mode-comparison points use the same single-tab-stop roving
  model. Scatter focus remained on Arkansas after Enter selected it and the linked plot redrew.
- Native year, state, mode, publication-status, secondary-mode, scale, and comparison-state controls
  provide non-SVG ways to change the analysis.
- The state-by-mode matrix, accessible mode-comparison table, five-year state profile, and complete
  evidence ledger use semantic tables with captions and scoped headers. Rank and inspector actions use
  native buttons. Visual-view switching uses buttons with `aria-pressed`; inactive panels are hidden.
- The map and matrix use hatching plus publication-status text for non-published cells. The complete
  ledger labels these values “suppressed or zero” and does not expose them as numeric zero.
- Loading, profile, and brief updates have polite live regions in the HTML. Their timing and wording
  under assistive technology have not been manually verified.

## Recorded targeted browser findings

- The whole-country default rendered all 51 jurisdictions, 306 state × involved-mode ledger rows,
  51 map groups, 51 matrix rows, and 306 matrix cells from the selected annual artifact.
- Map, matrix, rank, and scatter each exposed one roving tab stop. Arrow navigation moved focus within
  the active visualization without adding every datum to the page tab order.
- Matrix selection updated state, mode, inspector, profile, ledger, and URL. Rank, scatter, and state
  comparison rendered the matching published and non-published values from the same artifact.
- A scatter-point Enter action preserved focus after redraw. Switching years loaded the exact
  historical artifact and its semantic regime; the profile continued to show the separately pinned
  five-year evidence.
- Saved state comparisons, copy-link recovery messaging, and English/Spanish switching preserved the
  complete URL state. Clipboard access was unavailable in the browser harness; the UI exposed the
  intended plain-language fallback instead of reporting a false success.
- At 390×844, the document had no horizontal overflow, the studio and filters reflowed to one column,
  analytic tables retained their own scroll regions, and all rendered non-inline controls met the
  24×24 CSS-pixel target minimum. Only inline provenance/source links were below 24px in height, which
  fall under the inline target-size exception.
- The browser console contained no warnings or errors during either desktop or narrow-viewport flows.

## Remaining manual keyboard and zoom script

Record results for the remaining steps with no pointer:

1. Run one uninterrupted skip-link and full-tab-order pass, including focus visibility and every
   inactive panel's exclusion from the tab order.
2. Repeat map and scatter activation with Space, and exercise matrix Home/End and vertical arrow keys.
3. Remove individual brief items and clear the brief using only the keyboard.
4. Read the matrix, comparison table, five-year profile, and complete ledger in table-navigation order.
   Confirm state, year, involved mode, count, and “suppressed or zero” status are understandable.
5. Repeat the core flow at 200% browser zoom. Check focus visibility, horizontal table regions,
   target size, reflow, and that no control or content is obscured.

## Human screen-reader review — pending

NVDA + Firefox and VoiceOver + Safari have **not** been run against this component. The manual pass
must cover headings and landmarks, button name/role/value, map and plot navigation, table navigation,
dynamic loading and selection announcements, focus stability, language switching, and the equivalence
of every visualized value with the semantic tables.

Particular questions to resolve:

- Do NVDA and VoiceOver announce the map's 51-item roving-control model, its arrow-key instructions,
  and the state names/counts without implying that all 51 items are separate page-tab stops?
- Do SVG `role="button"` state groups and plot points expose consistent names and roles in both
  browser/assistive-technology combinations?
- Does the browser-verified focus restoration after map and scatter redraws remain predictable under
  both screen readers?
- Are polite status messages announced once, at the useful time, without interrupting table reading?

## Release disposition

**Blocked on required human review.** Automated, data-contract, targeted browser-keyboard, and
narrow-viewport evidence are green, but this record contains no NVDA or VoiceOver pass and no 200%
zoom result. Under the project's accessibility policy, it cannot serve as the completed manual
accessibility artifact for a release and must not be represented as verified conformance.
