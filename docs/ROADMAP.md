# Standards and metrics ledger

Last measured: 2026-07-16 · Owner: Chelsea Kelly-Reif · Review cadence: per
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

## Delivery health

Portfolio automation measures delivery/quality-debt metrics from Git and CI.
For this library/static-site repo, deployment frequency and change lead time are
the applicable DORA signals. Change-fail rate, failed-deployment recovery time,
and deployment rework become meaningful only after a tagged release or Pages
deployment incident exists; they must remain N/A rather than be filled with
invented zeroes.

## Open review and owner actions

- Complete and commit actual NVDA/VoiceOver evidence; an automated agent cannot
  perform or sign a human assistive-technology walkthrough. ADR 0012's provisional
  public-preview disposition records owner-accepted residual risk but does not close
  this work or change any **Not performed** row.
- Approve the preregistered scoring rule with a real statistician after the
  evaluation window; fixture success is not predictive-validity evidence.
- Configure PyPI Trusted Publishing and exercise the signed tag workflow for the
  first release.
- Provide real exposure counts and official-collision validation where the
  research roadmap explicitly requires external data.

These are review/account/data gates, not missing deterministic implementation.
They stay visible here and in their owning artifacts until the named evidence
exists.
