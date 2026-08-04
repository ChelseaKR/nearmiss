# 14. County FARS context requires a verified public projection

Date: 2026-07-18

## Status

Proposed — begin private feasibility work; do not publish a county map or county
counts until every acceptance gate below passes.

## Context

The national Atlas now provides a state evidence sheet based on reviewed annual
FARS state-by-involved-mode projections. Users can legitimately ask the next
question: what official fatal-crash context is published for a county within
their state?

This is not a client-side zoom feature. The existing public artifacts contain
state aggregates only. Rendering county shapes without a separately reviewed
county projection would imply finer evidence that has not been published.

The private, proof-bound FARS joined artifacts already retain three useful
inputs for a feasibility gate:

- source-native `state_code` and three-digit `county_code` on each crash;
- `county_status` (`reported`, `other`, `not_reported`, or `unknown`);
- an immutable annual `county_code_system` bound to the source-year contract.

Those fields make a safe county projection possible, but they are not a public
county product. In particular, FARS county codes must be verified against a
pinned county-equivalent presentation join before they can be associated with
Census geometry. County boundaries also need their own source, vintage, digest,
and topology proof. Census describes Cartographic Boundary Files as simplified
thematic-map representations and makes county-equivalent files available; the
file vintage must be explicit because geographic areas can change between years.

## Decision

Build a **private feasibility artifact first**, then a state-sharded public
county projection only after the artifact, its presentation join, and its
geography all reconcile.

The public product, if approved, will be a state/year-sharded static artifact.
It will contain only county-equivalent identities, names, geometry references,
published counts, and publication status. It will never contain FARS case IDs,
event coordinates, dates, raw source rows, or a numeric value for a withheld
cell.

### Phase A — private feasibility artifact

For each reviewed annual snapshot, construct an internal accounting report that:

1. verifies every record has the exact source-year county-code system;
2. splits records into `reported`, `other`, `not_reported`, and `unknown`;
3. counts distinct crashes once per involved mode only for `reported` counties;
4. retains non-reported categories as accounting buckets, never fabricated
   county identities;
5. proves that reported-county contributions plus non-reported buckets equal the
   state projection for every state × involved-mode cell.

This report is a release gate and remains private even when no county values are
withheld. It is the cheapest way to find annual mapping drift before creating
any public geometry or UI.

### Phase B — reviewed presentation join and geometry

For each annual FARS county-code system, maintain a versioned crosswalk from
`(FARS state code, FARS county code)` to a Census county-equivalent GEOID. The
crosswalk must explicitly handle FARS sentinel codes and reject ambiguous,
missing, duplicate, or out-of-state mappings.

Build state-sharded county boundary artifacts from a pinned Census Cartographic
Boundary File vintage. Each artifact must record:

- the exact Census distribution URL, raw ZIP digest and byte length;
- conversion and simplification settings;
- state FIPS, county GEOID, and county-equivalent name;
- geometry validity/topology checks; and
- a one-to-one proof between crosswalk GEOIDs and geometry GEOIDs.

### Phase C — public artifact and county lens

Only after Phases A and B pass, publish `county-mode` artifacts keyed by state
and year. A candidate cell has exactly one of two public states:

- `published` with a numeric `crash_count` at or above the effective publication
  floor; or
- `suppressed_or_zero` with no numeric count anywhere in the public artifact.

The county lens must retain the state lens claim boundary: counts are reviewed
fatal-crash burden, not exposure-normalized risk, fault, causation, treatment
effect, a hotspot designation, or a priority ranking. Modes overlap and cannot
be added.

## Alternatives considered

### Render county boundaries now, with no data

Rejected. It gives the appearance of locality while answering no verified
county-level question and creates pressure to infer results from an empty map.

### Publish raw FARS county values directly

Rejected. It bypasses source-year code verification, reconciliation, small-cell
publication policy, and the public-artifact integrity path.

### Publish one national county bundle

Rejected. It is unnecessary for a state-first interaction, increases payload and
review scope, and makes annual corrections harder to isolate. State shards are
the unit users enter from the existing Atlas and the unit that can be reconciled
to the state ledger.

## Acceptance gates

No county values or map ship until all are green:

1. Annual feasibility accounting reconciles by state × involved mode, including
   all sentinel county buckets.
2. Every reported source county maps once to a valid Census county-equivalent
   GEOID, with no cross-state joins.
3. Every public county GEOID maps once to reviewed geometry, and every geometry
   artifact passes digest, byte-length, and topology checks.
4. The public artifact cannot contain a hidden count for a withheld cell in
   JSON, DOM text, SVG, ARIA, data attributes, CSS properties, downloads, or
   charts.
5. County totals plus explicit non-reported buckets reconcile to the existing
   state artifact for each annual release and involved mode.
6. Difficult cases pass fixtures: Alaska county equivalents, Virginia independent
   cities, Louisiana parishes, DC, and FARS sentinel counties.
7. At least three intended users can name a county-level decision this context
   informs and correctly explain that it is burden, not local risk.

## Initial work items

1. Add the private annual county-feasibility schema and builder, using the
   existing proof-bound joined artifact seam.
2. Add synthetic fixtures for reported and sentinel county codes plus a
   state/mode reconciliation test.
3. Obtain and hash one Census county-equivalent boundary source for a deliberately
   difficult pilot state; write the corresponding FARS-to-Census crosswalk
   contract.
4. Review the pilot accounting result before committing to nationwide geometry or
   public UI work.

## Consequences

This delays a visually impressive county map, but it prevents a more serious
failure: presenting unverified local-looking data as evidence. It also creates a
reusable county artifact path that can be audited, corrected annually, and
tested without adding a live mapping service or exposing source records.

## Sources

- [U.S. Census Cartographic Boundary Files](https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.2020.html)
- [Census Cartographic Boundary File description and naming convention](https://www.census.gov/programs-surveys/geography/technical-documentation/naming-convention/cartographic-boundary-file.html)
- [2024 Census cartographic-boundary filename specification](https://www2.census.gov/geo/tiger/GENZ2024/2024_file_name_def.pdf)
