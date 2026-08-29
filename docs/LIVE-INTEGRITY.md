# Live integrity sentinel

The public site is checked every day and on demand by
`.github/workflows/live-integrity.yml`. The job has read-only repository permission, checks out the
current `main` commit, rebuilds the allowlisted static-site artifact with Python site packages
disabled, and compares the canonical CloudFront production origin at
[nearmiss.chelseakr.com](https://nearmiss.chelseakr.com) with that exact build.

The sentinel verifies:

- the deployment and site-manifest source commit;
- the apex, the `/fars/national/` directory route, and every remotely retrievable manifest file,
  byte for byte and by SHA-256;
- every annual FARS artifact declared by the canonical release index;
- English and Spanish year-specific share URLs; and
- representative private, source, fixture, debug, run-manifest, and retired synthetic-product paths
  still return HTTP 404.

Responses are size- and time-bounded, compression and redirects are not accepted, the production
origin is fixed in code, and bounded retries cover normal CloudFront edge convergence. The production
deployment waits for its wildcard CloudFront invalidation to complete before it runs this same exact
verification. The cache policy keys only the verifier's `verify` query nonce; application filters do
not multiply otherwise identical static objects. The sentinel never shares the deployment concurrency
group: a read must not block or replace a queued production deploy. If `main` moves while a check is
running, the job emits a warning and yields so it can be rerun against one unambiguous deployed
commit. It reports private-path and retired-surface probe counts separately.

The shared artifact keeps `.nojekyll` and `CNAME` hash-bound for the legacy GitHub Pages mirror. The
CloudFront deployment explicitly excludes and deletes both host-control objects from its private S3
origin, while the live sentinel requires their canonical public URLs to return the reviewed 404
document.

## Gated is not the same as published

Several merge-blocking gates exercise surfaces this origin does not serve, and that is
deliberate rather than drift — recorded here because issue #156 showed a reader can only
find it by reading the deploy allowlist. `web/contract_check.mjs` (run by `npm run
contract` on every PR) boots `web/davis-demo.html`, `web/app.js`, `web/embed.html` and
`data/published/davis.geojson`; `tools/a11y_check.py` and `npm run axe` cover
`web/davis-demo.html`, `web/submit.html` and `web/embed.html`; `make serve` opens the
Davis methods UI. None of those files appears in `PUBLIC_WEB_FILES`
(`tools/build_site.py`), so none is deployed, and this sentinel asserts the opposite:
`RETIRED_PUBLIC_PATH_PROBES` (`src/nearmiss/live_site_verifier.py`) requires
`/web/davis-demo.html`, `/web/app.js`, `/web/submit.html`,
`/data/published/davis.geojson` and `/data/published/riverside.geojson` to return the
reviewed 404.

They are kept as **local, synthetic test surfaces**: the consumer contract, the
schema-fidelity checks and the accessibility floor are what a fork standing up its own
city inherits, and retiring the gates with the deployment would retire that guarantee
too. The rule for reading this repository is therefore: a gate covering a file is
evidence the file still has a contract, never evidence the origin serves it. What the
origin serves is exactly `site-manifest.json`, and this sentinel is what proves it.

The deployed locale catalogs are narrowed the same way: `_write_national_locales` in
`tools/build_site.py` publishes only the `web.coverage.*` subset, so the 112 `web.app.*`
keys that describe the retired demo UI are gated for parity and completeness but never
shipped to a browser.

## Run it on demand

Open **Actions → live integrity sentinel → Run workflow** on `main`. A successful run prints one JSON
line with the source SHA, public file and byte counts, default FARS year/source revision, and separate
private-path and retired-surface probe counts. It does not download or inspect private ingestion
storage and needs no secret.

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
