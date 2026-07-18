# Public county release-index contract

The county release index is the only future client allowlist for county context.
It is implemented and tested, but no county index, correction ledger, boundary,
or value shard is currently placed in `data/published/`, copied by the site
build, or fetched by the browser.

For each approved year and state, the canonical index pins:

- the immutable value-shard path, byte length, digest, and publication revision;
- the public boundary-shard path, byte length, and digest;
- the annual FARS contract revision and semantic-regime identifier;
- the reviewed crosswalk version and digest;
- the effective publication floor; and
- the exact canonical correction-ledger bytes.

Value files must use `fars/<year>/counties/<state-fips>-r<revision>.json`.
Geometry files must use `counties/<state-fips>.json`. Relative paths, duplicate
states, detached geometry digests, source-contract drift, unsupported years, and
unindexed shard files fail closed.

The correction ledger is deliberately count-free. A correction records its
affected year/state, immutable prior and replacement value and boundary pins,
review date, reviewed reason, change scope, and deployment commit. It cannot
claim a value or geometry change without the corresponding pin changing. The
directory verifier requires every current and ledger-retained shard to match its
exact pin and refuses extra county-shard files.

`tools/build_fars_county_public_index.py` is an explicit-input, atomic writer:
it does not discover files. A future approved release must still add reviewed
real artifacts, an approved correction ledger, site-build allowlisting, manifest
coverage, live verification, and the county experience. This contract alone
does not authorize any of those changes.
