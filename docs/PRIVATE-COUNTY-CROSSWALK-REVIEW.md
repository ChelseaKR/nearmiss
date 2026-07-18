# Private county crosswalk review

This is the intake gate for a future county lens. It produces no public data,
map layer, count, or download.

## Purpose

FARS county codes are source-native annual GSA codes. Census GEOIDs are
presentation identities. A reviewer must make that join explicit; the build
never infers a GEOID by concatenating codes.

## Workflow

1. Create the exact private county-feasibility artifact from a verified annual
   FARS joined artifact.
2. Build the pinned private Census county boundary shards.
3. Generate a no-count review packet:

   ```sh
   PYTHONPATH=src python tools/build_fars_county_crosswalk.py \
     --feasibility /secure/2024-feasibility.json \
     --template-out /secure/2024-county-review.json
   ```

4. Independently review every row. Replace `pending-review` with an immutable
   review reference; map a row to the exact Census name, `NAMELSAD`, FIPS, and
   GEOID, or retain it as explicitly `unresolved` with a reason.
5. Build the private crosswalk:

   ```sh
   PYTHONPATH=src python tools/build_fars_county_crosswalk.py \
     --feasibility /secure/2024-feasibility.json \
     --review /secure/2024-county-review.json \
     --boundary-dir /secure/county-boundaries-2024 \
     --out /secure/2024-county-crosswalk.json
   ```

The build refuses noncanonical inputs, source-code omissions, a pending review,
detached feasibility lineage, sentinel county codes, mismatched boundary source
provenance, or a reviewed identity that differs from a pinned boundary feature.

## Publication gate

The resulting crosswalk remains private. Any unresolved row blocks county
projection. A public county shard additionally requires reconciled projection,
suppression review, and the release approval described in the county-drilldown
plan.
