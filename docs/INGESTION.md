# Fail-closed ingestion foundation

The ingestion runner turns one fetched byte payload into an immutable raw snapshot, an immutable
normalized artifact, and an auditable active commit. It is the transaction boundary for future FARS,
BikeMaps, exposure, and local open-data refreshes; it is not itself a downloader or scheduler.

## Operator contract

For a source ID such as `fars-2024`, a successful attempt writes:

```text
<root>/fars-2024/
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
    root=Path("data/real/ingestion"),
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
- Never recursively remove a lock directory. Unexpected contents can indicate a different owner or a
  filesystem race and must be preserved for inspection.

No recovery CLI or garbage collector exists yet. Until those land, stale-lock recovery is a manual,
reviewed operator action; automated jobs must fail closed.

## Current limits

- One local filesystem and one writer per source.
- Same-user path replacement remains a residual TOCTOU risk; the storage root must be trusted and
  private.
- Directory-fsync durability depends on the host filesystem and mount configuration.
- Content-addressed blobs are retained indefinitely.
- Source identity, expected upstream digest/year, record counts, scheduling, and registry linkage are
  responsibilities of the source-specific orchestration layer.

The architecture decision and trade-offs are recorded in
[ADR 0007](adr/0007-content-addressed-fail-closed-ingestion.md).
