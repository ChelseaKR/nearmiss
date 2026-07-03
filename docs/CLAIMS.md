# Claims manifest

Every load-bearing accuracy claim in the prose docs is wrapped in a paired HTML comment
(`<!-- claim:ID --> … <!-- /claim:ID -->`) and listed here with a **witness**: the test or source
file that makes the claim true (or, for a "planned, not yet implemented" claim, the file whose
*absence of* the feature the wording honestly describes).

`tools/check_claims.py` (run by `make claims`, part of `make verify`) enforces the manifest in both
directions:

- every claim ID below appears as a **matched** open/close tag pair in its doc file;
- every witness path exists, and a `path::test_name` witness names a function that exists;
- every `<!-- claim:… -->` tag found in `README.md`, `docs/METHODOLOGY.md`, or `CHANGELOG.md` is
  listed here — a tagged claim missing from this table fails the gate (drift is caught both ways).

The witness is deliberately narrow: it is the thing a reviewer can open to confirm the sentence is
not an overclaim. When a claim says a feature is *planned*, the witness is the file that would house
it, so the gap stays visible instead of drifting back into a promise.

| Claim ID | Doc anchor (file + section) | Witness (test or file) |
| --- | --- | --- |
| `lockfile-committed-hashed` | `README.md` — § Install | `requirements.lock` |
| `obs-intake-only` | `README.md` — § Observability | `src/nearmiss/obs.py` |
| `dataset-schema-prose` | `CHANGELOG.md` — § Scope and conventions | `schema/dataset.schema.md` |
| `rate-union-not-per-type` | `docs/METHODOLOGY.md` — § 1. Notation and the unit of analysis | `src/nearmiss/stats/rates.py` |
| `low-confidence-flagged-not-excluded` | `docs/METHODOLOGY.md` — § 2. From raw reports to counts | `src/nearmiss/stats/__init__.py` |
| `byar-poisson-ci` | `docs/METHODOLOGY.md` — § 5.2 Interval for a single segment's rate | `tests/test_rates.py::test_poisson_ci_contains_point_and_widens_relatively_for_small_n` |
| `wilson-proportions` | `docs/METHODOLOGY.md` — § 5.3 Proportions, when the question is a share | `tests/test_rates.py::test_wilson_ci_bounds` |
| `bh-fdr` | `docs/METHODOLOGY.md` — § 5.5 Multiplicity | `tests/test_fdr.py::test_significant_field_is_fdr_corrected_in_analysis` |
| `gi-on-rate-not-count` | `docs/METHODOLOGY.md` — § 8.2 Getis-Ord Gi\* | `tests/test_hotspot.py::test_getis_ord_flags_the_planted_corridor_cluster` |
| `gi-weights-straightline` | `docs/METHODOLOGY.md` — § 8.2 Getis-Ord Gi\* | `src/nearmiss/stats/getis_ord.py` |
| `coverage-sims-planned` | `docs/METHODOLOGY.md` — § 9.2 Interval checks | `tests/test_rates.py::test_poisson_ci_zero_count` |
