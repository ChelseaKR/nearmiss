# 9. Separate source declaration, lineage verification and triangulation

Date: 2026-07-12

## Status

Accepted

## Deciders

nearmiss maintainers

## Context

The source registry describes what an operator intends to use. It is reviewable metadata, but it does
not prove that source bytes exist or passed a source-specific contract. The original coverage logic
nevertheless granted `official_outcome_triangulation` whenever a registry row declared
`kind = "official_outcomes"`.

The local FARS ingestion workflow now preserves enough information to prove a narrower fact: an active
private crash-level artifact can be traced to immutable raw bytes and reproduced by the current mapping.
That still does not identify cyclist or pedestrian involvement or connect a crash to a city street
segment and analysis window.

## Decision

Represent four distinct trust states:

1. **Declared** — a source-registry row exists.
2. **Chain verified** — the active receipt, immutable history, raw and normalized hashes, artifact
   contract and deterministic normalization replay agree.
3. **Crash context ready** — verified FARS crash-level outcomes are available as private context.
4. **Triangulation ready** — a separately verified person-mode join and segment/time linkage exist.

`nearmiss coverage --fars-root ROOT` may establish states 2 and 3. It must use a read-only, bounded,
POSIX no-follow verifier, fail if an ingestion lock or ambiguous history exists, and emit only safe
aggregate lineage metadata. A matching registry row with `id = "fars"` and
`kind = "official_outcomes"` is also required before the capability
`verified_official_outcomes` appears.

Neither a declaration nor a verified crash table grants `official_outcome_triangulation`. Verified
official outcomes do not enter contributor incident counts, exposure calculations, evidence-tier
promotion, or the public artifact.

## Consequences

- Coverage no longer turns operator-authored TOML into an analytical claim.
- A local verifier proves receipt and artifact integrity plus deterministic raw-to-normalized
  derivation without repairing or publishing the private store.
- Registry-only, verified-only, and matched states remain distinguishable in machine-readable output.
- Verification proves local consistency under the current adapter. It does not prove that NHTSA signed
  or supplied the asserted bytes, and it does not by itself assess dataset-year freshness.
- Person-table mode attribution, segment/time linkage, comparative methodology and privacy review
  remain explicit later gates.

## Alternatives considered

- **Trust the registry declaration.** Rejected because a declaration contains no evidence bytes or
  audit chain.
- **Trust matching hashes without replay.** Rejected because a self-consistent artifact could still
  contain outcomes not derived from the preserved raw export.
- **Call verified crashes triangulation.** Rejected because crash rows alone lack involved road-user
  mode and city analysis linkage.
- **Silently continue when an explicitly supplied private root fails verification.** Rejected because
  a successful downgraded report could hide tampering or operator error.
