# Fail-closed ingestion foundation

The ingestion runner turns one fetched byte payload into an immutable raw snapshot, an immutable
normalized artifact, and an auditable active commit. It is the transaction boundary for future FARS,
BikeMaps, exposure, and local open-data refreshes; it is not itself a downloader or scheduler.

The current filesystem backend requires a POSIX environment (tested on Linux/macOS) with effective
user ownership, Unix permission bits, hard links, atomic same-filesystem rename, file/directory fsync,
and `O_NOFOLLOW` support. Windows and non-POSIX/network filesystems are not supported by this backend.

## Operator contract

For a source ID such as `fars-joined-2024`, a successful attempt writes:

```text
<root>/fars-joined-2024/
  raw/sha256/<raw-sha256>.bin
  normalized/sha256/<normalized-sha256>.bin
  normalized/current.json
  receipts/<attempt-id>.json
```

`normalized/current.json` is the active success receipt and atomic commit marker. It points to the two
immutable artifacts and carries their hashes. The normalized data is the content-addressed `.bin`
file named by that marker; consumers must not treat `current.json` as normalized source data.

The owned root and every directory beneath it are mode `0700`; raw/normalized artifacts, markers,
and receipts are `0400`. A path owned by a different effective user fails closed even when its mode
bits are otherwise private.
Publishing is a separate, explicit aggregation step and must never make this private tree public.

## Python API

```python
from pathlib import Path

from nearmiss.ingestion import run_ingestion

result = run_ingestion(
    root=Path.home() / ".local" / "share" / "nearmiss" / "ingestion",
    source_id="example-source",
    fetch=fetch_bounded_source_bytes,
    normalize=normalize_and_validate_source,
    validate_normalized=reject_suspicious_regression,
    max_raw_bytes=256 * 1024 * 1024,
    max_normalized_bytes=128 * 1024 * 1024,
)

print(result.current_path)       # validated active receipt / commit marker
print(result.normalized_path)    # immutable normalized bytes
print(result.receipt_path)       # immutable attempt history
```

The byte ceilings are post-materialization activation gates. `fetch` and `normalize` must apply their
own streaming or bounded-read controls while acquiring/constructing large payloads. Both callbacks
must return non-empty `bytes`; source-aware validation receives the candidate and prior normalized
bytes before activation.

Do not place the private root under this repository (including `data/real/...`) while using
`nearmiss serve --dir .`. The development server's built-in private-path guard covers `data/raw/`, not
arbitrary operator-selected ingestion roots. Keep the root outside every directory any static server
can read.

## Failure and recovery rules

- A fetch, normalization, validation, preservation, or commit failure leaves the prior active marker
  in place and writes a redacted failure receipt when safe.
- `KeyboardInterrupt` and `SystemExit` are re-raised. The lock is released only when the active marker
  is provably the prior or new valid receipt.
- Before any later attempt can commit, preflight validates the active marker and both artifacts and
  reconciles that marker into immutable receipt history. This preserves the audit chain if an earlier
  process was interrupted after the atomic commit but before its history copy.
- If `.ingestion.lock` remains, stop. Do not delete it based only on age. The state was ambiguous or a
  rollback failed and needs operator inspection.
- Confirm that `normalized/current.json` is a valid success receipt, that its source ID is expected,
  and that both referenced private files hash to the recorded SHA-256 before clearing a stale lock.
- A rollback-failed attempt preserves two distinct audit identities: the still-active success marker
  is reconciled to `receipts/<attempt-id>.json`, while the failure record is
  `receipts/<attempt-id>.failure.json`. Preserve and validate both before clearing the lock. The next
  preflight performs the success-marker reconciliation before accepting new data.
- Never recursively remove a lock directory. Unexpected contents can indicate a different owner or a
  filesystem race and must be preserved for inspection.

No recovery CLI or garbage collector exists yet. Until those land, stale-lock recovery is a manual,
reviewed operator action; automated jobs must fail closed.

## Current limits

- One local filesystem and one writer per source.
- POSIX filesystem semantics only; Windows support requires a separate backend with equivalent commit,
  ownership, link, and durability guarantees.
- Same-user path replacement remains a residual TOCTOU risk; the storage root must be trusted and
  private.
- Directory-fsync durability depends on the host filesystem and mount configuration.
- Content-addressed blobs are retained indefinitely.
- Source identity, expected upstream digest/year, record counts, scheduling, and registry linkage are
  responsibilities of the source-specific orchestration layer.

The architecture decision and trade-offs are recorded in
[ADR 0007](adr/0007-content-addressed-fail-closed-ingestion.md).

## Source integrations: local FARS

`nearmiss ingest-fars` is the first source-specific consumer of this transaction. It reads a bounded
local NHTSA FARS CSV/ZIP, validates a deterministic private outcome artifact, and uses source ID `fars`.
See [REAL-DATA.md](REAL-DATA.md#official-outcomes--national-context-not-an-intake-source) for the
operator command and source-specific limits. It does not perform network acquisition, scheduling,
publication, mode inference, or segment comparison.

`nearmiss ingest-fars-year` is the additive, exact annual accident/person path. It requires a local
raw archive, private root, registered year, and exact append-only contract revision. The registered
contract—not CLI policy flags—fixes the official archive size/hash, source and release identity,
table encodings, mapping versions, row bounds, and reviewed regression policy. The command activates
independent `fars-joined-<year>` lineages (currently 2020–2024), replays the full raw archive before
returning success, and emits aggregate verification evidence only. It still performs no download,
scheduling, segment/time comparison, or publication.

Invoke that command from within a recognizable nearmiss source checkout or assembled public-site
tree. The CLI binds the private-root preflight to that real invocation boundary and, for an editable
install, to the source checkout as well. It deliberately fails closed when a wheel/pipx installation
is invoked outside either tree: the Python installation prefix is not evidence of what an operator
might serve. This check prevents placement under the active nearmiss tree; as documented in the
threat model, operators must separately keep the root outside any unrelated static-server tree.

`nearmiss coverage --fars-root ROOT` is a separate, read-only consumer. It fails closed unless the
legacy source-ID-`fars` active marker matches immutable history, every content hash and artifact
contract holds, and replaying the preserved raw export produces the exact stored normalized bytes. A
matching source-registry row with `id = "fars"` and `kind = "official_outcomes"` is also required
before coverage reports `verified_official_outcomes`. It does not yet consume the independent annual
lineages. Verification performs no repair or permission change and never grants triangulation, tier
promotion, or publication.
