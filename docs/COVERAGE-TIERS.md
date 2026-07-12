# Source registries and evidence tiers

Nationwide coverage does not imply nationwide street-level certainty. `nearmiss coverage` checks a
city's declared sources against the files that actually load and reports which analyses are
supportable. It never produces a composite safety score or compares cities.

```bash
nearmiss coverage --config config/davis-demo.toml
nearmiss coverage --config config/city.toml --registry path/to/city.sources.toml
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
outcomes agree. Those are separate findings. Official crash/outcome and intervention-history sources
unlock separate capabilities and remain visible as gaps when absent.

Capabilities require both usable loaded data and the matching registry declaration. A stale street,
incident, or exposure source blocks promotion to `measured_city`; a large report count never overrides
freshness or observed-exposure coverage.

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
