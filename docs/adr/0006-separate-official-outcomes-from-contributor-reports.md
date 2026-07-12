# 6. Separate official outcomes from contributor reports

Date: 2026-07-12

## Status

Accepted

## Deciders

nearmiss maintainers

## Context

nearmiss needs nationwide outcome context to compare community-reported near-miss signals with severe
road-safety outcomes. NHTSA's Fatality Analysis Reporting System (FARS) provides a national census of
qualifying fatal motor-vehicle traffic crashes, but those records are not contributor reports. They
do not have a reporter mode, self-assessed severity, or nearmiss hazard classification.

Routing FARS through the existing `SourceAdapter` and intake schema would require inventing fields or
silently assigning meanings that are absent from the official source. It would also make downstream
code more likely to combine a lagging fatal-outcome measure with a leading near-miss signal as though
they were interchangeable observations.

## Decision

Create a sibling, runtime-checkable `OfficialOutcomeAdapter` protocol, immutable batch provenance,
and a separately versioned `official-outcome.schema.json`. Official outcome adapters do not appear in
the contributor-report adapter registry.

The first implementation reads the FARS crash-level `accident.csv` table from a local CSV or official
nested ZIP export. It assigns deterministic source-derived identifiers, validates dates, coordinates,
fatality counts and archive bounds, and emits complete accepted/rejected accounting plus the input
SHA-256. It does not infer involved road-user modes; FARS mode classification requires an explicit
person-table join in a later decision and implementation.

## Consequences

- Official outcomes can provide national context without acquiring fabricated intake semantics.
- Every file-backed parsed batch is traceable to its source bytes and accounts for every source row;
  programmatic row iterables carry explicit null source-byte provenance.
- The same official outcome schema can later support state crash data, provided each adapter documents
  its source-specific scope and limitations.
- Consumers must join or compare the report and outcome datasets explicitly; there is no single mixed
  record stream.
- This slice is offline-only. Download authentication, expected-digest pins, immutable ingestion
  receipts, scheduled refreshes, person-level mode joins, and segment linkage remain separate gates.

## Alternatives considered

- **Map FARS rows into the intake report schema.** Rejected because required reporter and hazard
  semantics do not exist in FARS and would have to be invented.
- **Add FARS fields directly to the published segment schema.** Rejected because a source adapter and
  canonical record boundary are needed before aggregation, linkage, and privacy decisions can be
  reviewed independently.
- **Wait for a unified national crash API.** Rejected because NHTSA already publishes stable annual
  CSV exports and an offline boundary is reproducible and testable today.
