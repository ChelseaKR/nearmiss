# 13. Keep the Python 3.11 floor (portfolio-standard exception)

- Status: Accepted
- Date: 2026-07-16
- Deciders: Chelsea Kelly-Reif (maintainer)
- Tags: tooling, compatibility, standards

## Context

The portfolio CODE-QUALITY standard sets `requires-python = ">=3.12"` as the default floor for
Python repositories, with a documented-exception path for repositories that have a real reason to
support 3.11 while it remains on its upstream security-support track (until October 2027).

`nearmiss` declares `requires-python = ">=3.11"` in `pyproject.toml`, and that floor is not an
accident of history — it is load-bearing in several committed artifacts:

- **A stated portability property.** `pyproject.toml` documents that the geometry and statistics
  are pure, typed standard-library Python, so "the analysis runs anywhere Python 3.11+ runs, with
  no native/geospatial build step." Advocates and reviewers reproducing the analysis on a stable
  Linux distribution get a working toolchain from the system Python — Debian 12 (bookworm), still
  in mainstream support, ships Python 3.11.
- **A tested commitment, not an aspiration.** The CI `test` matrix runs the full suite on both
  3.11 and 3.12 (`.github/workflows/ci.yml`), and `docs/ROADMAP.md` carries "100% green on 3.11
  and 3.12" as an AUTO-tracked metric. The trove classifiers, `README.md` ("Requires **Python
  3.11+**"), and `CONTRIBUTING.md` all state the same floor.
- **Reproducibility is a hard rule (HR5).** Narrowing the runtime floor shrinks the set of
  environments in which `make reproduce` works. That is a compatibility-breaking change for
  downstream users and should be made deliberately — with a matrix change, a classifier change,
  a docs change, and a CHANGELOG entry — not as a side effect of a standards sweep.

The development default is already 3.12 (`.python-version`), and every single-version CI job pins
3.12, so the project gains 3.12's toolchain benefits today without dropping 3.11 users.

## Decision

`nearmiss` keeps

```toml
requires-python = ">=3.11"
```

in `pyproject.toml` as an accepted exception to the portfolio's 3.12 default floor, for as long as
Python 3.11 remains within upstream security support and the CI matrix keeps the 3.11 leg green.

The floor is revisited — as its own ADR superseding this one — when any of the following happens:

- Python 3.11 reaches upstream end-of-life (scheduled October 2027);
- a dependency or language feature the project actually needs requires 3.12+;
- the CI 3.11 matrix leg is removed or stops being merge-blocking.

## Consequences

- The published package remains installable on Debian-12-class system Pythons with no additional
  interpreter install, preserving the "runs anywhere Python 3.11+ runs" property that the README,
  CONTRIBUTING, and ROADMAP already promise.
- The project keeps paying the (small) cost of the dual 3.11/3.12 CI matrix leg and must avoid
  3.12-only syntax and stdlib APIs in `src/` until this ADR is superseded.
- The portfolio conformance checker records this file as the accepted 3.11 exception rather than
  flagging `requires_python_floor` as a silent violation.
