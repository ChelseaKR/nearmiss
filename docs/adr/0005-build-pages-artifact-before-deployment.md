# 5. Build the Pages artifact before deployment

Date: 2026-07-12

## Status

Accepted

## Deciders

nearmiss maintainers

## Context

PR #74 introduced an allowlisted GitHub Pages artifact but assembled it inside the push-only
deployment job. Pull requests could test the Python builder, but they did not exercise the exact Pages
packaging boundary. That left two avoidable risks: a candidate change could fail only after merge, and
the job that held the Pages deployment permission also checked out and packaged repository content.
PR #76 separated those responsibilities; this ADR records that decision immediately after the merge.

The repository's documentation standard requires an ADR whenever a workflow `permissions:` block is
touched. Moving packaging into a separate job adds a new explicit permission boundary and therefore
requires this decision record.

## Decision

Build and upload the allowlisted Pages artifact in a dedicated `build-pages` job on pull requests and
pushes. Grant that job only `contents: read`. The push-only `deploy-pages` job depends on the complete
CI gate and consumes the already-built artifact; it retains only the permissions required by GitHub
Pages (`pages: write` and `id-token: write`, plus `contents: read`).

The artifact builder rejects symlinks and path-resolution escapes, and its manifest covers every
payload file except the manifest envelope itself. Deployment smoke tests verify the deployed commit
and critical public paths.

## Consequences

- Pull requests exercise the same artifact assembly and upload path that a main-branch deployment
  consumes.
- Repository checkout and artifact construction run without Pages write or identity-token access.
- The deploy job has a smaller responsibility and cannot silently rebuild different content after
  the rest of CI has passed.
- GitHub's artifact handoff becomes part of the release path; an unavailable or expired artifact
  fails the deployment closed.
- Rollback remains an operator action: redeploy a known-good workflow run or revert the offending
  commit, then verify the deployment stamp and smoke checks.

## Alternatives considered

- **Keep building inside the deploy job.** Rejected because the exact packaging path would remain
  push-only and coupled to elevated deployment permissions.
- **Grant Pages write permissions to the build job.** Rejected because packaging does not deploy and
  does not need that authority.
- **Publish the repository root.** Rejected because repository internals are not public-site assets;
  a narrow allowlist is easier to audit and fails safer.
