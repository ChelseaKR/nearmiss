# Infra — public static site plus optional scale-to-zero intake

nearmiss is designed so an advocacy group with no budget can still run it. The intake can run as a
**stateless, scale-to-zero serverless** function, and the published site is **static-friendly**, so
there is no always-on component to keep paid.

What lives here (the analysis still runs entirely offline without any of it):

- [`aws-static-site.yml`](aws-static-site.yml) provisions the canonical
  `nearmiss.chelseakr.com` origin: a private, versioned S3 bucket, CloudFront with OAC and TLS,
  Route 53 A/AAAA aliases, directory-route rewriting, security headers, and a narrowly scoped
  GitHub OIDC deployment role. The `production` GitHub environment can publish only the exact
  artifact assembled by the dependency-gated `build-pages` job; no static AWS key is stored.
  The legacy `nearmiss.report` GitHub Pages origin stays live during migration.
  First deployment uses `PublishDns=false`; after the reviewed artifact is present at the private
  origin, update the same stack with `PublishDns=true` to expose the Route 53 A and AAAA aliases.
  Deploy this stack in **`us-east-1`**: CloudFront accepts ACM certificates only from that region.
  The `production` environment is configured with an exact `main` branch policy, and administrators
  cannot bypass that deployment restriction. The OIDC subject
  `repo:ChelseaKR/nearmiss:environment:production` is therefore a main-only deployment identity.
  The deploy job downloads the reviewed artifact, checks out the exact source into a separate
  directory, rebuilds with `python -S`, and byte-compares both trees **before** requesting its OIDC
  token. The Pages-only `.nojekyll` and `CNAME` controls are excluded and deleted from the canonical
  origin. A failed transfer or non-deterministic build therefore cannot mutate the origin.

- Pull requests exercise the exact `build-pages` assembly and both artifact-upload paths. On `main`,
  dependency-gated deploy jobs publish that one reviewed artifact to GitHub Pages and the canonical
  CloudFront origin only after the full CI is green.
  `tools/build_site.py` allowlists `web/` and `data/published/`, rejects symlinks and path-resolution
  escapes, and excludes private/raw and repository-internal files. The artifact exposes
  `/deployment.json` and `/site-manifest.json`; the manifest hashes every payload file (the manifest
  envelope itself is the sole exception), and the workflow verifies the deployed commit and critical
  data/UI paths before reporting success. The least-privilege job boundary is recorded in
  [ADR 0005](../docs/adr/0005-build-pages-artifact-before-deployment.md).

- A serverless **intake** deploy (validate against the report schema, rate-limit to resist spam and
  poisoning, write to the private raw store).
- A **scheduled rebuild** that re-runs the pipeline and republishes the open dataset, keeping it
  current (timeliness), with rebuild latency budgeted in CI.
- A **container image** and one-command deploy for self-hosting.

Cost target: near zero, with a budget alarm. Secrets are provided via the environment and never
committed — see [`SECURITY.md`](../SECURITY.md).

## Rollback

Re-run the deploy workflow for a known-good commit after reverting `main` to that content through a
normal reviewed PR. Do not rewrite published data in place: the deployment stamp and manifest must
continue to identify the exact commit that produced the live artifact.

The CloudFront bucket is versioned. An emergency rollback still rebuilds a known-good reviewed
commit, syncs that exact artifact, invalidates the distribution, and reruns the live verifier; do not
restore a loose subset of old S3 object versions because that would break the manifest envelope.
The workflow intentionally reports a failed post-publication verification rather than automatically
rolling back on a possibly transient edge failure, so the bounded verifier and this exact-artifact
rollback procedure are both part of the operator response.
