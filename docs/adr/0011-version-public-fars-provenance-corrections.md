# ADR 0011: Version public FARS provenance corrections

- Status: Accepted
- Date: 2026-07-12

## Context

The first public 2024 state-by-mode artifact identified its source as a Final File. NHTSA's April
2026 FARS Analytical User's Manual instead identifies 2024 as the Annual Report File (ARF) and
explains that an ARF is later replaced by a final file. The pinned archive identity and projected
counts remain valid; the release-stage provenance is wrong.

Published NearMiss artifacts are immutable and hash-addressed. Rewriting the existing 2024 artifact
or index URL would erase the exact public record that users may already have downloaded.

## Decision

Append 2024 annual contract revision 2 with the same raw archive identity and mapping versions,
`release_stage = "annual_report_file"`, an exact predecessor digest, and an explicit correction
review reference. The registry permits unchanged raw bytes and mappings only for this narrow
provenance-only transition; normal reused-archive revisions still require a mapping advance.

Retain `fars-2024-state-mode.json` and `fars-state-mode-index.json` byte-for-byte. Publish the
corrected artifact as `fars-2024-state-mode-r2.json`, publish the current allowlist as
`fars-state-mode-index-v2.json`, and bind prior and replacement bytes in
`fars-release-corrections.json`. The browser consumes only the current index and displays the exact
selected release stage.

## Consequences

- Existing URLs remain auditable and reproducible.
- Current users receive corrected provenance without any change to state/mode counts or suppression.
- Validators, schemas, browser checks, Pages assembly, deployment smoke tests, and the live-integrity
  sentinel must understand revision-aware filenames and verify both retained and current catalogs.
- A later NHTSA Final File will require another reviewed contract revision and a new immutable public
  artifact; it must not overwrite the ARF release.
