# Live integrity sentinel

The public site is checked every day and on demand by
`.github/workflows/live-integrity.yml`. The job has read-only repository permission, checks out the
current `main` commit, rebuilds the allowlisted static-site artifact with Python site packages
disabled, and compares the canonical CloudFront production origin with that exact build.

The sentinel verifies:

- the deployment and site-manifest source commit;
- the apex, the `/fars/national/` directory route, and every remotely retrievable manifest file,
  byte for byte and by SHA-256;
- every annual FARS artifact declared by the canonical release index;
- English and Spanish year-specific share URLs; and
- representative private, source, fixture, debug, and run-manifest paths still return HTTP 404.

Responses are size- and time-bounded, compression and redirects are not accepted, the production
origin is fixed in code, and bounded retries cover normal CloudFront edge convergence. The production
deployment waits for its wildcard CloudFront invalidation to complete before it runs this same exact
verification. The cache policy keys only the verifier's `verify` query nonce; application filters do
not multiply otherwise identical static objects. The sentinel never shares the deployment concurrency
group: a read must not block or replace a queued production deploy. If `main` moves while a check is
running, the job emits a warning and yields so it can be rerun against one unambiguous deployed
commit.

The shared artifact keeps `.nojekyll` and `CNAME` hash-bound for the legacy GitHub Pages mirror. The
CloudFront deployment explicitly excludes and deletes both host-control objects from its private S3
origin, while the live sentinel requires their canonical public URLs to return the reviewed 404
document.

## Run it on demand

Open **Actions → live integrity sentinel → Run workflow** on `main`. A successful run prints one JSON
line with the source SHA, public file and byte counts, default FARS year/source revision, and negative
probe count. It does not download or inspect private ingestion storage and needs no secret.

## Respond to a failure

1. Confirm whether `main` or the `deploy-cloudfront` production deployment moved during the run;
   rerun once if the error says it did.
2. Compare `deployment.json` and `site-manifest.json` with the current `main` SHA.
3. Treat any negative privacy response that differs from the guaranteed-missing 404 baseline as a
   security incident. Do not work around it
   by weakening the probe.
4. For a byte, manifest, header, or routing mismatch, inspect the last `deploy-cloudfront` job, its S3
   sync, and its completed CloudFront invalidation. Restore service by reverting the offending `main`
   commit through a reviewed pull request and deploying that exact rebuilt artifact. A retained
   known-good workflow artifact may be used for immediate emergency service restoration, but `main`
   must then be reverted to the same source commit so the deployment record and recurring sentinel
   agree. Require both the deploy verifier and the sentinel to pass.

This is an integrity, availability, and privacy-denial check—not traffic analytics, third-party
alerting, a full browser monitor, or proof that the underlying data is current. The summary reports
freshness metadata so a human can assess it without converting age into an unsupported claim.
