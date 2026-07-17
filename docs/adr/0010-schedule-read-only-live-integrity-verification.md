# 10. Schedule read-only live integrity verification

Date: 2026-07-13

## Status

Accepted

## Deciders

nearmiss maintainers

## Context

The canonical CloudFront deployment verifies the exact source commit, the complete remotely
retrievable artifact, release index, annual artifacts, directory routing, and representative negative
privacy paths immediately after every push to `main`. The legacy Pages deployment separately verifies
its critical runtime surface. Neither check runs again until another deployment. A later hosting,
cache, DNS, or publication-boundary regression could therefore remain undetected, including an
accidentally served repository path that was never part of the allowlisted artifact.

Adding a scheduled workflow creates a new explicit GitHub Actions `permissions:` boundary. The
documentation standard requires this ADR for that change.

## Decision

Run a daily and manually dispatchable live-integrity workflow from the current `main` checkout. Grant
the workflow only `contents: read`; grant no Pages write, identity token, environment, secret, issue,
or notification authority.

The verifier rebuilds the exact allowlisted site with Python site packages disabled, then performs
bounded read-only HTTPS requests to the fixed `nearmiss.chelseakr.com` origin. It requires the live manifest,
deployment record, apex, every remotely retrievable manifest file, annual FARS release pin and
localized share shell to match that exact build. It also requests the public `/fars/national/`
directory route and binds that response to its manifest-listed `fars/national/index.html` bytes. The
manifest-bound `.nojekyll` hosting control and a
fixed negative inventory must continue returning HTTP 404. Redirects,
compression, non-public DNS answers, oversized responses, malformed paths and ambiguous JSON fail
closed.

The sentinel has its own concurrency group, so it cannot block or replace a queued production deploy.
The production job waits for a wildcard CloudFront invalidation before verification, and bounded
retries cover ordinary edge convergence. The CloudFront cache policy keys the verifier's `verify`
query nonce and no other query parameter, so each integrity run gets an independent cache entry
without letting application-filter URLs amplify the cache. If `main` moves during a sentinel run, the
result is reported as a warning and yields to the deployment rather than mislabeling normal
convergence as corruption. Otherwise a stable mismatch fails the workflow.

## Consequences

- Production integrity and representative privacy-denial paths are checked even when no code changes.
- The check has no authority to repair, redeploy, open an issue, or inspect private ingestion storage.
- GitHub Actions provides retention and notification for a failed run; third-party alerting and real
  browser monitoring remain separate future work.
- Daily public reads add negligible traffic but depend on GitHub Actions, Route 53, CloudFront, and the
  private S3 origin being available. A platform outage can make the sentinel red without changing
  repository bytes.
- A main push that races the read remains free to deploy; the sentinel either converges during its
  bounded retries or explicitly classifies a moved ref as a rerun condition.

## Alternatives considered

- **Rely only on the post-deploy smoke check.** Rejected because it cannot detect later drift or
  accidental exposure.
- **Grant write permission and auto-rollback.** Rejected because observation does not need mutation
  authority, and an automated rollback could amplify a transient cache or platform failure.
- **Use an external monitoring vendor.** Deferred because it adds credentials, data processing and
  operational authority that are unnecessary for this first integrity sentinel.
- **Probe with shell `curl` only.** Rejected because a testable bounded verifier gives path, JSON,
  byte-budget, redirect and negative-inventory checks one reusable contract.
