# Claims manifest

Every load-bearing accuracy claim in the prose docs is wrapped in a paired HTML comment
(`<!-- claim:ID --> … <!-- /claim:ID -->`) and listed here with a **witness**: the test or source
file that makes the claim true (or, for a "planned, not yet implemented" claim, the file whose
*absence of* the feature the wording honestly describes).

`tools/check_claims.py` (run by `make claims`, part of `make verify`) enforces the manifest in both
directions:

- every claim ID below appears as a **matched** open/close tag pair in its doc file;
- every witness path exists, and a `path::test_name` witness names a function that exists **and that
  test is collected by pytest and passes**;
- every `<!-- claim:… -->` tag found in any root-level or `docs/` Markdown file — including every doc
  the shipped HTML links to — is listed here; a tagged claim missing from this table fails the gate
  (drift is caught both ways).

The witness is deliberately narrow: it is the thing a reviewer can open to confirm the sentence is
not an overclaim. When a claim says a feature is *planned*, the witness is the file that would house
it, so the gap stays visible instead of drifting back into a promise.

**What the gate can and cannot confirm.** A witness that names a test is *run*: it has to be
collected and to pass, so a skipped, xfailed, emptied-out, or uncollected witness fails the build
rather than satisfying it. A witness that names a plain file — a lockfile, a schema, a module whose
*absence* of a feature is the claim — has no test to run, and is checked for existence only. The gate
prints which witnesses fell into that second category rather than reporting them as green, because
"this file is here" is weaker evidence than "this test passes" and a reader should be told which one
a given sentence rests on.

**Scope.** The scan covers every `*.md` at the repository root and every `docs/**/*.md`, and it
separately resolves every `docs/…md` link in the repository's HTML so the docs a visitor reaches from
the live site are always read (a site link to a doc that does not exist is an error here too). Since
this is a drift gate for *tagged* sentences, a wide scan costs nothing until a claim is tagged — it
only removes blind spots.

| Claim ID | Doc anchor (file + section) | Witness (test or file) |
| --- | --- | --- |
| `lockfile-committed-hashed` | `README.md` — § Install | `requirements.lock` |
| `obs-intake-only` | `README.md` — § Observability | `src/nearmiss/obs.py` |
| `dataset-schema-prose` | `CHANGELOG.md` — § Scope and conventions | `schema/dataset.schema.md` |
| `rate-union-primary-plus-per-type-layers` | `docs/METHODOLOGY.md` — § 1. Notation and the unit of analysis | `tests/test_publish_privacy.py::test_rates_by_type_publishes_type_specific_rate_matching_breakdown` |
| `low-confidence-excluded-from-primary` | `docs/METHODOLOGY.md` — § 2. From raw reports to counts | `tests/test_stats_numerics.py::test_quality_tier_split_primary_rate_excludes_low_confidence` |
| `exposure-sensitivity-declared-only` | `docs/METHODOLOGY.md` — § 3.3 The exposure floor and "exposure unknown" | `tests/test_exposure_sensitivity.py::test_no_declared_alternative_is_not_evaluated_never_stable` |
| `overdispersion-widens-every-published-interval` | `docs/METHODOLOGY.md` — § 4. Rates: turning counts and exposure into risk | `tests/test_overdispersion.py::test_per_hazard_type_intervals_are_widened_too` |
| `maup-varies-only-the-units` | `docs/METHODOLOGY.md` — § 8.3 What we publish from the spatial layer | `tests/test_maup.py::test_coarse_rates_use_the_primary_count_the_published_rate_uses` |
| `byar-poisson-ci` | `docs/METHODOLOGY.md` — § 5.2 Interval for a single segment's rate | `tests/test_rates.py::test_poisson_ci_contains_point_and_widens_relatively_for_small_n` |
| `wilson-proportions` | `docs/METHODOLOGY.md` — § 5.3 Proportions, when the question is a share | `tests/test_rates.py::test_wilson_ci_bounds` |
| `bh-fdr` | `docs/METHODOLOGY.md` — § 5.5 Multiplicity | `tests/test_fdr.py::test_significant_field_is_fdr_corrected_in_analysis` |
| `gi-on-rate-not-count` | `docs/METHODOLOGY.md` — § 8.2 Getis-Ord Gi\* | `tests/test_hotspot.py::test_getis_ord_flags_the_planted_corridor_cluster` |
| `gi-weights-network` | `docs/METHODOLOGY.md` — § 8.2 Getis-Ord Gi\* | `tests/test_network.py` |
| `gi-permutation-beside-not-instead` | `docs/METHODOLOGY.md` — § 8.2 Getis-Ord Gi\* | `tests/test_gi_permutation.py::test_methodology_describes_what_the_permutation_pass_actually_computes` |
| `coverage-sims-implemented` | `docs/METHODOLOGY.md` — § 9.2 Interval-coverage checks | `tests/test_coverage_simulation.py::test_byar_poisson_interval_coverage` |
| `dossier-claim-boundary` | `docs/DECISION-DOSSIER-TEMPLATE.md` — § 2. Claim boundary | `tests/test_dossier.py::test_dossier_is_corridor_specific_and_claim_limited` |
| `county-drilldown-dormant` | `docs/ROADMAP.md` — § Dormant, and declared so | `tests/test_county_drilldown_dormant.py::test_no_county_module_is_reachable_from_a_pipeline_entry_point` |
