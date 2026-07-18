# Public county artifact contract

The county publication contract is implemented, but no county artifact is
published or allowlisted yet.

One public state shard can be derived only from the exact private feasibility
artifact, fully resolved reviewed crosswalk, reconciled private projection, and
matching canonical public Census boundary shard. The public boundary itself can
be derived only from its reviewed private source shard. The value builder rejects
any detached digest, year or source mismatch, crosswalk/boundary identity
mismatch, or county cell without a boundary feature.

Every county has all six involved-mode cells. A cell is either:

- `published`, with a count at or above the configured floor (never below 10);
- `suppressed_or_zero`, with no numeric field at all.

Public accounting contains only county and cell counts. It intentionally omits
state, county, published, suppressed, and non-reported contribution totals, so
subtraction cannot recover a withheld value. The artifact also excludes raw FARS
county codes, case identifiers, private feasibility digests, private projection
digests, and private boundary-shard identity.

Before any state shard can be put in the client allowlist, a release must add an
approved publication policy, an immutable county index and correction record,
reviewed data inputs, a boundary delivery decision, and adversarial differencing
tests across releases. Until then, the contract remains a tested production
boundary rather than a public feature.
