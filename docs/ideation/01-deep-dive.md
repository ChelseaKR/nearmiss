# Deep dive — current state as read on 2026-07-01

This is an assessment from reading the repository (code, docs, CI, git history), not
from running it. Claims below cite the file they come from; where something could not
be verified by reading alone, that is said.

## Architecture summary

nearmiss is a pure-typed-Python (3.11+, single runtime dependency `jsonschema`,
per `pyproject.toml` and ADR-0003) pipeline that turns crowdsourced road-hazard
reports into an exposure-normalized, uncertainty-quantified, privacy-aggregated open
dataset. The stages are small modules with one orchestrator:

- **Intake & validation** — `src/nearmiss/intake.py` validates against
  `schema/report.schema.json` (via `src/nearmiss/validation.py`) into a gitignored
  private raw store; `src/nearmiss/moderation.py` adds a pending→approved/rejected
  queue for public submissions (JSON files under `data/pending/`), with light
  PII-leak regex flags and near-duplicate detection.
- **Pipeline** — `src/nearmiss/pipeline/{dedupe,geocode,snap,classify,quality}.py`:
  deterministic O(n²) dedupe, offline gazetteer geocoding (with an opt-in Nominatim
  adapter in `src/nearmiss/geocoder.py`), nearest-segment snapping via
  `geometry.point_to_polyline_m` (equirectangular local projection), closed-vocabulary
  classification, and quality flags (`unsnapped`, `low_accuracy`, `far_snap`).
- **Statistics** — `src/nearmiss/stats/`: Byar Poisson CIs and Wilson intervals
  (`rates.py`), report-share-vs-exposure-share bias findings (`bias.py`), Gaussian KDE
  labeled as report intensity (`kde.py`), Getis-Ord Gi\* on the exposure-normalized
  rate with Benjamini-Hochberg FDR (`getis_ord.py`), city-wide-only temporal and
  weather-association breakdowns (`temporal.py`), all orchestrated by
  `stats/__init__.py:analyze()` via `engine.py:build_analysis()`.
- **Publication** — `src/nearmiss/publish.py` builds the open GeoJSON plus a hashed
  metadata sidecar, enforcing hard rule #4 with a `_FORBIDDEN_KEYS` denylist,
  `assert_published_clean` / `assert_metadata_clean` invariants, and the
  `min_publish_n` k-anonymity floor. `brief.py` renders the bilingual advocacy brief
  through gettext catalogs (`src/nearmiss/i18n.py`, `src/nearmiss/locales/`).
- **Serving** — `src/nearmiss/server.py`, a read-only stdlib server that blocks
  `data/raw/` and dotfiles, redacts blocked paths from its structured JSON log
  (`obs.py`), and exposes `/livez` / `/readyz`. The public site is static
  (GitHub Pages, `CNAME` → nearmiss.report; `web/app.js` renders the two-map
  counts-vs-rate contrast plus the authoritative sortable table).
- **Config-over-code** — `src/nearmiss/config.py` + `config/*.toml` (two synthetic
  demo cities committed; `davis.toml` / `sacramento.toml` point at gitignored real
  inputs assembled by `make real` via `tools/fetch_bikemaps.py`,
  `tools/fetch_osm_streets.py`, `tools/build_exposure.py`).
- **Gates** — `Makefile` `verify` = ruff + mypy strict + pytest (90% branch-coverage
  floor) + structural a11y + pip-audit/gitleaks + i18n catalog parity;
  `.github/workflows/ci.yml` mirrors it with SHA-pinned actions, CodeQL, a DCO check,
  and a `make reproduce` byte-for-byte drift gate on `data/published/`;
  `mutation.yml` runs advisory mutmut scoped to `stats/getis_ord.py` and
  `stats/rates.py`.

## What is genuinely strong

- **The hard rules are code, not prose.** k-anonymity withholding lives in
  `analyze()` (`publishable=not (0 < count < config.min_publish_n)`) *and* is
  re-asserted at the publish boundary (`assert_published_clean`), so a bug upstream
  still cannot leak. The KDE peak is only ever reported as a publishable segment id
  (`stats/__init__.py`). The temporal module refuses per-segment×per-hour cells by
  design. This is defense-in-depth applied to honesty.
- **Self-incriminating documentation.** `docs/METHODOLOGY.md` names its own gaps
  (overdispersion "PLANNED, not yet implemented"; permutation Gi\* "not what is
  computed today"), and `docs/LIMITATIONS.md` is literally a list of attacks with an
  invitation to use them. Very few analytics projects write this down.
- **Reproducibility as a merge gate.** CI re-runs the full pipeline and fails on any
  diff under `data/published/` — the strongest available proof of the "open and
  reproducible end to end" claim short of third-party replication.
- **Test design.** Planted-hotspot fixtures with a busy decoy (`tests/fixtures/`,
  documented in `tests/README.md`) test the *thesis* (volume ≠ danger), not just the
  code; 26 test files cover pipeline, stats numerics, privacy invariants
  (`tests/test_publish_privacy.py`), the server's blocklist, and the real-data
  fetchers.
- **Real-data on-ramp exists and is honest.** `docs/REAL-DATA.md` plus the BikeMaps/
  OSM/exposure fetchers give a genuine path from synthetic demo to real city, with the
  weakest input (exposure) allowed to be honestly absent rather than faked.

## Structural debt and gaps actually observed

1. **The 2026-06-30 research pass is orphaned on a branch.** `git log` shows
   `research-panel-and-roadmap` (commit `6dfabb0`: `docs/RESEARCH-ROADMAP.md`,
   `docs/USER-RESEARCH.md`, `stats/maup.py`, `pearson_dispersion`/`quasi_poisson_ci`
   in `rates.py`, tests) forked from `8daa24c` and never merged, while `main` advanced
   8 commits (i18n gettext migration, coverage uplift, observability, mutation
   testing, msgpack pin, pre-commit fixes) — several touching the same files
   (`i18n.py`, `config.py`, `stats/__init__.py`, `tests/test_rates.py`). The
   `[tool.mutmut]` comment in `pyproject.toml` even records the confusion: "The task
   brief named a `stats/maup.py`; no such module exists in this repo." Meanwhile the
   branch's own RESEARCH-ROADMAP marks RR-02/RR-05 "shipped this pass." The repo's
   honesty ledger and its main branch currently disagree.
2. **Several documented methods don't exist in code.** Directly observed
   doc-over-code claims: METHODOLOGY §8.2 says Gi\* neighbors are "defined on the
   street network … not naive straight-line distance," but `getis_ord.py` uses a
   haversine centroid distance band; §1 says rates are "never silently pooling
   incompatible hazards," but `analyze()` computes one all-hazards rate per segment;
   §2 promises low-confidence reports are "excluded from the primary rate and
   analyzed separately," but `aggregate.py` counts flagged records identically; §9.2
   claims committed interval-coverage simulations, but no such test exists in
   `tests/` (grep across `test_rates.py`, `test_fdr.py`, `test_stats_numerics.py`);
   README § Install says `requirements.lock` "is not committed yet" while the file is
   committed at the repo root; README's quality-attributes section claims "structured
   logs and metrics on intake and each pipeline stage," but `obs.py` is wired only
   into the server; `CHANGELOG.md` references a "mirroring JSON Schema validated in
   CI" for the published dataset that does not exist (`schema/` holds only
   `report.schema.json` and the prose `dataset.schema.md`).
3. **The exposure data model is thinner than the methodology.** `models.Exposure` is
   a single scalar + source string + date. The trust tiers (observed/modeled/proxy),
   multi-source corroboration, exposure floor, and temporal-alignment flag that
   METHODOLOGY §3 specifies have no representation in code or in the published
   properties.
4. **No analysis window anywhere.** METHODOLOGY §1 requires every published number to
   carry its window `[t0, t1]`; `config.py` has no window fields and
   `publish.py` records none.
5. **Quadratic cores.** `dedupe` (reports²), `snap` (reports × segments × vertices),
   `getis_ord_star` (segments² haversine calls), KDE (grid² × points). Fine at the
   documented city scale (`docs/PERFORMANCE.md` is honest about this), but a hard
   ceiling for regional ambitions, and `getis_ord_star` also computes variance via
   the cancellation-prone `sum(x²)/n − mean²` form.
6. **Config is permissive.** `load_config` ignores unknown keys and unknown
   `[thresholds]` entries — a typo like `fdr_aplha = 0.01` silently runs at the 0.05
   default. For a project whose published significance depends on these values, that
   is a correctness hazard, not a style issue.
7. **Two parallel i18n systems.** The Python surface uses gettext catalogs gated by
   `make i18n`; the web UI carries a hand-maintained `I18N` object inside
   `web/app.js` (and `submit.js`) that no parity gate covers.
8. **Release engineering is aspirational.** No git tags exist; `publish.py` hardcodes
   `dataset_version: "0.1.0"` and `schema_version: "1.0.0"` as string literals;
   README claims "signed releases" that have never happened. (`RR-11` covers tagging
   + DOI; the automation and signing gap is broader.)
9. **Orphaned work beyond the research branch.** `origin/claude/real-data-map-integration-mud09x`
   contains a complete SimRa adapter (`tools/fetch_simra.py` + tests) that never
   landed.

## Strategic position inside the portfolio

nearmiss is the portfolio's flagship demonstration of **statistical candor as a
product feature**: it operationalizes the RESPONSIBLE-TECH-FRAMEWORK and
QUALITY-AND-METRICS standards (vendored at `docs/standards/`) more concretely than a
CRUD app ever could — five falsifiable rules, each with an enforcement point and a
tripwire. Its nearest sibling is `davis-bike-hazard-map` (map-as-product vs.
data-as-product). Its distinctive portfolio assets are (a) the planted-truth fixture
methodology, (b) the publish-boundary privacy invariants, and (c) the reproducibility
merge gate — all three are reusable patterns other repos could import, and two
expansion ideas (EXP-08, EXP-09 in `03-expansions.md`) propose exactly that
extraction. Its biggest strategic exposure is the gap between the documented
methodology and the implemented one (item 2 above): for a project whose brand is "we
never overclaim," doc-over-code drift is not cosmetic debt, it is brand risk. The
fixes file leads with that.
