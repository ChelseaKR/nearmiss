# 8. Normalize local FARS exports into private verified artifacts

Date: 2026-07-12

## Status

Accepted

## Deciders

nearmiss maintainers

## Context

The FARS adapter can parse official crash tables and the ingestion engine can preserve arbitrary byte
transforms, but neither alone defines an operator-ready national outcome input. A usable boundary must
bind the exact source bytes to a deterministic normalized batch, reject semantically truncated or
poisoned candidates, and remain separate from contributor reports and public segment datasets.

Live acquisition adds a different trust problem: NHTSA does not provide a project-controlled signed
manifest, and a URL string is not proof of where local bytes came from. Combining download and
activation in this slice would make acquisition failures harder to distinguish from mapping failures.

## Decision

Add `nearmiss ingest-fars` for a local CSV or official nested ZIP already acquired by the operator.

- Bound the local read before allocation and preserve exactly those bytes under their SHA-256.
- Require an expected FARS year, operator-supplied release label, exact static NHTSA distribution URL
  shape, and maximum invalid-row fraction.
- Normalize to a canonical, timestamp-free `official-outcome-artifact` containing the mapping version,
  source-byte hash, complete provenance/accounting and deterministic crash identities.
- Reject non-finite coordinates, malformed or duplicate identities, year mismatch, excessive
  rejections, suspicious accepted-record regression and rollback to an older year against the active
  artifact. Record-count and year regressions can proceed only with distinct explicit operator
  acknowledgements recorded in the normalized artifact.
- Activate only through the content-addressed ingestion transaction. Keep raw exports, normalized
  outcomes, active markers and receipts private and outside every served directory.
- Print only hashes, aggregate counts, policy metadata and root-relative private paths; never print
  outcome coordinates.

## Consequences

- An operator can turn a nationwide official export into a reproducible private artifact with a full
  raw→normalized→receipt hash chain using one command.
- Identical bytes and policy produce identical normalized bytes; attempt receipts remain distinct.
- The stored distribution URL and release label are operator assertions bound into the artifact, not a
  cryptographic NHTSA attestation.
- The artifact remains fatal-crash context only. It cannot identify cyclist/pedestrian involvement
  without `person.csv`, and it grants no coverage or triangulation capability by itself.
- Network download, expected digest manifests, scheduling, recovery tooling, segment linkage and public
  aggregate comparisons remain later decisions.

## Alternatives considered

- **Download and activate in one command.** Rejected for this slice because acquisition authenticity,
  retry policy and network secret handling need an independently reviewable boundary.
- **Write a loose JSON list of outcomes.** Rejected because it would omit mapping version, source hash,
  rejection policy and complete accounting needed to reproduce or audit the batch.
- **Register FARS as contributor incidents.** Rejected by ADR 0006: official fatal outcomes and
  community near-miss reports have different semantics and must remain separate evidence streams.
