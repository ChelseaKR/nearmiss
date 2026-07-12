# Large-scale fixes (FIX-01 … FIX-14) — drafted 2026-07-01

Deep structural fixes only. Each is net-new relative to README Phases 1–4, the
2026-06-20 panel (`R#`/`E#`), and the 2026-06-30 research roadmap (`RR-#`/`RE-#`);
where a fix builds on an existing ID it says so and goes beyond it. Effort tiers:
S ≈ afternoon · M ≈ 1–3 days · L ≈ 1–2 weeks · XL ≈ multi-week.

> **Dependency note, not a fix:** msgpack 1.2.0 carries GHSA-6v7p-g79w-8964 (fixed in
> 1.2.1). `main` already pins `msgpack>=1.2.1` (`pyproject.toml`, commit `072a90d`),
> but the unmerged `research-panel-and-roadmap` branch predates that pin — FIX-01's
> merge must preserve it. A one-line check, not a large-scale item.

---

### FIX-01 — Land the orphaned research branch onto diverged main
- **Status:** ✅ Done — the research branch landed on main (RESEARCH-ROADMAP/USER-RESEARCH docs, RR-02 overdispersion, RR-05 MAUP rank-stability are all on `main`).
- **Pitch:** Reconcile `research-panel-and-roadmap` (commit `6dfabb0`) — RR-02
  overdispersion, RR-05 MAUP module, RESEARCH-ROADMAP.md, USER-RESEARCH.md — with the
  8 commits `main` has gained since, and finish the wiring.
- **Why it matters:** The repo's own roadmap says RR-02/RR-05 "shipped"; `main` says
  otherwise (no `stats/maup.py`, no `pearson_dispersion`). Every consumer of `main` —
  including the published datasets and the METHODOLOGY §4 "not yet implemented"
  flag — is out of sync with the planning record. For a statistical-candor project
  this is the single most corrosive open item.
- **Shape:** Rebase/merge `6dfabb0` across the i18n-gettext migration (`i18n.py`,
  `brief.py` strings now flow through catalogs — the branch's new user-facing strings
  need extraction into `locales/messages.pot` or `make i18n` fails), the coverage
  uplift (`tests/test_rates.py` conflicts), and `config.py` churn (the branch adds
  `overdispersion_adjust`). Then: wire `pearson_dispersion` output and the
  `RankStability` artifact into `publish.py` metadata (`methods.dispersion`,
  `maup_rank_stability`) and `brief.py`; update METHODOLOGY §4/§8 and LIMITATIONS §5
  from "planned" to "implemented, config-gated"; extend the mutmut scope note in
  `pyproject.toml` that currently denies `maup.py` exists.
- **Effort:** M. **Risks:** merge conflicts in `stats/__init__.py` and tests;
  the branch predates the msgpack pin and the SHA-pinned-actions/coverage gates, so
  `make verify` must be re-run post-merge, not trusted from the branch.
- **Excellent looks like:** `main` passes `make verify`; published metadata for both
  demo cities carries a dispersion φ and a rank-stability block; METHODOLOGY contains
  zero "planned" flags that the code has already satisfied and zero "implemented"
  claims it hasn't.

### FIX-02 — Network-topology spatial weights for Gi\*
- **Status:** ✅ Done (PR #50, 2026-07-12) — `network.py` SegmentGraph street-network Gi\* weights; per-city `dataset_version` 0.1.0 -> 0.1.1.
- **Pitch:** Replace the straight-line centroid distance band in
  `stats/getis_ord.py` with street-network adjacency/network-distance weights built
  from the `streets.geojson` the pipeline already loads.
- **Why it matters:** METHODOLOGY §8.2 *already claims* neighbors are "defined on the
  street network … not naive straight-line distance." The code does the opposite:
  `getis_ord_star()` calls `haversine_m` between centroids. Beyond doc-parity, the
  statistical point is real — two segments across a river or freeway are not
  neighbors, and a Euclidean band can manufacture or dilute clusters near barriers.
  Affects every published `getis_ord_significant` flag.
- **Shape:** Build a segment graph in a new `src/nearmiss/network.py` (endpoints
  within a snap tolerance share a node — `tools/fetch_osm_streets.py` already splits
  ways at intersections, so endpoints are principled); weights = k-hop adjacency or
  network distance ≤ `gi_band_m` via Dijkstra over segment lengths (pure Python,
  keeps ADR-0003). Feed `getis_ord_star` a precomputed neighbor map instead of
  recomputing pairwise haversine. Add a barrier fixture (two parallel streets, no
  connecting edge, planted hotspot on one side) asserting the Euclidean band and the
  network band disagree and the network answer is published.
- **Effort:** L. **Risks:** disconnected components in sparse networks (define
  behavior: island segments get self-only weight and are labeled untested); changes
  published z-scores, so `data/published/` regenerates — must ship with a CHANGELOG
  schema-note and a dataset version bump.
- **Excellent looks like:** doc and code agree; the barrier fixture passes; the
  weights definition (`type`, `band`, graph node tolerance) is recorded in
  `metadata.methods`; per `docs/MUTATION-TESTING.md` discipline, mutmut scope extends
  to `network.py`.

### FIX-03 — Claims-parity audit: make every documented method claim CI-checkable
- **Status:** ✅ Done (PR #35) — docs/CLAIMS.md manifest + `tools/check_claims.py` CI drift gate.
- **Pitch:** Sweep the doc-over-code drift found on 2026-07-01 (see
  `01-deep-dive.md` item 2), fix each side to match, and add a lightweight
  claims-manifest gate so drift cannot silently recur.
- **Why it matters:** The project's brand is "we never overclaim." Today the docs
  overclaim in at least six places (network weights, per-hazard rates, quality-tier
  sensitivity, coverage simulations, lockfile status, pipeline observability, plus
  CHANGELOG's phantom dataset JSON Schema). Each is individually small; collectively
  they are exactly the attack a hostile reviewer would run: "your methodology PDF
  describes a different program."
- **Shape:** (1) Correct the false claims now — either implement (FIX-02/-06/-07
  cover the big three) or reword to "planned," which METHODOLOGY already does well
  elsewhere. (2) Add `docs/CLAIMS.md`: a table of load-bearing claims, each with a
  claim ID, the doc anchor, and the test or file that witnesses it; add
  `tools/check_claims.py` to `make verify` that fails when a claim ID's witness test
  disappears or a doc drops/edits a tagged claim without touching the manifest.
  Pattern is the same as the existing `make i18n` POT-drift gate.
- **Effort:** M (the sweep) + S (the gate). **Risks:** the manifest itself can rot —
  keep it to the ~20 claims that would embarrass the project if false, not every
  sentence.
- **Excellent looks like:** a skeptic can pick any hard claim in README/METHODOLOGY
  and be pointed, mechanically, to the code and test that make it true; CI fails on
  new drift.

### FIX-04 — Exposure trust tiers, corroboration, and temporal alignment in the data model
- **Status:** ✅ Done (PR #53, 2026-07-12) — exposure trust tiers, corroboration/disagreement, `exposure_floor`, `exposure_stale` flag; dataset schema 1.1.0.
- **Pitch:** Grow `models.Exposure` from `(estimate, source, date)` to the model
  METHODOLOGY §3 actually specifies: trust tier (observed/modeled/proxy), optional
  multiple sources per segment with a corroboration/disagreement finding, an exposure
  floor, and a report-window vs. exposure-window alignment flag.
- **Why it matters:** Exposure is the decisive input (LIMITATIONS §3 calls it "the
  shakiest"), and today a Strava-style proxy and a permanent count station are
  indistinguishable in the published `exposure_source` free-text string. Consumers
  cannot filter by trust, and a large count-vs-proxy disagreement — which §3.1 calls
  "itself a finding" — is currently invisible. Goes beyond `RR-03` (interval
  propagation) and `RE-07` (more adapters): this is the *schema* both of those need.
- **Shape:** Extend `models.Exposure` and `loaders.load_exposure` (accept
  `tier`, optional `sources: []`); `exposure.py` gains `corroboration()` returning
  per-segment agreement ratios; publish `exposure_tier` (and
  `exposure_disagreement` when multi-source) in `publish._feature`; add
  `exposure_stale` to the published `quality_flags` vocabulary when
  |exposure_date − analysis window| exceeds a config threshold; document in
  `schema/dataset.schema.md` §fields as a MINOR additive change; surface tier in
  `web/app.js` table and `brief.py`.
- **Effort:** L. **Risks:** schema addition ripples to `tools/build_exposure.py`,
  fixtures, and the web table; keep old single-source files loading (tier defaults
  to `unknown`, honestly).
- **Excellent looks like:** the Riverside fixture gains a two-source segment whose
  disagreement is published; no published rate exists without a tier; a QGIS user can
  filter to observed-tier segments only.

### FIX-05 — First-class analysis window ✅ DONE
- **Status:** DONE — `Config.window_start/window_end` parse an optional `[window]`
  table (ISO dates, reversed/unparseable ranges rejected at load); `pipeline.run`
  filters `occurred_at` to the window and reports an `out_of_window` removal count;
  `publish.py` stamps `metadata.window` into both the embedded and sidecar metadata
  (keys always present, null when unset); the brief header states the window or warns
  when none is configured (localized EN/ES); the demo configs carry a window spanning
  the synthetic fixtures so `make reproduce` stays byte-stable.
- **Pitch:** Add `[window] start/end` to `config.py`, filter records to it in
  `engine.build_analysis`, and stamp the window into every published artifact and
  brief.
- **Why it matters:** METHODOLOGY §1: "A rate with no window … attached is not a
  publishable number." No window exists anywhere in the code, so today's published
  rates are silently all-time — mixing 2015-era BikeMaps reports with 2026 exposure
  once real data lands, which §3.2 itself calls "comparing two different cities."
- **Shape:** `Config.window_start/window_end` (ISO dates, optional but warned when
  absent for real configs); filter in the pipeline on `occurred_at` with an explicit
  `out_of_window` removal count in `pipeline.run`'s summary; write
  `metadata.window`; brief states the window in its header; FIX-04's staleness flag
  reads against this window.
- **Effort:** S–M. **Risks:** none structural; demo fixtures need windows spanning
  their synthetic timestamps to keep `make reproduce` byte-identical or a deliberate
  regeneration.
- **Excellent looks like:** every published number is traceable to a stated window;
  running the same config with two windows produces two cleanly-labeled datasets.

### FIX-06 — Per-hazard-type rate layers (stop the silent union)
- **Status:** ✅ Done (PR #37, 2026-07-12) — per-hazard-type `rates_by_type` layers with small-n suppression; the pooled top-level rate is labeled a union.
- **Pitch:** Compute and publish type-specific rates + CIs where n permits, and label
  the current pooled rate explicitly as "all hazard types (union)".
- **Why it matters:** METHODOLOGY §1 promises "a rate is always computed within a
  type or for an explicitly defined union … never silently pooling incompatible
  hazards." `analyze()` pools everything; a dooring epidemic and a pothole cluster
  currently produce one number. Advocacy asks differ radically by type (protected
  lane vs. resurfacing) — the pooled rate under-serves the exact council use case.
- **Shape:** `aggregate.py` already carries `hazard_breakdown`; add per-type counts →
  `rate_with_ci` per type when the type's count ≥ `small_n`, suppressed below (the
  existing k-anonymity/small-n discipline extends naturally); publish under a new
  `rates_by_type` property (additive schema change); Gi\* stays on the union rate by
  default with the union labeled in `metadata.methods`; brief gains a "dominant
  hazard, with rate" line per ranked segment.
- **Effort:** M. **Risks:** small-n suppression will blank most types in sparse
  cities — that is the honest outcome, and the `low_sample` vocabulary already
  expresses it.
- **Excellent looks like:** the fixture city publishes a dooring-specific rate on the
  planted dooring segment; nothing publishes a per-type rate below `small_n`; the
  union label appears in every artifact that shows the pooled rate.

### FIX-07 — Quality-tier sensitivity split for the primary rate
- **Status:** ✅ Done (PR #38, 2026-07-12) — primary rate excludes low-confidence records; `rate_sensitivity_delta` + `excluded_low_confidence_fraction` published.
- **Pitch:** Exclude `low_accuracy`/`far_snap` records from the primary published
  rate, publish the excluded fraction, and report a sensitivity delta
  (rate-with vs. rate-without flagged records).
- **Why it matters:** METHODOLOGY §2 step 4 documents exactly this ("excluded from
  the primary rate and analyzed separately as a sensitivity check. The fraction of
  reports excluded is published") and the code does none of it — flagged records
  count identically in `aggregate.py`. A hostile reviewer can currently move a
  hotspot by feeding low-accuracy points.
- **Shape:** `aggregate()` gains a `primary=True/False` split keyed on
  `_LOW_CONFIDENCE_RAW` (already defined in `stats/__init__.py`); `analyze()`
  computes both; publish `excluded_low_confidence_fraction` in
  `metadata.summary` and a per-segment `rate_sensitivity_delta` when the two rates'
  CIs disagree materially; fixture with planted low-accuracy noise asserting the
  primary rate is stable.
- **Effort:** M. **Risks:** double computation is cheap; the subtle part is honest
  wording in the brief — "the ranking does/does not depend on low-confidence
  reports."
- **Excellent looks like:** a poisoning attempt via deliberately-vague locations
  measurably cannot move the primary ranking (add this as a red-team test alongside
  `tests/test_publish_privacy.py`).

### FIX-08 — Strict config validation
- **Status:** ✅ Done — strict config validation (`_reject_unknown` on top-level and `[thresholds]` keys, range checks, did-you-mean hints).
- **Pitch:** Reject unknown config keys and out-of-range thresholds instead of
  silently ignoring them.
- **Why it matters:** `load_config` (`src/nearmiss/config.py`) drops unknown keys and
  unknown `[thresholds]` entries on the floor. A typo (`fdr_aplha`, `min_publsh_n`)
  silently runs the analysis at defaults — in a project where those numbers govern
  published significance and privacy. This is the cheapest correctness/operability
  fix in the repo.
- **Shape:** Enumerate allowed top-level and threshold keys; raise `ConfigError`
  listing unknowns with a did-you-mean; validate ranges (`0 < fdr_alpha < 1`,
  `min_publish_n >= 2`, `confidence_z > 0`, `kde_grid >= 2`, window sanity from
  FIX-05); tests for each. Optionally emit a canonicalized "effective config" block
  into the run manifest (FIX-09).
- **Effort:** S. **Risks:** `raw=data` passthrough is used nowhere critical, but
  third-party configs with extra keys will now fail — that is the point; provide an
  `x-` escape prefix for annotations.
- **Excellent looks like:** a misspelled threshold cannot alter a published dataset;
  `tests/test_robustness.py` gains the typo cases.

### FIX-09 — Run manifest + pipeline-stage telemetry ✅ DONE
- **Status:** Done (branch `roadmap/fix-09-run-manifest-pipeline-stage-telem`). New
  stdlib-only `src/nearmiss/manifest.py` (`sha256_file`, `effective_config`,
  `build_manifest`); `engine.build_analysis` times each stage and attaches
  `{stage, counts, ms}` to `AnalysisBundle.stages`; `publish()` writes
  `<slug>.run.json` (gitignored — the timings sidecar is unhashed and not
  byte-stable) and runs its provenance section through `assert_metadata_clean`;
  `__main__ run` emits one `msg="stage"` JSON line per stage via `obs.get_logger()`.
  The `manifest_digest` covers the provenance section only, so `make reproduce`
  stays byte-stable. Tests: `tests/test_manifest.py` + extensions to
  `test_observability.py`, `test_publish_privacy.py`, `test_reproduce.py`.
- **Pitch:** Emit a machine-readable provenance manifest per run (input file SHA256s,
  effective config hash, package version, per-stage counts, wall-times) next to the
  published artifacts, and structured stage logs via the existing `obs.py`.
- **Why it matters:** README claims "structured logs and metrics on intake and each
  pipeline stage"; only `server.py` logs today. More importantly, the
  figure→statistic→raw traceability chain is documented prose — a manifest makes it a
  diffable artifact, closes the observability overclaim, and gives `make reproduce`
  a richer tripwire (it can explain *what* drifted, not just that bytes did).
- **Shape:** New `src/nearmiss/manifest.py`; `engine.build_analysis` collects stage
  summaries (pipeline already returns one) and timings; `publish.py` writes
  `<slug>.run.json` (hashes of `streets/reports/exposure` inputs, config digest,
  `nearmiss` version, stage counts including FIX-05's `out_of_window` and FIX-07's
  excluded fraction); `__main__.py` `run` logs one JSON line per stage through
  `obs.get_logger()`. Privacy: manifest contains counts and hashes only — extend
  `assert_metadata_clean` to it.
- **Effort:** M. **Risks:** the manifest must be deterministic (no timestamps in the
  hashed portion) or it breaks the reproduce gate; keep timings in an unhashed
  sidecar section.
- **Excellent looks like:** given only `data/published/`, a third party can verify
  which exact inputs and config produced it; a reproduce failure names the drifted
  input.

### FIX-10 — Machine-readable published-dataset schema + contract gate
- **Status:** ✅ Done (PR #41, 2026-07-12) — `schema/dataset.schema.json` + publish-time validation + `web/contract_check.mjs` consumer-contract CI gate.
- **Pitch:** Ship the `dataset.schema.json` that `CHANGELOG.md` already claims exists,
  validate both committed GeoJSONs against it in CI, and treat `web/app.js` +
  `web/embed.js` as contract consumers with a fixture-driven test.
- **Why it matters:** The published GeoJSON is the product, and its only schema is
  prose (`schema/dataset.schema.md`). Downstream consumers (QGIS users, `RE-11`'s
  reuse kit, `RE-12`'s API) have nothing to validate against, and a publisher-side
  field rename would ship silently. The CHANGELOG's claim of a CI-validated mirror
  schema is currently false (FIX-03 catches this class; FIX-10 is the substantive
  half).
- **Shape:** Write `schema/dataset.schema.json` (Feature properties, metadata foreign
  member, flag vocabularies as enums — additive-friendly per the versioning policy in
  `dataset.schema.md` §7); add a `publish` self-check (validate before write, same
  pattern as `assert_published_clean`); CI job validates `data/published/*.geojson`;
  a jsdom test (the axe harness in `web/axe_check.mjs` shows the pattern) loads the
  fixture GeoJSON through `app.js`'s parsing path.
- **Effort:** M. **Risks:** schema and prose doc can themselves drift — generate the
  field table in `dataset.schema.md` from the JSON Schema, or add both to FIX-03's
  manifest.
- **Excellent looks like:** any conforming consumer can validate any nearmiss
  dataset offline; a property rename fails CI in two places (publisher and web
  consumer) before it can ship.

### FIX-11 — Supply-chain completion: hashed CI installs, release automation, signed artifacts
- **Status:** ✅ Done (PR #51, 2026-07-12) — hashed `--require-hashes` CI installs from `requirements-dev.lock`, single-sourced versions (`versions.py`), tag-triggered release pipeline with SBOM/Sigstore/SLSA/Trusted Publishing.
- **Pitch:** Make CI install from the committed hashed lock, extend locking to the
  dev toolchain, and automate tag-triggered releases with signing/attestation —
  turning README's "signed releases" and the vendored
  SECURITY-AND-SUPPLY-CHAIN-STANDARD's SBOM/Sigstore/SLSA rows from claims into
  mechanisms.
- **Why it matters:** `requirements.lock` is committed but covers only the runtime
  dependency tree (`piptools compile pyproject.toml` — effectively `jsonschema`);
  every CI job still runs unpinned `pip install -e ".[dev]"`, so the actual gate
  toolchain (pytest, ruff, mypy, pip-audit, babel) is resolved fresh each run. No git
  tags exist; `publish.py` hardcodes `dataset_version`/`schema_version` strings.
  Builds beyond `RR-10` (commit the lock — done) and `RR-11` (tag + DOI): this is the
  automation and integrity layer those assume.
- **Shape:** `make lock-dev` compiling `.[dev]` with hashes; CI installs
  `--require-hashes` (Renovate/Dependabot keep it fresh — `renovate.json` exists);
  single-source the version (read `importlib.metadata` in `publish.py` instead of
  literals; dataset/schema versions move to constants in one module); a
  `release.yml` workflow on tag: build, generate SBOM, sign wheel + both published
  GeoJSONs with Sigstore, attach SLSA provenance, publish via PyPI Trusted
  Publishing (OIDC), append the CHANGELOG's dual schema-version sections.
- **Effort:** L. **Risks:** hash-pinned CI breaks on transitive releases until
  Renovate PRs land (that is the designed behavior); Sigstore signing of *data*
  artifacts is unusual — document verification steps in `docs/REAL-DATA.md` or the
  data card so it helps rather than mystifies.
- **Excellent looks like:** a consumer can cryptographically verify that
  `davis.geojson` came from a tagged, CI-built release of this repo; no version
  string exists in more than one place.

### FIX-12 — Spatial indexing for the quadratic cores (keep pure Python)
- **Status:** ✅ Done — `spatial_index.py` grid index consumed by KDE/Gi\* band queries (now in `honest_rates.spatial_index`).
- **Pitch:** Grid-bucket spatial index shared by `snap`, `dedupe`, KDE, and Gi\*
  neighbor search, lifting the practical ceiling from ~10³ to ~10⁴–10⁵ segments
  without breaking ADR-0003's no-native-deps rule.
- **Why it matters:** `docs/PERFORMANCE.md` honestly documents O(n²) dedupe and the
  O(M²) Gi\* step (~5.5 s at 300 segments/6k reports). Sacramento-scale OSM extracts
  (the committed `config/sacramento.toml` target) will be an order of magnitude
  larger, and EXP-03 (corridors) and EXP-09 (benchmark suite) both want headroom. No
  existing backlog item targets the algorithmic core.
- **Shape:** `src/nearmiss/spatial_index.py`: uniform grid over the projected plane
  (cell = max(snap_max_m, gi_band_m)); `snap.py` queries candidate segments from
  3×3 neighborhoods instead of scanning all; `dedupe.py` buckets by (cell,
  time-window); `getis_ord_star` takes the neighbor map (shared with FIX-02's graph
  path); KDE evaluates only cells within ~4σ of any point. Extend
  `tools/benchmark.py` with a 5k-segment case and assert results are *identical* to
  the naive path on fixtures (index is an accelerator, never an approximation).
- **Effort:** L. **Risks:** subtle boundary bugs (report exactly on a cell edge) —
  property-test equality against the brute-force path (FIX-14's harness);
  determinism must survive iteration-order changes (sort candidates by id).
- **Excellent looks like:** `python tools/benchmark.py 5000 100000` completes in
  under a minute; fixture outputs byte-identical to pre-index runs; PERFORMANCE.md
  updated with the new honest ceiling.

### FIX-13 — Single-source web i18n from the gettext catalogs
- **Status:** ✅ Done (PR #42, 2026-07-12) — web UI strings single-sourced from the gettext catalogs via `web_i18n.py` + `tools/po2json.py` -> `web/locales/*.json`.
- **Pitch:** Generate the web UI's translations from the same PO catalogs the brief
  uses, and put the web strings under the `make i18n` parity gate.
- **Why it matters:** `web/app.js` and `web/submit.js` carry hand-maintained `I18N`
  dictionaries that no gate covers; the Python side has full POT-drift/parity/BCP-47
  gates. The two surfaces will drift (a renamed hazard label in the brief but not the
  table breaks the "two views of one artifact" seamlessness claim), and every future
  locale must be added twice. Distinct from `RR-13` (finish the *Spanish content*);
  this is the *architecture* that makes RR-13 and every later locale cheap.
- **Shape:** Extract web strings into the babel workflow (babel can extract from JS,
  or maintain a small `web/locales/*.json` generated by a `tools/po2json.py` step in
  `make i18n-compile`); `app.js` loads the JSON catalog for the active `lang`;
  `tools/check_catalog_parity.py` extends to the web domain; document in
  `docs/I18N.md`.
- **Effort:** M. **Risks:** the static-hosting model (GitHub Pages, no build step
  today) means generated JSON must be committed — the existing committed-`.mo`
  pattern already accepts that trade.
- **Excellent looks like:** one `msgid` inventory covers brief + web; adding locale
  N+1 touches `locales/` only; the parity gate fails when a web string bypasses the
  catalog.

### FIX-14 — Numerical hardening + property/metamorphic test harness for the stats core
- **Status:** ✅ Done — numerical hardening (two-pass Gi\* variance) + hypothesis property/metamorphic suite (`tests/test_stats_properties.py`, `tests/test_stats_numerics.py`).
- **Pitch:** Replace cancellation-prone formulas, then pin the statistical invariants
  with property-based (Hypothesis) and metamorphic tests — including the
  interval-coverage simulations METHODOLOGY §9.2 currently claims but the suite lacks.
- **Why it matters:** `getis_ord_star` computes variance as `sum(x²)/n − mean²`
  (catastrophic cancellation for large means); KDE sums exponentials naively; and the
  strongest calibration claim in the methodology (95% intervals cover ~95%) has no
  witness test on `main`. The advisory mutation suite (`docs/MUTATION-TESTING.md`)
  probes the code's *sensitivity to edits*; nothing probes its *mathematical
  invariants*.
- **Shape:** Welford/two-pass variance in `getis_ord.py`; a seeded coverage
  simulation test (simulate Poisson counts at known θ across the small-count range,
  assert Byar coverage within tolerance — deterministic seed, marked slow);
  Hypothesis strategies asserting: rate scales linearly with `per`; scaling all
  exposures by c scales rates by 1/c with identical z-scores; permuting segment order
  changes nothing; CIs widen monotonically in z; `poisson_ci` bounds are ordered and
  non-negative; dedupe is order-independent given the chrono sort. Add Hypothesis to
  the `dev` extra (audited surface change — note for the pip-audit gate).
- **Effort:** M. **Risks:** flaky tolerance choices — fix seeds and use generous but
  meaningful bounds (coverage ∈ [0.92, 0.98] at n≥ the documented range); Hypothesis
  shrinking output must not embed anything resembling real coordinates (it won't —
  fixtures are abstract).
- **Excellent looks like:** §9.2 becomes true; a future refactor of the stats core
  (FIX-02/FIX-12) lands with these invariants as the safety net; mutation survivors
  in `rates.py` drop against the documented baseline.
