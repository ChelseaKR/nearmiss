# Bug review and synthetic user research — 2026-06-17

A combined adversarial **code review** and **synthetic user-research panel** for
nearmiss, run as a 16-agent study: six adversarial bug-hunting lenses over the
whole codebase, and ten persona participants doing guided cognitive walkthroughs
of the site, the data, the docs, and the contributor path. Each bug finding was
independently re-verified before being trusted.

This report is itself written to the project's standard: it states what is real,
what was fixed, and what is still wrong, without softening. The headline is that
the review found **two genuine contributor-privacy leaks** (hard rule #4) that
the original implementation shipped, plus a cluster of **documentation-overclaims
the code did not honor** — exactly the failure mode this project exists to avoid.
Most code defects are now fixed; the remaining items are documentation honesty
and a roadmap of usability work, tracked below.

> Scope note: this study was run against a synthetic, single-city demo (Davis
> fixtures). Findings about placeholder street names and "synthetic demo" labeling
> reflect that; the methods generalize.

## Contents

- [How the study was run](#how-the-study-was-run)
- [Part 1 — Code bug review](#part-1--code-bug-review)
- [Part 2 — User research panel](#part-2--user-research-panel)
- [Part 3 — Cross-cutting themes](#part-3--cross-cutting-themes)
- [Part 4 — Prioritized recommendations and status](#part-4--prioritized-recommendations-and-status)
- [Appendix — persona roster](#appendix--persona-roster)

## How the study was run

- **Bug hunt (6 lenses):** statistical correctness; the privacy invariant;
  pipeline/geometry/determinism; the web frontend; CLI/IO/errors; and
  cross-cutting concerns. Each lens read the actual source and verified behavior
  by running code in the project's virtual environment. Every non-trivial finding
  was then re-checked by an independent verifier agent prompted to refute it.
- **User panel (10 personas):** a roadside reporter, a blind screen-reader user,
  a skeptical traffic engineer, a non-technical council member, an open-data
  researcher, a first-time contributor, a Spanish-speaking advocate, a journalist,
  a low-vision (200%-zoom) user, and an advocate adapting nearmiss to a new city.
  Each read the files a person with that goal would actually hit, narrated the
  experience, and returned severity-rated issues with verbatim quotes.

Limitations: the personas are synthetic and perform an expert/cognitive
walkthrough, not live assistive-technology testing. Screen-reader and zoom
findings are structural predictions to be confirmed by real NVDA/VoiceOver and
browser-zoom sessions (still pending — see the ACR).

## Part 1 — Code bug review

22 findings; all confirmed by a second verifier. Status reflects fixes applied in
the `fix: address adversarial review` change.

### Critical — contributor-privacy leaks (hard rule #4)

| # | Finding | Status |
| --- | --- | --- |
| P1 | **The dev server served the private raw store.** `nearmiss serve --dir .` (the documented default) exposed `data/raw/davis/reports.json` over HTTP — full-precision coordinates and reporter tokens — contradicting THREAT-MODEL T5 and HR4. Proven with a live request. | **Fixed.** The server now refuses any path under `data/raw/` or any dotfile with HTTP 403, verified (`/data/raw` → 403, `/data/published` + `/web` → 200). |
| P2 | **Published metadata leaked a near-raw coordinate.** `metadata.kde_peak` shipped a 5-decimal (~1 m) coordinate ~15 m from real reports and bypassed the privacy gate entirely. | **Fixed.** The KDE peak is published only as a segment id; metadata now passes its own `assert_metadata_clean` gate. |
| P3 | **No minimum-occupancy (k-anonymity).** Segments with `report_count == 1` published precise public geometry — "exactly one person reported an incident on this block." | **Fixed.** Segments with `0 < report_count < min_publish_n` (default 3) are withheld entirely from the GeoJSON, metadata, and brief; `assert_published_clean` enforces it. |

### High — honesty and correctness

| # | Finding | Status |
| --- | --- | --- |
| H1 | THREAT-MODEL documented privacy controls (coordinate fuzzing, jitter, timestamp coarsening, a CI occupancy gate) **that did not exist in code**. | **Fixed (docs).** All privacy docs reconciled to the real model: aggregation to public street segments + k-anonymity withholding + never publishing points/timestamps/tokens. The min-occupancy invariant is now real and enforced. |
| H2 | **Significance was uncorrected** `z > 1.96`, but the methodology and schema promised a false-discovery-rate adjustment. | **Fixed.** Significance is now Benjamini-Hochberg FDR-corrected. |
| H3 | Published field name and quality-flag vocabulary disagreed with the schema/data-card (`significant` vs `getis_ord_significant`; raw flags vs the documented set). | **Fixed.** Field renamed to `getis_ord_significant`; flags mapped to `low_sample` / `geocode_low_confidence` / `exposure_unknown`. |

### Medium

| # | Finding | Status |
| --- | --- | --- |
| M1 | `coverage()` counted zero/negative exposures as covered, overstating published `exposure_coverage`. | **Fixed** (counts only usable, positive exposures). |
| M2 | Dedupe ordered survivors by the raw ISO **string**, misordering across timezone offsets. | **Fixed** (orders by parsed epoch). |
| M3 | Web `fail()` wrote an error message into `innerHTML` — an HTML-injection sink on a malformed data response. | **Fixed** (`textContent`). |
| M4 | Sort comparator returned `NaN` for null-vs-null, making `exposure_unknown` rows sort nondeterministically. | **Fixed** (null-safe, stable, id-tiebroken). |
| M5 | A missing input file crashed with a raw traceback and exit 1 instead of a clean error. | **Fixed** (`NearmissError`, exit 2). |
| M6 | A non-numeric config threshold raised a bare `ValueError`, not `ConfigError`. | **Fixed.** |
| M7 | The forbidden-key denylist omitted `mode` and `severity`. | **Fixed** (added). |

### Low (all fixed)

`wilson_ci` now guards `successes > trials`; `assert_published_clean` flattens
any GeoJSON geometry nesting; `load_streets` rejects <2-vertex LineStrings; the
web table sets an initial `aria-sort` and uses a global underscore replace and a
null-geometry guard; the duplicate landmark label was disambiguated; and the
schema validator cache is keyed on the resolved path so the env override is
honored. A separate first-contributor finding — an **invalid `pre-commit` hook
id** (`forbidden-files`) that broke every commit — was also fixed (moved to a
`repo: local` fail hook).

## Part 2 — User research panel

Sentiment across the ten participants: 2 satisfied, 7 mixed, 1 frustrated, 0
delighted/blocked. The statistics and the honest framing earned real trust; the
gaps were **documentation that overpromised** and **the absence of a fast,
plain-language front door** for non-technical users.

### Maria — roadside reporter (mobile, < 1 minute) · *mixed*

> "I came here to report a truck buzzing me, and the front page is a statistics
> manifesto. Where's the button that says 'Report a hazard'?"

No prominent "Report a hazard" link from the README; reporting goes through a
public GitHub issue whose form warns (twice) that input is public — at odds with
the privacy promise; no "what happens after you submit" reassurance; the
"bilingual / mobile-first" reporting claims are not delivered.

### Darnell — blind screen-reader user · *satisfied*

> "A skip link that actually works and a heading list with no gaps — I'm already
> in a better mood than most sites put me in."

The skip link, heading structure, and the table-as-equivalent are genuinely good.
But **sorting is silent to a screen reader** (no `aria-live` announcement of the
new order), and the ACR reads as an as-built report when it is still aspirational.

### Priya — skeptical traffic engineer · *mixed*

> "I'll give them this: the methodology is the most honest piece of advocacy
> writing I've read in years … so my job got harder."

The honesty disarmed her — then she found the **methodology describes statistics
the code does not run**: it claims an exact (Garwood) Poisson interval (code uses
Byar), a conditional-permutation Gi\* reference distribution (code uses the
analytic normal approximation), an overdispersion check, and ranking by the lower
confidence bound (code ranks by the point estimate). Defensibility depends on the
doc matching the code.

### Sam — council member, 5 minutes, no stats · *mixed*

> "The title nails my exact question … then two lines later 'units of exposure'
> and I'm already lost on what a unit even is."

Placeholder IDs ("Street seg-06") instead of real names; no inline plain-language
definition of Gi\*/CI in the brief; **no bottom-line "what to do" sentence** he
could read aloud; the bias caveat, uncountered, can read as "you can't conclude
anything."

### Lin — open-data researcher · *mixed*

> "The README sold me a self-describing artifact with embedded version and
> provenance. Then I opened the file and the only keys are `features` and `type`."

The schema promises a top-level `metadata` member (version, content hash,
provenance) the GeoJSON does not carry; the file has **no version identifier**;
CITATION.cff is `type: software` with no dataset citation or DOI; cross-references
name `nearmiss.geojson` (actual: `davis.geojson`).

### Alex — first-time contributor · *mixed*

> "The 'read first' box at the top of the README is the most honest thing I've
> seen in an OSS repo … I trusted the project more."

The status note and CONTRIBUTING landed well. Blockers: the **broken pre-commit
hook id**; `make install` assumes `python` is ≥3.11; `make security` calls
`gitleaks`, which `pip install` does not provide.

### Rosa — Spanish-speaking advocate · *frustrated*

> "Line 345 told me, present tense, that the form 'is bilingual where the
> community is.' My community is Spanish-speaking. The only form in this whole
> repo is in English."

**Localization is claimed as delivered (present tense) in the README and
ACCESSIBILITY, but does not exist**: English-only form, no language field in the
schema, no localized outputs. The same feature is "done" in two docs and
"planned" in a third.

### Jordan — journalist · *satisfied*

> "The README is basically pre-arguing with my headline … Caught me."

The guardrails work. But the **loud surfaces** (page `<title>`, `<h1>`, brief
title — "where the danger actually is") undercut the discipline of the fine print,
nothing on those surfaces says the Davis data is a **synthetic demo**, and the
brief gives no ready-to-print honest sentence.

### Kenji — low-vision, 200% zoom · *mixed*

> "First thing I see is a real 'Skip to the data' link … this project actually
> knows I'm here."

But `table { min-width: 44rem }` (704px) **breaks reflow at 200% zoom** (WCAG
1.4.10); the first column is not horizontally sticky; and the ACR's reflow/target
rows are "Supports (target)," not verified.

### Fatima — adapting nearmiss to a new city · *mixed*

> "I copied the very first command out of the README and it errored — there is no
> `--city` flag, it wants `--config`. Not a great first ten seconds."

The **README Usage block shows commands the CLI does not accept** (`--city`,
`nearmiss intake path/to/reports.json`); an exposure/segment id mismatch yields
`exposure_coverage = 0%` silently; there is no "adapt to your city" guide and no
geocoder adapter, so address-only reports are hard-rejected.

## Part 3 — Cross-cutting themes

1. **Documentation overclaim is the dominant risk** — not bugs. Five personas and
   three bug lenses independently hit docs that promise more than the code does:
   privacy controls (fixed), FDR (fixed), methodology specifics (Garwood,
   permutation, overdispersion, lower-bound ranking), localization, embedded
   dataset metadata, and the CLI surface. For a project whose entire value is
   honesty, **doc-vs-code drift is the highest-severity class of defect.**
2. **The statistics and the honest framing are the project's strength.** The
   traffic engineer and the journalist — the two hardest audiences — were won over
   by the methodology and the report-volume-vs-danger discipline.
3. **There is no fast, plain-language front door.** The roadside reporter, the
   council member, and the new-city adopter all hit a wall of statistics prose
   with no "Report a hazard," no bottom-line sentence, and no quickstart that
   matches reality.
4. **Accessibility foundations are strong but unverified at the edges.** Skip
   link, landmarks, and the authoritative table are real; live-region sort
   announcements, 200%-zoom reflow, and the manual screen-reader audit are not yet
   done — and the ACR should keep saying so.

## Part 4 — Prioritized recommendations and status

> **Update — remediation round (2026-06-17): every finding below is now
> addressed.** All 22 code findings and all medium-priority and roadmap items
> from the panel were implemented and verified (52 tests pass; ruff + mypy
> `--strict` clean; `make demo`/`reproduce` green). Specifically, since the first
> pass: address-only intake + an offline geocoder (Fatima); a `language` field and
> a bilingual English/Spanish brief + report form (Rosa); a self-describing
> embedded `metadata` member + a hashed `requirements.lock` + `getis_ord_significant`
> field reconciliation (Lin, Alex); a plain-language glossary, bottom-line sentence,
> exposure unit, and bias counterweight in the brief, plus real Davis street names
> (Sam, Jordan); a sticky table column + `aria-live` sort + an automated axe-core
> CI run (Kenji, Darnell); a loud error on exposure↔segment id mismatch and an
> "adapt to your city" guide (Fatima); a "what happens next" + privacy note on the
> report form (Maria); and Makefile Python-version/gitleaks guards (Alex). The only
> items intentionally left as honest, documented roadmap are a **networked**
> geocoder adapter (the offline gazetteer ships) and the **manual NVDA/VoiceOver**
> accessibility audit (automated axe + structural gates ship).

### Done in this pass

- All three privacy leaks (P1–P3) and all 22 code findings fixed; FDR, k-anonymity,
  coverage, dedupe, field names, robustness, and the pre-commit hook.
- All privacy docs reconciled to the real aggregation + k-anonymity model.

### High priority (honesty — fix in docs/code next)

- Reconcile **METHODOLOGY** to the implemented statistics (Byar interval; analytic
  Gi\* z + Benjamini-Hochberg FDR; no overdispersion check or lower-bound ranking
  yet — mark those planned).
- Mark **localization** as planned, not delivered, in the README and ACCESSIBILITY;
  remove the present-tense bilingual claims.
- Fix the **README Usage** block to the real `--config` CLI; add a prominent
  **"Report a hazard"** pointer and a one-line **synthetic-demo** label on the web
  page and the brief.
- Embed a top-level **`metadata`** member (schema_version, content hash, license,
  source) in the published GeoJSON so it is self-describing, as the schema promises;
  give CITATION.cff a dataset citation.

### Medium priority (usability)

- Brief: inline plain-language definitions of Gi\*/CI, a **bottom-line recommendation
  sentence**, and the exposure unit on the page.
- Web: an `aria-live` announcement on sort; reduce the table `min-width` and make the
  first column sticky for 200%-zoom reflow.
- Real **street/intersection names** in city data (and a note that demo IDs are
  placeholders).
- A clear error when exposure ids do not join to street segments (instead of a silent
  0% coverage).

### Roadmap (features)

- A geocoder adapter for address-only imports; an "adapt this to your city" guide;
  bilingual intake; the manual NVDA/VoiceOver + axe accessibility audit.

## Appendix — persona roster

Maria (roadside reporter, mobile) · Darnell (blind, NVDA/VoiceOver) · Priya
(skeptical traffic engineer) · Sam (council member, non-technical) · Lin
(open-data researcher) · Alex (first-time contributor) · Rosa (Spanish-speaking
advocate) · Jordan (journalist) · Kenji (low-vision, 200% zoom) · Fatima
(advocate adapting nearmiss to a new city).
