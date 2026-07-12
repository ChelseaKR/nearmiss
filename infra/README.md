# Infra — optional, scale-to-zero

nearmiss is designed so an advocacy group with no budget can still run it. The intake can run as a
**stateless, scale-to-zero serverless** function, and the published site is **static-friendly**, so
there is no always-on component to keep paid.

What lives here (optional — the analysis runs entirely offline without any of it):

- Pull requests exercise the exact `build-pages` assembly and Pages-artifact upload path. On `main`,
  the dependency-gated `deploy-pages` job consumes that artifact only after the full CI is green.
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
