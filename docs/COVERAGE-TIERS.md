# Source registries and evidence tiers

Nationwide coverage does not imply nationwide street-level certainty. `nearmiss coverage` checks a
city's declared sources against the files that actually load and reports which analyses are
supportable. It never produces a composite safety score or compares cities.

```bash
nearmiss coverage --config config/davis-demo.toml
nearmiss coverage --config config/city.toml --registry path/to/city.sources.toml
nearmiss coverage --config config/city.toml --fars-root "$HOME/.local/share/nearmiss/ingestion"
```

The JSON result is intended for onboarding checks, city galleries, CI, and future APIs. Its tiers
are deliberately conservative:

Every result includes the registry's SHA-256 and its non-sensitive source descriptors (identifier,
kind, name, license, vintage, geography, access, URL, and synthetic flag), so a tier is traceable to
the exact source declaration that produced it.

| Tier | Meaning |
| --- | --- |
| `demonstration` | A core street, incident, or exposure source is synthetic. |
| `national_baseline` | Context/screening is possible, but usable segment exposure is absent. |
| `modeled_city` | Segment rates are possible, but observed exposure is incomplete, modeled, or stale. |
| `measured_city` | Observed, current exposure meets the registry's coverage threshold. |
| `partner_city` | The measured-city bar is met and a partner organization and review reference are recorded. |

Promotion does not imply that a city is safe, that its reports are representative, or that official
outcomes agree. Those are separate findings. An official-outcome registry row is a declaration, not
proof that any bytes exist. It never grants triangulation by itself.

Capabilities require both usable loaded data and the matching registry declaration. For FARS, the
optional `--fars-root` additionally verifies the owner-only active receipt, immutable history, raw and
normalized hashes, artifact contract, and deterministic raw-to-normalized replay. A stale street,
incident, or exposure source blocks promotion to `measured_city`; a large report count never overrides
freshness or observed-exposure coverage.

Context and intervention-history rows likewise remain declarations until source-specific records are
loaded and validated; they do not mint `contextual_screening` or `before_after_evaluation_inputs` from
TOML alone.

## Official-outcome trust states

| Registry `id = "fars"`, `kind = "official_outcomes"` | Verified active FARS chain | Result |
| --- | --- | --- |
| No | No | Declare the source; no outcome capability. |
| Yes | No | Verify with `--fars-root`; no outcome capability. |
| No | Yes | Verification metadata is visible, but no capability without the matching declaration. |
| Yes | Yes | Grants only `verified_official_outcomes`. |

`verified_official_outcomes` means the local crash-level artifact is internally consistent with its
preserved raw bytes. It does **not** authenticate an NHTSA signature, identify road-user modes, link
crashes to street segments/time windows, publish precise outcomes, or grant
`official_outcome_triangulation`. Those require separately reviewed person-table, linkage,
methodology, and privacy work. Verified FARS never changes the evidence tier, incident count, segment
count, or exposure coverage.

The JSON result records declared official-outcome IDs and either `not_requested` or a safe verified
summary (year, mapping/release metadata, aggregate counts, hashes, and attempt ID). It never contains
the private root, internal paths, rows, outcome IDs, or coordinates. Supplying an invalid
`--fars-root` fails the command without emitting a downgraded assessment.

## Registry contract

Add `source_registry = "path/to/city.sources.toml"` to the city config. The registry is versioned
TOML:

```toml
version = 1
city = "Example"
measured_min_coverage = 0.8

[partner]
organization = "Example Safe Streets Coalition"
review_ref = "meeting-notes-2026-07-12"

[[sources]]
id = "example-counts-2026"
kind = "exposure" # streets | incidents | exposure | official_outcomes | context | interventions
name = "Example bicycle and pedestrian counts"
license = "CC0-1.0"
updated_at = "2026-06-30"
geography = "Example city limits"
access = "open" # open | partner | licensed | private
url = "https://example.gov/counts"
synthetic = false
stale_after_days = 365
```

`organization` and `review_ref` must be supplied together. A registry date is compared to the
analysis window, latest valid report date, or latest registry date—not the wall clock—so repeated
assessments are reproducible. Use `--as-of YYYY-MM-DD` for an explicit freshness audit date.
