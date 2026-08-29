# Standards and metrics ledger

Last measured: 2026-08-22 · Owner: Chelsea Kelly-Reif · Review cadence: per
release and quarterly.

Feature and research hypotheses live in [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md)
and the README's [Roadmap](../README.md#roadmap). This file is the enforcement
ledger required by the portfolio Quality & Metrics standard. A row is an
AUTO-GATE, a concrete REVIEW-GATE with an evidence artifact, or an explicit
N/A-with-reason—never an unowned aspiration.

## Metrics

| Metric | Target | Measured by | Gate | Owner |
|---|---|---|---|---|
| Branch coverage | ≥ 90.00% | `make test`; pytest-cov plus independent `coverage report --precision=2` | AUTO | Maintainer |
| Python tests | 100% green on 3.11 and 3.12 | CI `test` matrix over synthetic/known-answer fixtures | AUTO | Maintainer |
| Lint / format / types | 0 errors | `make lint`; `make type` (`mypy --strict`) | AUTO | Maintainer |
| Published-data privacy | 0 denylisted fields; no raw/pending data in public artifacts | privacy/moderation tests plus Pages artifact allowlist | AUTO | Maintainer |
| Reproducibility | Byte-for-byte clean published-data diff | CI `reproducibility`; `make reproduce` | AUTO | Maintainer |
| Five hard rules | Every published dataset passes HR1–HR5 | `make conformance` | AUTO | Maintainer |
| Documentation claim parity | 100% tagged claims have manifest entries and executable witnesses | `make claims` | AUTO | Maintainer |
| Dependency vulnerabilities | 0 known vulnerable packages in the hashed merge-gate lock | `pip-audit --strict --require-hashes` | AUTO | Maintainer |
| SHA-pinned workflow actions | 100% | zizmor + CodeQL Actions + OpenSSF Scorecard | AUTO | Maintainer |
| Automated accessibility | 0 axe violations; all structural/contract/RTL checks green | `make web-check` and `make accessibility` | AUTO | Maintainer |
| EN/ES catalog parity | 100% keys and placeholders; catalogs compile | `make i18n` | AUTO | Maintainer |
| Server log privacy / health | Blocked paths redacted; liveness 200; readiness fails closed | `tests/test_observability.py`, `tests/test_server.py` | AUTO | Maintainer |
| City-scale performance | Recheck the committed 300/6,000 and 800/20,000 baselines; investigate >10% regression | `make bench`; [`PERFORMANCE.md`](PERFORMANCE.md) | REVIEW | Maintainer |
| Screen-reader walkthrough | Dated NVDA and VoiceOver evidence per stable release; provisional owner-attested evidence permitted for a bounded solo-maintainer public preview | [`accessibility/ACR.md`](accessibility/ACR.md) manual-test rows; [`ADR 0012`](adr/0012-solo-maintainer-provisional-review-attestation.md) | REVIEW | Maintainer / human reviewer |
| Threat model / DPIA | Review on every new collection, publication, or network surface | [`THREAT-MODEL.md`](THREAT-MODEL.md), [`DPIA.md`](DPIA.md) | REVIEW | Maintainer |
| Statistical validity | Method changes carry known-answer/differential evidence; external-validity claims require specialist review | [`METHODOLOGY.md`](METHODOLOGY.md), preregistration sign-off | REVIEW | Statistician / maintainer |
| AI evaluation / GenAI telemetry | N/A—deterministic statistics and rules only; no model, prompt, retrieval, embedding, or AI ranking path | ADR 0004 plus dependency/import scan | N/A | Maintainer |
| Change-fail rate (release pipeline) | Track and drive down; no fixed numeric target at this release cadence | `gh run list --workflow=release.yml` cross-referenced with `gh release list` — see Delivery health below for the definition and the record | REVIEW | Maintainer |
| Failed-deployment recovery time | Track and drive down; no fixed numeric target at this release cadence | same | REVIEW | Maintainer |
| Deployment rework | Track and drive down; no fixed numeric target at this release cadence | same | REVIEW | Maintainer |

## Delivery health

Portfolio automation measures delivery/quality-debt metrics from Git and CI.
For this library/static-site repo, deployment frequency and change lead time are
the applicable DORA signals, tracked by that automation. Change-fail rate,
failed-deployment recovery time, and deployment rework become meaningful only
after a tagged release or Pages deployment incident exists; they were carried
as N/A rather than filled with invented zeroes until that precondition was
met, on 2026-08-08.

**Definitions, since none of the three metrics has one obvious reading for a
tag-triggered release pipeline (issue #184):** a *deployment* is one
`release.yml` run triggered by pushing a version tag. A deployment *fails* if
either of its two jobs (build/verify/SBOM/sign/attest/GitHub-Release, then
publish-to-PyPI) does not complete successfully — a signed GitHub Release
with no PyPI publish still counts as a failed deployment, because the release
was not fully shipped. *Recovery* is the next deployment that completes the
same intended release; where no such deployment exists, that is recorded as
unrecovered rather than averaged away. *Rework* is any deployment that needed
a second attempt, on the same tag or a superseding one, to ship completely.

**The record, verified against `gh run list --workflow=release.yml` and `gh
release list` directly (not retyped from a prior summary):** four tags have
shipped — v0.2.0, v0.3.0, v0.3.1 (2026-08-08), and v0.4.0 (2026-08-16) —
across **five** `release.yml` runs, not the three tags / four runs an earlier
revision of this section reported before v0.4.0 shipped.

| Tag | Runs | Outcome |
|---|---|---|
| v0.2.0 | 1 | Build/sign/GitHub-Release job succeeded; PyPI publish **failed** (the name `nearmiss` was taken). Not retried on this tag — see below. |
| v0.3.0 | 1 | Both jobs succeeded on the first run. |
| v0.3.1 | 2 | First run **failed** the build job's clean-environment wheel smoke test before signing, so no release was cut and PyPI publish was correctly skipped. Tag moved to `976cf5e`; the retry, started 2026-08-08T23:25:10Z, ~16 minutes after the failed run started (2026-08-08T23:08:56Z) and ~7 minutes after it finished, succeeded fully. |
| v0.4.0 | 1 | Both jobs succeeded on the first run. |

**Computed:**

- **Change-fail rate: 2 of 5 deployments (40%).** v0.2.0's PyPI leg and
  v0.3.1's first attempt.
- **Deployment rework: 2 of 5 deployments, on 2 of 4 tags (50% of tags
  shipped so far needed rework).**
- **Failed-deployment recovery time: the two failures are not the same kind
  of event, and averaging them would misstate both.** v0.3.1 recovered on
  its own tag in ~16 minutes (push-to-push) / ~7 minutes (failure-end to
  retry-start). v0.2.0 **never recovered on its own tag** — the PyPI leg for
  the name `nearmiss` was abandoned rather than retried; the underlying
  problem (the name was taken) was instead fixed by publishing under the
  renamed package `nearmiss-safety`, first shipped with v0.3.0 about 1h15m
  later (`aea68e3`). Two data points are too few for a stable average in any
  case; both are reported so a reader can see which kind of recovery — a
  same-tag retry, or a later release superseding the failure — actually
  happened each time.

These are now measured rows, not an aspiration. Re-measure after the next
release and update this section rather than letting it go stale again — the
"three tags" figure this section carried through 2026-08-16 is exactly the
failure mode this paragraph exists to prevent, arriving from the other side.

## Open review and owner actions

- Complete and commit actual NVDA/VoiceOver evidence; an automated agent cannot
  perform or sign a human assistive-technology walkthrough. ADR 0012's provisional
  public-preview disposition records owner-accepted residual risk but does not close
  this work or change any **Not performed** row.
- Approve the preregistered scoring rule with a real statistician after the
  evaluation window; fixture success is not predictive-validity evidence.
- Mint a DOI (Zenodo or equivalent) against a shipped tag and fill in
  `CITATION.cff`'s `doi:` field — the marker now carries this issue's
  reference (`TODO(#184)`, satisfying CQ-34's no-bare-marker gate) but the DOI
  itself is not yet minted. PyPI Trusted Publishing and the signed tag
  workflow are done: `nearmiss-safety` 0.3.0, 0.3.1, and 0.4.0 are published,
  and v0.2.0, v0.3.0, v0.3.1, and v0.4.0 each cut a signed GitHub Release with
  an SBOM and a SLSA attestation (2026-08-08 and 2026-08-16).
- Provide real exposure counts and official-collision validation where the
  research roadmap explicitly requires external data.

These are review/account/data gates, not missing deterministic implementation.
They stay visible here and in their owning artifacts until the named evidence
exists.

## Dormant, and declared so

Built, tested, contracted, and reachable from nothing. Recorded here rather than left in
the third state a reader cannot classify — not a stub, not shipped, not declared. Issue
#182.

<!-- claim:county-drilldown-dormant -->
The **county drill-down** — seven modules under `src/nearmiss/`
(`fars_county_public_index`, `fars_county_publication`, `fars_county_feasibility`,
`fars_county_projection`, `fars_county_boundary_publication`, `fars_county_crosswalk`,
`fars_county_crosswalk_review`), three build tools
(`tools/build_fars_county_crosswalk.py`, `tools/build_fars_county_public_index.py`,
`tools/build_us_county_boundaries.py`), eight test modules, three published contract
documents and ADR 0014 — is **planned and not yet in service**. No `make` target, no CI
job, and no entry in `tools/build_site.py`'s published-file allowlist reaches any of it,
and `data/published/` holds no county artifact. The published FARS layer is 51
state-level jurisdictions across 2020-2024; counties: zero.

The blocker is a human step, not missing code:
[`docs/PRIVATE-COUNTY-CROSSWALK-REVIEW.md`](PRIVATE-COUNTY-CROSSWALK-REVIEW.md) requires
a reviewer to clear every `pending-review` row by hand, and an unresolved row blocks
county projection.
[`docs/COUNTY-DRILLDOWN-IMPLEMENTATION-PLAN.md`](COUNTY-DRILLDOWN-IMPLEMENTATION-PLAN.md)
names Virginia as the first pilot and says it "must pass before any public claim of
nationwide geographic coverage". No pilot has produced an artifact, so no such claim is
made anywhere.

Nothing is deleted and nothing is promised. `make verify` still lints, type-checks and
tests all of it, which is the maintenance cost this declaration makes visible rather than
removes. Every module and tool above carries a `DORMANT:` paragraph in its own docstring,
and `tests/test_county_drilldown_dormant.py` fails if any of them becomes reachable from
a pipeline entry point — so this claim cannot quietly outlive the state it describes.
<!-- /claim:county-drilldown-dormant -->
