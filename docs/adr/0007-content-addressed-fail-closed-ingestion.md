# 7. Use content-addressed, fail-closed ingestion transactions

Date: 2026-07-12

## Status

Accepted

## Deciders

nearmiss maintainers

## Context

National coverage requires repeatable refreshes from heterogeneous external sources. A fetch can be
truncated, malformed, unexpectedly empty, interrupted during activation, or replaced upstream without
notice. Overwriting one mutable file would destroy the last-known-good input and make it impossible to
prove which source bytes produced an analysis.

Some sources may contain precise incident locations or other non-public material. The generic
ingestion boundary therefore also needs private-by-default filesystem permissions and controlled
failure records that do not copy upstream URLs, tokens, or payload fragments into logs or receipts.

## Decision

Implement a source-agnostic filesystem transaction with injected byte-producing `fetch` and
deterministic `normalize` functions.

- Preserve raw and normalized payloads as owner-only, immutable SHA-256-addressed files.
- Make `normalized/current.json` a validated success receipt, not the normalized payload. Its atomic
  replacement is the commit point and it names both immutable artifacts and their hashes.
- Copy committed success receipts and all failure receipts into an immutable per-attempt history.
  If an interrupt occurs between the commit and history copy, the next preflight validates and archives
  the active marker before permitting another commit.
- Validate the candidate against the previous normalized bytes before committing, so a source adapter
  can reject empty or suspiciously regressed refreshes.
- Serialize receipts against a strict, separately versioned JSON Schema before installation and use
  only controlled failure messages/types.
- Serialize writers with an owner-only per-source directory lock. Release it only when the active
  marker is provably the prior or candidate state; retain ambiguous or failed-rollback state for
  operator recovery.
- When rollback fails, keep the active success marker's historical identity separate from the
  rollback-failure record (`<attempt>.json` versus `<attempt>.failure.json`) so recovery can preserve
  both without an immutable-name collision.
- Default owned directories to `0700` and artifacts, markers, and receipts to `0400`.
- Scope this backend to POSIX filesystems that provide effective-user ownership, Unix modes, hard
  links, atomic same-filesystem rename, and file/directory fsync semantics.

## Consequences

- A crash leaves either the previous valid active receipt or a new self-contained valid receipt; an
  active payload is never represented by an unreceipted mutable file.
- Historical receipts continue to resolve to immutable normalized payloads after later refreshes.
- Source-specific ingestion can add byte/year/digest/count gates without reimplementing transaction
  and redaction behavior.
- Content-addressed blobs accumulate until a reviewed garbage-collection policy exists.
- A hard-killed process can leave a stale lock intentionally. There is no automatic stale-lock expiry;
  an operator must inspect the active marker and artifacts before recovery.
- The current API materializes bytes supplied by callbacks. Producers that acquire large inputs must
  apply their own streaming/bounded-download controls before returning bytes.
- Windows and non-POSIX/network filesystems require a separate backend; this implementation does not
  claim equivalent permission or durability behavior there.

## Alternatives considered

- **Overwrite `current.json` with normalized bytes.** Rejected because activation and provenance would
  be separate operations and historical receipts would point at mutable content.
- **Delete old or stale locks automatically.** Rejected because elapsed time cannot prove the owning
  process is dead or the active marker is consistent.
- **Require a database or object store.** Rejected for the foundation because local atomic rename,
  hard-link installation, hashes, and directory fsync provide a zero-service deployment path. A remote
  backend can implement the same contract later.
