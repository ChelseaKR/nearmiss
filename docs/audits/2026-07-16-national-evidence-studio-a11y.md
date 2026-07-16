# National evidence studio accessibility review — 2026-07-16

**Kind:** pre-release accessibility component review
**Surface:** `web/us-coverage.html`, `web/us-coverage.js`, `web/us-coverage.css`,
`web/us-coverage-studio.css`, the EN/ES catalogs, and `web/us_coverage_check.mjs`
**Release / commit:** baseline `faad0a1`; remediation is the PR #110 head containing this record
**Target:** WCAG 2.2 Level AA and Revised Section 508 functional performance criteria
**Summary verdict:** **Incomplete — not a conformance result.** The structural and axe gates pass.
A rendered-browser simulation and independent review found six interaction/semantics defects in `faad0a1`; they were
remediated and the focused regression, 200%-equivalent layout proxy, and 400%-equivalent reflow
stress proxy pass. The required human NVDA and VoiceOver reviews, an uninterrupted end-to-end
keyboard pass, and an actual browser 200% zoom check have not been performed.

This file is a pre-release checklist and evidence placeholder, not proof that a manual accessibility
audit occurred. A pending row must not be cited as a pass. Replace each pending row with the exact
environment, command or assistive-technology version, date, result, and findings only after the check
is actually performed.

## Evidence status

| Review layer | Environment / method | Status | Evidence |
| --- | --- | --- | --- |
| Source and DOM-contract inspection | Direct review of baseline `faad0a1` and the remediated PR head | Complete as implementation inspection only | Mechanisms and remediations listed below; no conformance verdict |
| Structural accessibility gate | `make verify PYTHON=.venv/bin/python` → `make accessibility` | **Pass** | `tools/a11y_check.py` passed `index.html`, `submit.html`, `embed.html`, and `us-coverage.html` |
| Automated axe scan | `make verify PYTHON=.venv/bin/python` → `npm run axe`; rendered studio contract also runs axe | **Pass** | No axe violations in the static national page or its rendered canonical-route DOM |
| Targeted desktop interaction pass | In-app Chromium surface (version not exposed), 1280×720, 2026-07-16 | **Pass after remediation for the recorded flows** | Map Space/Home/End, matrix arrows/Home/End, scatter Space/redraw, comparison focus, brief add/remove focus, deep links, profile loading, and EN/ES state verified; native view/action buttons were pointer-activated where the harness did not synthesize their native keyboard click |
| Mobile / narrow-viewport pass | In-app Chromium surface (version not exposed), 390×844, 2026-07-16 | **Pass at the recorded viewport** | Single-column reflow, two-column view switcher, one-column filters, 306-row ledger, 24px control minimum, map keyboard selection, and no document-level horizontal overflow verified |
| 200%-equivalent layout proxy | 640×360 CSS viewport representing a 1280×720 window at 200%, EN, all five views, selected five-year profile, four brief cards | **Pass as an automated proxy only** | No document-level horizontal overflow; matrix/profile tables own their overflow; no tested button/select/summary below 24×24 CSS px |
| 400%-equivalent reflow stress proxy | 320×640 CSS viewport, ES, all five views, selected five-year profile, four brief cards | **Pass as an automated proxy only** | No document-level horizontal overflow, one-column studio/filter layout, no tested button/select/summary below 24×24 CSS px |
| Actual 200% browser zoom | Browser zoom and environment to be recorded | **Not performed** | CSS-viewport proxies are not being represented as an actual browser-zoom result |
| NVDA + Firefox | Windows, NVDA version, and Firefox version to be recorded | **Not performed** | No human screen-reader evidence |
| VoiceOver + Safari | macOS, VoiceOver version, and Safari version to be recorded | **Not performed** | No human screen-reader evidence |

## Implemented mechanisms observed in source

These observations combine source inspection with the targeted browser evidence above; they are not
screen-reader findings:

- The national SVG map uses one roving tab stop across 51 named `role="button"` state/DC groups.
  Arrow keys and Home/End move within the group; Enter and Space select. Each name contains the state,
  involved mode, and either its published count or its non-published status.
- Visible bilingual instructions explain each dense view's roving-item model; the matrix instruction
  separately identifies its scroll region and mode-filter stops. Every generated roving item
  references its instruction with `aria-describedby`.
- Map selection redraws the linked views and restores focus to the selected state. ArrowRight from
  Alabama moved focus to Alaska, and Enter selected Alaska while retaining `map:AK` focus and loading
  its exact 2020–2024 profile.
- Matrix cells, rank rows, and published mode-comparison points use the same single-tab-stop roving
  model. When the selected state is represented in a dense view, that view exposes one linked
  `aria-current="true"` item. Scatter focus remained on the activated point after the linked plot
  redrew.
- Native year, state, mode, publication-status, secondary-mode, scale, and comparison-state controls
  provide non-SVG ways to change the analysis.
- The state-by-mode matrix, mode-comparison table, state-comparison table, five-year state profile,
  and complete evidence ledger use semantic tables with captions and scoped headers. Decorative
  comparison tracks are hidden from accessibility APIs. Rank and inspector actions use native
  buttons. Visual-view switching uses buttons with `aria-pressed` and `aria-controls`; inactive
  panels are hidden.
- The map and matrix use hatching plus publication-status text for non-published cells. The complete
  ledger labels these values “suppressed or zero” and does not expose them as numeric zero.
- Loading, profile, and brief updates use atomic polite `role="status"` regions. Their timing and
  wording under assistive technology have not been manually verified.

## Recorded targeted browser findings

- The whole-country default rendered all 51 jurisdictions, 306 state × involved-mode ledger rows,
  51 map groups, 51 matrix rows, and 306 matrix cells from the selected annual artifact.
- Map, matrix, rank, and scatter each exposed one roving tab stop. Arrow navigation moved focus within
  the active visualization without adding every datum to the page tab order.
- Matrix selection updated state, mode, inspector, profile, ledger, and URL. Rank, scatter, and state
  comparison rendered the matching published and non-published values from the same artifact.
- Scatter-point Enter and Space actions preserved focus after redraw. Switching years loaded the exact
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

## Remediation loop findings

The simulation first ran against baseline `faad0a1`, then the same focused checks were repeated after
each repair:

1. **Detached focus after “Compare this state” — fixed.** The action destroyed its focused inspector
   button during rerender. It now moves focus to the first comparison-state selector, which remains
   connected and matches the selected state.
2. **Detached focus after removing a brief card — fixed.** Removal now focuses the next remove action,
   the previous action when the final card in a list is removed, or “Clear brief” when the list becomes
   empty.
3. **No exposed keyboard model for dense controls — fixed.** Visible EN/ES instructions now describe
   each roving item set's Tab entry, Arrow/Home/End movement, and Enter/Space selection; the matrix
   copy separately names its scroll region and mode filters. Instructions are programmatically
   associated with every roving item.
4. **Selection was visual-only in map, matrix, and scatter — fixed.** All four dense views now expose
   one linked `aria-current="true"` selection whenever that state has an item in the view.
5. **State comparison depended on visual columns — fixed during the same loop.** It is now a captioned
   table with state column headers, involved-mode row headers, decorative tracks hidden from the
   accessibility tree, and a named focusable wrapper when horizontal scrolling is required.
6. **Status and view relationships were underspecified — fixed during the same loop.** Status regions
   are atomic, view controls reference their panels, initial duplicate rendering was removed, and
   forced-colors focus uses system `Highlight` for the SVG/plot focus stroke.

`web/us_coverage_check.mjs` now locks these repairs with deterministic real-artifact regression tests.

## Remaining manual keyboard and zoom script

Record results for the remaining steps with no pointer:

1. Run one uninterrupted skip-link and full-tab-order pass, including focus visibility and every
   inactive panel's exclusion from the tab order.
2. Repeat map and scatter activation with Space, matrix Home/End and vertical arrows, comparison entry,
   and brief removal as one uninterrupted no-pointer human session.
3. Confirm focus remains visible after every destructive action and view redraw.
4. Read the matrix, comparison table, five-year profile, and complete ledger in table-navigation order.
   Confirm state, year, involved mode, count, and “suppressed or zero” status are understandable.
5. Repeat the core flow at actual 200% browser zoom. Check focus visibility, horizontal table regions,
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

**Blocked on required human review.** Automated, data-contract, targeted browser-interaction, and
layout-proxy evidence are green, but this record contains no NVDA or VoiceOver pass, no uninterrupted
human no-pointer pass, and no actual 200% browser-zoom result. Under the project's accessibility
policy, it cannot serve as the completed manual accessibility artifact for a production release and
must not be represented as verified conformance.
