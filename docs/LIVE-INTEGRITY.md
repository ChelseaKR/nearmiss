# Live integrity sentinel

The public site is checked every day and on demand by
`.github/workflows/live-integrity.yml`. The job has read-only repository permission, checks out the
current `main` commit, rebuilds the allowlisted Pages artifact with Python site packages disabled,
and compares production with that exact build.

The sentinel verifies:

- the deployment and site-manifest source commit;
- the apex and every remotely retrievable manifest file, byte for byte and by SHA-256;
- every annual FARS artifact declared by the canonical release index;
- English and Spanish year-specific share URLs; and
- representative private, source, fixture, debug, and run-manifest paths still return HTTP 404.

Responses are size- and time-bounded, compression and redirects are not accepted, the production
origin is fixed in code, and a cache-buster plus bounded retries covers normal GitHub Pages edge-cache
convergence. The sentinel never shares the deployment concurrency group: a read must not block or
replace a queued production deploy. If `main` moves while a check is running, the job emits a warning
and yields so it can be rerun against one unambiguous deployed commit.

GitHub Pages consumes `.nojekyll` as a hosting control and does not serve it. It remains hash-bound in
the local deployment manifest, while the live sentinel requires its public URL to stay 404.

## Run it on demand

Open **Actions → live integrity sentinel → Run workflow** on `main`. A successful run prints one JSON
line with the source SHA, public file and byte counts, default FARS year/source revision, and negative
probe count. It does not download or inspect private ingestion storage and needs no secret.

## Respond to a failure

1. Confirm whether `main` or a Pages deployment moved during the run; rerun once if the error says it
   did.
2. Compare `deployment.json` and `site-manifest.json` with the current `main` SHA.
3. Treat any negative privacy response that differs from the guaranteed-missing 404 baseline as a
   security incident. Do not work around it
   by weakening the probe.
4. For a byte or manifest mismatch, inspect the last Pages deployment. Restore service by reverting
   the offending `main` commit through a reviewed pull request or redeploying the last known-good
   workflow artifact, then require the sentinel and the deploy smoke check to pass.

This is an integrity, availability, and privacy-denial check—not traffic analytics, third-party
alerting, a full browser monitor, or proof that the underlying data is current. The summary reports
freshness metadata so a human can assess it without converting age into an unsupported claim.
