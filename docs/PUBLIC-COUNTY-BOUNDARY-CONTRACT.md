# Public county boundary contract

County geometry has its own public artifact boundary. A public state shard is
derived from one reviewed private Census county-equivalent shard, then retains
only public Census provenance, state identity, feature geometry, reviewed county
names, and verified feature accounting.

The public envelope never preserves the private artifact type, visibility,
paths, or digest. It has no FARS counts, FARS county codes, crosswalk rows,
case identifiers, or private feasibility/projection metadata.

Each geometry payload is closed, size-bounded, canonical JSON. It rejects
duplicate keys, non-finite numbers, unclosed rings, invalid coordinates,
cross-state GEOIDs, duplicate or unordered features, and inconsistent polygon or
coordinate accounting. A county value shard binds to the digest of this public
geometry artifact—not to private boundary bytes.

This is an implemented release contract only. No public boundary artifact is
currently allowlisted, published, or rendered in the site. A later reviewed
release must add the county value index, correction ledger, exact artifact pins,
and site-build approval before any geometry or county lens becomes public.
