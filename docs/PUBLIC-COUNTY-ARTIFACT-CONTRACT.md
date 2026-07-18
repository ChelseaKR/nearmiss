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

The immutable county index and count-free correction-ledger contracts are now
implemented, including canonical paths, byte/digest pins, detached-boundary
rejection, retained-revision verification, and adversarial release tests. Before
any state shard can be put in the client allowlist, a release must still add an
approved publication policy, reviewed real data inputs, a boundary-delivery
decision, site-build approval, and cross-release differencing review. Until
then, the contracts remain tested production boundaries rather than a public
feature.
