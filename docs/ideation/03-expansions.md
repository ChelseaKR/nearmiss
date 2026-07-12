# Expansions (EXP-01 … EXP-16) — drafted 2026-07-01

Three horizons: **H1** deepen the core, **H2** adjacent capabilities/audiences/
integrations, **H3** transformative bets. All net-new relative to README Phases 1–4,
the panel backlog (`R#`/`E#`), and the research roadmap (`RR-#`/`RE-#`); overlaps are
cited and exceeded, and everything respects the panel's anti-features list
(no routing product, no gamification, no real-time raw feed, no crystal-ball claims).

---

## H1 — Deepen the core

### EXP-01 — Publish-time null-calibration panel ("we attacked our own dataset")
- **Pitch:** For every published city, run the full hotspot method against label-
  shuffled and rate-homogenized versions of that city's own data and publish the
  false-positive behavior as a calibration artifact beside the dataset.
- **Impact:** Converts §9.3's *fixture-time* null tests into a *per-dataset* proof a
  skeptic can inspect: "on 200 shuffles of this exact network and exposure, the
  method flagged a mean of 0.4 spurious hotspots at fdr_alpha=0.05." Distinct from
  `RR-09` (permutation inference for the statistic itself); this is a published
  diagnostic of the whole pipeline's calibration on the city's real geometry.
- **Shape:** `src/nearmiss/stats/calibration.py` (seeded shuffle of counts across
  segments holding exposure fixed; re-run `getis_ord_star`+BH; summarize);
  `nearmiss analyze --calibrate` writes `<slug>.calibration.json`; brief gains one
  sentence; web provenance banner links it. Privacy-safe by construction (aggregates
  of aggregates).
- **Effort:** M (L if FIX-12 isn't done first — 200 re-runs of an O(M²) core).
- **Risks/deps:** FIX-12 for runtime; deterministic seeds for the reproduce gate.
- **Excellence bar:** every published dataset ships a calibration file; the demo
  cities' false-positive rate is ≤ the nominal FDR within simulation error.

### EXP-02 — Versioned dataset releases with honest change attribution
- **Status:** ✅ Done (2026-07-02) — `tools/diff_datasets.py` attributes every
  hotspot appearance/disappearance between two vintages to a cause (method
  change, threshold change, revised exposure, new reports, suppression, or
  recomputation), emitting a machine-readable `.json` + `.md` change report
  under `data/published/changes/` with the reporting-decline bias caveat carried
  verbatim into every report. Uses the existing `<slug>.metadata.json` sidecars
  as the run-manifest substitute (FIX-09 manifests do not yet exist) and
  degrades to counts-only attribution when they are absent. Covered by
  `tests/test_diff_datasets.py`.
- **Pitch:** Publish dataset vintages (v2026-Q3, …) with a generated change report
  that *attributes* every hotspot appearance/disappearance to its cause: new
  reports, revised exposure, method change, or threshold change.
- **Impact:** The politically dangerous moment for any safety dataset is when a
  hotspot vanishes ("was it fixed, or did you fiddle the numbers?"). Attribution
  answers it mechanically. Goes beyond `RE-11`'s machine-readable version feed (which
  lists versions) — this explains *why* the ranking moved, leaning on FIX-09's run
  manifests to diff inputs vs. method.
- **Shape:** `tools/diff_datasets.py` consuming two `<slug>.geojson` +
  `<slug>.run.json` pairs; classification logic (input hash changed vs.
  `metadata.methods` changed vs. counts changed); markdown + JSON change report
  committed under `data/published/changes/`.
- **Effort:** M. **Risks/deps:** FIX-09 (manifests), FIX-11 (real releases to diff);
  wording discipline so "hotspot resolved" is never claimed from reporting decline
  alone (bias caveat carries over).
- **Excellence bar:** a journalist can quote the change report verbatim without
  misattributing a ranking shift.

### EXP-03 — Corridor-level aggregation for advocacy asks
- **Pitch:** Merge contiguous significant segments (via FIX-02's street graph) into
  named corridors with corridor-level rates, CIs, and n — the unit council motions
  are actually written in.
- **Impact:** Briefs currently rank blocks; campaigns target corridors ("5th St from
  A to F"). Aggregation also stabilizes small-n blocks legitimately (larger n, same
  denominator discipline) — a MAUP-aware complement to `RE-02`'s smoothing, published
  *alongside* block-level results, never instead of them.
- **Shape:** `stats/corridors.py`: union contiguous same-street significant segments;
  recompute count/exposure sums → `rate_with_ci`; publish as a second
  FeatureCollection layer or `corridor_id` property; brief's ranked table gains a
  corridor view; MAUP transparency note auto-included (both granularities shown, per
  the `stats/maup.py` discipline once FIX-01 lands).
- **Effort:** M–L. **Risks/deps:** FIX-01, FIX-02; naming heuristics from segment
  `name` fields; must not resurrect k-anonymity leaks (corridor counts are sums of
  already-publishable segments — assert it).
- **Excellence bar:** the demo brief produces one correct corridor ("5th St (C–F)")
  and zero corridors that chain across barriers.

### EXP-04 — Pluggable source-adapter framework with declarative crosswalks
- **Pitch:** Promote the BikeMaps fetcher pattern into a first-class adapter
  framework — declarative field-crosswalk manifests, per-source provenance and bias
  labels — and land the orphaned SimRa adapter as the second adapter.
- **Impact:** README Phase 4 gestures at "optional import paths"; `docs/REAL-DATA.md`
  hand-documents one crosswalk table. A framework makes each new source (SimRa,
  city 311/SeeClickFix exports, advocacy-group spreadsheets) a manifest + tests, and
  forces per-source honesty: every imported dataset carries its source's own bias
  profile into `bias.py`'s narrative and the data card. Note: a complete
  `tools/fetch_simra.py` + tests already exists unmerged on
  `origin/claude/real-data-map-integration-mud09x`.
- **Shape:** `src/nearmiss/adapters/` with a `SourceAdapter` protocol (fetch/parse →
  intake-schema dicts + a provenance block); crosswalk tables as data
  (TOML) validated against both schemas; migrate `tools/fetch_bikemaps.py`, merge the
  SimRa branch; adapter conformance test (round-trip through
  `validation.validate_report`).
- **Effort:** L. **Risks/deps:** upstream API drift (keep the offline `--from-file`
  paths canonical for tests); severity/type mappings are judgment calls — record each
  in the manifest with a rationale line, per the existing crosswalk's
  "honesty over precision we don't have" rule.
- **Excellence bar:** adding a new source touches no pipeline code; every published
  dataset's data card lists per-source report counts and the source's bias label.

### EXP-05 — Privacy-budgeted segment×time-band release (differential privacy)
- **Pitch:** Unlock the "dangerous at the 3pm school bell" question that
  `docs/LIMITATIONS.md` currently rules out, by releasing coarse segment ×
  part-of-day counts under a formal ε-DP noise mechanism instead of the current
  all-or-nothing suppression.
- **Impact:** Safe-Routes-to-School advocacy (panel persona P2) is blocked today
  because `stats/temporal.py` is deliberately city-wide-only. DP noise on coarse
  bands could be provably safe where k-anonymity thresholds alone are not — or the
  analysis may show it isn't worth the noise at nearmiss's ns; either result is
  publishable.
- **Shape:** design doc first (mechanism, ε, sensitivity of a report-add on
  segment×band cells, composition with the existing GeoJSON release); prototype in
  `stats/temporal.py` behind config; publish only with the noise scale and ε stated
  in metadata (statistical candor extends to the privacy math).
- **Effort:** XL. **Risks/deps:** **hard SME gate — a privacy researcher must review
  the mechanism before anything ships** (see `04-…` gates); risk of
  utility-theater (noise so large the bands are meaningless — measure and say so);
  interacts with THREAT-MODEL T1's linkage adversary.
- **Excellence bar:** a written adversarial analysis a red-teamer (persona P23)
  signs off on, and published bands whose noise is stated beside every number.

### EXP-06 — Contributor data-rights tooling
- **Pitch:** Token-based self-service for contributors: export "my reports," request
  deletion, and an automated retention policy for the private raw store.
- **Impact:** The consent posture is currently prose (`RR-15` is a *statement*;
  DATA-CARD §consent is description). Executable rights — delete-my-data that
  actually re-runs the pipeline and republishes — makes the community-ownership claim
  concrete and future-proofs against privacy regulation for any hosted deployment.
- **Shape:** `nearmiss contributor export|delete <reporter_token>` operating on
  `data/raw/` + the moderation stores; deletion tombstones (so re-imports of the same
  upstream source don't resurrect deleted reports — hash the upstream id);
  `make reproduce` semantics after deletion documented (published artifacts change,
  legitimately); retention window in config.
- **Effort:** M. **Risks/deps:** token possession is the only auth (documented
  honestly — whoever holds the token holds the rights); deletion vs. the
  append-only approved store in `moderation.py` needs a compaction path.
- **Excellence bar:** deletion round-trip test: submit → approve → publish → delete →
  republish shows the count decrement and no residue in any store.

### EXP-07 — Moderation transparency report
- **Pitch:** Publish per-release counts of submissions received/approved/rejected,
  rejection-reason categories, flag frequencies, and median review latency.
- **Impact:** The moderation queue (`src/nearmiss/moderation.py`) is a human
  judgment point in an otherwise mechanically-audited pipeline — the one place
  censorship or bias could hide. A transparency report applies the project's
  audit-as-artifact discipline (`docs/audits/README.md`) to its own gatekeeping,
  and deters the astroturf narrative in both directions. Complements `RE-10`
  (defenses) — this is accountability *for* the defenses.
- **Shape:** `nearmiss moderate stats` aggregating `queue.json` (statuses, flags,
  `received_at`→decision latency; reasons bucketed by a small taxonomy); emitted
  into the metadata sidecar and a `docs/audits/`-style dated artifact. Privacy: counts
  only; reason free-text never published verbatim.
- **Effort:** S–M. **Risks/deps:** tiny-n cells can identify a rejected submitter in
  a small town — apply the existing `min_publish_n` floor to report cells.
- **Excellence bar:** every published dataset states how many submissions did *not*
  make it in, and why, in categories.

## H2 — Adjacent capabilities, audiences, integrations

### EXP-08 — Extract the stats core as a standalone "honest rates" library
- **Pitch:** Package `stats/` (exposure-normalized rates, small-count CIs,
  Gi\*+FDR, bias shares, planted-fixture harness) as an independent, documented
  library for *any* point-event dataset — crime, code-enforcement, wildlife strikes,
  service requests.
- **Impact:** README already claims "the exposure-normalization and hotspot code are
  usable on any point dataset"; nothing makes that true (imports are package-relative,
  models are nearmiss-specific). A clean extraction multiplies the portfolio's
  methods-credibility and gives other portfolio repos (and outsiders) the same
  denominator discipline for one `pip install`.
- **Shape:** New repo or `src/honest_rates/` namespace consumed by nearmiss;
  interface = plain sequences + a small `Unit` protocol instead of
  `models.Segment`; carry the planted-fixture test harness as part of the public API
  (the harness *is* the differentiator); nearmiss becomes its first consumer.
- **Effort:** L. **Risks/deps:** FIX-02/FIX-12/FIX-14 first (don't freeze a
  straight-line-band API); versioning discipline across two repos (the
  RELEASE-AND-VERSIONING standard's public-API contract applies).
- **Excellence bar:** a non-traffic demo notebook (e.g., 311 pothole *reports* vs.
  street *traffic* exposure) reaches correct "busy ≠ dangerous" conclusions using
  only the extracted library.

### EXP-09 — Open planted-truth benchmark suite for hotspot methods
- **Pitch:** Publish a suite of synthetic cities with known ground truth across
  controlled regimes — reporting bias strength, overdispersion φ, MAUP
  sensitivity, exposure error — as a public benchmark any hotspot tool can run.
- **Impact:** `tools/make_fixtures.py` and `tools/benchmark.py` already generate
  planted-truth cities; generalizing them into a versioned benchmark positions
  nearmiss as the referee of the heat-map-lie problem, not just one contestant, and
  gives RR-02/RR-05-class methods work a permanent measuring stick. Strong portfolio
  fit (evaluation-harness DNA).
- **Shape:** `benchmarks/` with generator configs + frozen generated cities +
  ground-truth manifests + a scorer (precision/recall on planted hotspots, decoy
  false-positive rate, interval coverage); score nearmiss itself and publish the
  scorecard; invite other tools via a README table.
- **Effort:** L. **Risks/deps:** benchmark overfitting (rotate held-out regimes);
  generation must be seeded and documented so the "known answers" claim is
  verifiable.
- **Excellence bar:** an external tool author can produce a comparable scorecard in
  under an hour; nearmiss's own scorecard is committed, including the regimes where
  it does poorly.

### EXP-10 — HR1–HR5 conformance verifier for forks and instances
- **Status:** ✅ Done (2026-07-02). Shipped as `tools/verify_dataset.py` (stdlib-only
  CLI: JSON verdict + 0/1 exit), covered by `tests/test_verify_dataset.py` (both
  committed datasets pass; a corrupted fixture fails each of HR1–HR5 individually), and
  wired into `make conformance` / `make verify`. The verdict is scoped to the artifact,
  not the publisher's conduct.
- **Pitch:** A runnable checker that audits any nearmiss-style published artifact
  for the five hard rules — denominator present or honestly absent, intervals on
  every rate, bias statement present, k-anonymity floor respected, reproducibility
  manifest attached — and issues a machine-verdict.
- **Impact:** ADAPTING.md invites forks; nothing today stops a fork from publishing
  raw-count "danger" maps under the nearmiss name. The panel's E20 gallery idea
  presumes a human-reviewed quality badge — this is the *machine* half that makes
  human review scale, and it protects the method's reputation as it spreads.
- **Shape:** `tools/verify_dataset.py` (or a subcommand) consuming any
  `<slug>.geojson` + sidecar: schema-validate (FIX-10), assert no 0<n<floor
  feature, assert rate⇒interval⇒n, assert metadata privacy text and methods block;
  exit code + JSON verdict; document as the gallery's entry gate.
- **Effort:** M. **Risks/deps:** FIX-10 (schema); a verdict is about the *artifact*,
  not the fork's private conduct — say so to avoid overclaiming what a static check
  proves.
- **Excellence bar:** the verifier rejects a deliberately-corrupted fixture on all
  five rules; the two committed datasets pass it in CI.

### EXP-11 — QGIS plugin with honest symbology
- **Pitch:** A small QGIS plugin that loads any conforming nearmiss GeoJSON with the
  correct visual grammar pre-wired: rate-not-count symbology, CI-labeled tooltips,
  significance as pattern+text, `exposure_unknown` rendered as "unknown," never as
  zero.
- **Impact:** Planners and GIS analysts (panel P9/P14) live in QGIS; today they get
  raw attributes and can innocently rebuild the heat-map lie in two clicks. Goes
  beyond `RE-11`'s static `.qml` style: a plugin can enforce the legend text, load
  the metadata block into layer properties, and run the EXP-10 verifier on load.
- **Shape:** Python QGIS plugin (separate repo or `integrations/qgis/`);
  reads `metadata` foreign member; ships both demo datasets as sample data.
- **Effort:** L. **Risks/deps:** FIX-10 schema; QGIS plugin review cycle; maintenance
  surface for a new runtime (accept: plugin is thin, logic stays in the schema).
- **Excellence bar:** a GIS user who has never read METHODOLOGY produces a
  presentation-ready map that a skeptical traffic engineer cannot fault on labeling.

### EXP-12 — "How to lie with heat maps" teaching module
- **Pitch:** A self-contained curriculum built on the decoy fixtures: the same
  reports rendered naively vs. honestly, with exercises (find the decoy; break the
  CI; re-segment and watch a hotspot dissolve) — for journalism programs, civic-data
  workshops, and advocacy onboarding.
- **Impact:** The project's most transferable asset is the *argument*, and the
  fixtures make the argument runnable. Educates the exact consumers (journalists,
  council staff) whose misreads are THREAT-MODEL T4's adversary-free failure mode.
  Net-new audience; no new privacy surface (synthetic data only).
- **Shape:** `docs/teaching/` or `notebooks/`: 3–4 executed notebooks + a facilitator
  guide; reuse `notebooks/hotspots.ipynb` patterns; bilingual per the i18n
  discipline; accessibility of notebook HTML per the a11y gate.
- **Effort:** M. **Risks/deps:** keep it evergreen by driving from fixtures, not real
  cities; CI-execute the notebooks (also closes the "notebooks are the
  reproducibility backbone" claim gap noted in `01-deep-dive.md`).
- **Excellence bar:** a workshop participant can articulate, unprompted, why the
  busiest street lit up on the left map and not the right one.

### EXP-13 — Locale scaling kit (pseudo-locale gate, RTL smoke, onboarding path)
- **Pitch:** The machinery to go from 2 locales to N: a pseudo-locale CI check
  (catches concatenation/truncation/hardcoded strings), an RTL smoke test for the web
  view, and a documented community-translation workflow.
- **Impact:** `RR-13` finishes Spanish; the INTERNATIONALIZATION-STANDARD (vendored)
  names pseudolocale and RTL gates that nearmiss doesn't have. Language access is an
  equity feature here (under-reported groups are disproportionately LEP — the bias
  section's own argument), so cheap locale onboarding is mission, not polish.
- **Shape:** Generate `xx-pseudo` from the POT in `make i18n`; assert brief renders
  and no `_()`-bypassing string appears; Playwright/jsdom RTL layout smoke on
  `web/index.html` with `dir=rtl`; `docs/I18N.md` gains a "add a locale" runbook
  keyed to `tools/check_bcp47.py` and parity gates. Depends on FIX-13 so a locale is
  added once, not twice.
- **Effort:** M. **Risks/deps:** FIX-13; pseudo-locale must be excluded from
  published/shipping catalogs.
- **Excellence bar:** a community translator with no Python can submit a PO file and
  see it live in brief + web with zero code review comments about mechanics.

## H3 — Transformative bets

### EXP-14 — A governed open near-miss data standard with conformance suite
- **Pitch:** Promote `schema/dataset.schema.md` + `schema/report.schema.json` into a
  versioned, multi-stakeholder public specification — with the EXP-10 verifier as its
  conformance suite and documented crosswalks to BikeMaps, SimRa, and MMUCC/KABCO
  vocabularies.
- **Impact:** Today every crowdsourced-safety tool has a private schema; researchers
  re-crosswalk by hand (the `RE-03` MMUCC crosswalk is one instance). A standard is
  the difference between "a good repo" and "infrastructure." nearmiss is unusually
  well-positioned: its schema already ships versioning/deprecation policy
  (`dataset.schema.md` §7) and privacy invariants as first-class schema properties.
- **Shape:** Spin the schema into its own governed repo (spec text, JSON Schemas,
  conformance suite, crosswalk registry from EXP-04's manifests); recruit 2–3
  external implementers before calling it a standard; nearmiss becomes reference
  implementation.
- **Effort:** XL, mostly non-code. **Risks/deps:** governance is the hard part —
  without external adopters this is just renaming; **human gate: real conversations
  with BikeMaps/SimRa maintainers and at least one agency data owner** before
  drafting v1.
- **Excellence bar:** two independent tools exchange datasets that both pass the
  conformance suite without bilateral coordination.

### EXP-15 — Federated multi-instance commons (signed, conformant, aggregate-only)
- **Pitch:** A static federation index where independent nearmiss instances publish
  signed dataset metadata; a national/regional view is composed *only* from instances
  that pass EXP-10 conformance, showing per-city methods and coverage — never pooled
  rankings across incomparable exposure units.
- **Impact:** The honest version of "a national near-miss map": federation preserves
  community ownership (the project's stated governance value) while making the
  method's reach visible. Explicitly *not* the panel's auto-published gallery
  anti-feature: entry requires conformance + human review, and cross-city rate
  comparison is refused by design (exposure units differ — HR1 applies across
  cities too).
- **Shape:** `federation.json` spec (instance URL, dataset hashes, Sigstore
  signatures from FIX-11, conformance verdict from EXP-10, methods block); a static
  aggregator page; documented onboarding.
- **Effort:** XL. **Risks/deps:** FIX-11, EXP-10, EXP-14; moderation/liability
  questions when a member instance goes rogue — needs a written de-listing policy
  (human/legal gate).
- **Excellence bar:** three real instances federate; the aggregate view contains no
  number that pools across exposure units.

### EXP-16 — Pre-registered prospective evaluation of the method itself
- **Pitch:** The strongest possible honesty move: publicly pre-register, with
  timestamps, which FDR-significant corridors the current dataset flags, then score
  those predictions against the *next* period's independent data (new reports held
  out; official collisions where `RE-01`'s pipeline exists) — and publish the score,
  win or lose.
- **Impact:** `RE-01` is a retrospective validation study; pre-registration is the
  prospective, unfakeable version — it converts "near-miss data is a leading
  indicator" from literature citation into a tested claim about *this* system, and
  it is immune to the garden of forking paths because the predictions are frozen
  first. If the method fails, publishing that is exactly the portfolio's
  defer-and-report-honestly ethos.
- **Shape:** A registration artifact (hashed, timestamped — Sigstore/OSF) freezing
  dataset version, method params (FIX-11's single-source versions make this
  precise), flagged segments, and the scoring rule (e.g., rank correlation and
  hit-rate with CIs against held-out counts); a scheduled scoring run one period
  later; results committed as a dated audit artifact.
- **Effort:** XL elapsed (the work is small; the *time* is the cost). **Risks/deps:**
  needs real accumulating data (Sacramento config + EXP-04 sources); **SME gate: a
  statistician must approve the scoring rule before registration**; the framing must
  pre-commit to publishing a null result.
- **Excellence bar:** a dated, hash-verifiable prediction artifact exists before the
  evaluation window opens, and the scored outcome — whatever it is — is published
  with the same prominence as the predictions.
