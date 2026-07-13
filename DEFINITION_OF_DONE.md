# Definition of Done — nearmiss

Last reviewed: 2026-07-12. Recheck quarterly and whenever a gate, release
surface, or standards-applicability decision changes.

This instantiates the portfolio Quality & Metrics standard for nearmiss: a
typed Python library/CLI, deterministic data pipeline, static bilingual web
surface, and optional local read-only server. The project has no AI/LLM/RAG
component. The authoritative target/value ledger is
[`docs/ROADMAP.md`](docs/ROADMAP.md).

## AUTO-GATE

A change is not done until every applicable merge gate is green:

1. `ruff check .` and `ruff format --check .` report zero findings.
2. `mypy --strict` reports zero type errors.
3. The Python 3.11/3.12 test matrix passes with branch coverage at or above
   90%; planted-hotspot, privacy, moderation, and numerical known-answer tests
   remain green.
4. The published artifacts reproduce byte-for-byte and pass the five-hard-rule
   conformance checker; documentation claims remain linked to executable
   witnesses.
5. Dependency, secret, code, and workflow scans pass: blocking `pip-audit`,
   gitleaks, CodeQL, and high-severity zizmor; workflow actions remain SHA
   pinned. The tag workflow generates an SBOM, signature, and provenance.
6. All four authored web pages pass the structural WCAG gate, axe-core,
   consumer-contract checks, and the RTL layout smoke test.
7. EN/ES extraction, catalog/placeholder parity, `msgfmt`, web-catalog parity,
   BCP-47, and pseudolocale checks pass.
8. The public Pages artifact is built from the explicit allowlist and contains
   no private raw or pending-submission data.
9. Structured server logs remain privacy-redacted and `/livez` and `/readyz`
   remain fail-closed where appropriate.

`make verify PYTHON=.venv/bin/python` reproduces the local portions of these
gates. CI additionally runs the hosted CodeQL/gitleaks and Pages jobs.

AI evaluation is **N/A**: no model call, prompt, retrieval, embedding, or AI
ranking path exists. The dated decision and trigger are in
[`docs/adr/0004-standards-applicability.md`](docs/adr/0004-standards-applicability.md).
Adding any such path flips the standard to Applies before that feature can
merge.

## REVIEW-GATE

- The PR states acceptance criteria and the ISO/IEC 25010 characteristic(s)
  changed, and names rollback for schema, data, or deployment changes.
- A new collection, publication, or network surface updates the threat model,
  DPIA, data card, and residual-risk record in the same change.
- A statistical-method change includes a known-answer or differential test and
  does not claim external validity without the documented statistician/real-data
  review.
- A new interactive component receives keyboard and screen-reader review; the
  dated manual NVDA/VoiceOver evidence remains an honest open review gate until
  a human performs it.
- User-visible behavior, methods, schemas, and assumptions update the changelog
  and relevant documentation.

## RELEASE-GATE

Before a version is called released:

- `make verify` and `make reproduce` pass at the exact tag.
- The tag version, `pyproject.toml`, schema version, and changelog agree.
- Performance evidence and the ACR are reviewed for the release.
- The tag workflow builds and re-verifies the sdist/wheel, SBOM, keyless
  signature, and SLSA provenance, and Trusted Publishing completes.

The release workflow exists, but the first signed tag and PyPI Trusted
Publisher setup remain owner actions. Until they occur, this repository is
pre-release beta and must not claim that the release gate has been exercised.

## Ownership and protection

`DEFINITION_OF_DONE.md`, `docs/ROADMAP.md`, workflow files, privacy-critical
publication code, and the report schema are CODEOWNER-routed to `@ChelseaKR`.
Server-side review enforcement is a repository-setting decision; this document
does not imply an approval happened when it did not.
