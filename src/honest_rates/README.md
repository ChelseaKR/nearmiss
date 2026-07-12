# honest_rates

Exposure-normalized rates and honest hotspot detection for **any** point-event
dataset — not just [`nearmiss`](https://github.com/ChelseaKR/nearmiss), the
road-safety project this library was extracted from.

If you have a set of "places" (street segments, census tracts, store
locations, patrol beats, service areas — anything with a stable id and a
`(lat, lon)`), a count of events per place, and an independent exposure
denominator per place (foot traffic, housing units, inspected properties,
flight hours...), this library answers: **is this place actually more
dangerous, or just busier?**

## Why this exists

Ranking places by a raw event count always rewards traffic. The busiest place
looks "hottest" even when nothing unusual is happening there — a doughnut shop
gets more complaints than a back alley because more people pass the doughnut
shop, not because the doughnut shop is more dangerous. This library refuses
that shortcut:

1. **A count is never a rate.** Every rate is `count / exposure`
   (`honest_rates.rates`).
2. **Small counts get honest uncertainty.** Every rate ships a confidence
   interval, well-behaved down to a count of zero (Byar's approximation to the
   Poisson interval).
3. **A cluster must be one, not a coincidence.** Getis-Ord Gi* on the *rate*
   (never the raw count), with Benjamini-Hochberg false-discovery-rate control
   across all tested places (`honest_rates.hotspot`).
4. **Ground truth is provable.** `honest_rates.fixtures` generates a synthetic
   dataset with a *known* planted hotspot and a *known* busy decoy, so a
   pipeline built on this library can be checked against a known answer.

## Install

This package currently ships inside the `nearmiss` repository as an
independent, dependency-free `src/honest_rates/` package (pure standard
library — no numpy, no geopandas, no native build step). Until it is split
into its own repository and published, install it from a checkout:

```bash
pip install -e "git+https://github.com/ChelseaKR/nearmiss.git#subdirectory=src/honest_rates&egg=honest_rates"
# or, from a local clone:
pip install -e /path/to/nearmiss/src/honest_rates
```

It has **zero** dependency on `nearmiss` itself — nothing in `honest_rates/`
imports from `nearmiss.*`. `nearmiss` is a *consumer* of this library
(`nearmiss/stats/rates.py`, `nearmiss/stats/getis_ord.py`, and
`nearmiss/spatial_index.py` are thin re-exports over it), not the other way
around.

## Quick start

```python
from honest_rates import SimpleUnit, analyze

units = [
    SimpleUnit(id="store-1", lat=38.545, lon=-121.745),
    SimpleUnit(id="store-2", lat=38.546, lon=-121.744),
    SimpleUnit(id="store-3", lat=38.560, lon=-121.700),
]
counts = {"store-1": 9, "store-2": 11, "store-3": 40}       # raw complaint counts
exposure = {"store-1": 50.0, "store-2": 50.0, "store-3": 8000.0}  # e.g. foot traffic

results = analyze(units, counts, exposure, band_m=250.0)
for r in sorted(results, key=lambda r: r.rate or 0.0, reverse=True):
    print(r.unit_id, r.rate, r.significant)
# store-1 and store-2 (low exposure, concentrated events) rank above store-3
# (the busiest raw count, but a low rate) -- "busy" did not win.
```

See `examples/potholes_demo.py` for a fuller worked example (311 pothole
*reports* vs. street *traffic*, deliberately a different domain than
nearmiss's near-miss reports) that reaches this same "busy ≠ dangerous"
conclusion using only this library.

## Validating your own pipeline against a known answer

```python
from honest_rates.fixtures import planted_cluster_fixture
from honest_rates import analyze

fx = planted_cluster_fixture()
results = {r.unit_id: r for r in analyze(fx.units, fx.counts, fx.exposure, band_m=fx.band_m)}

ranked = sorted(results.values(), key=lambda r: r.rate or 0.0, reverse=True)
assert {r.unit_id for r in ranked[: len(fx.hotspot_ids)]} == fx.hotspot_ids
assert not results[fx.decoy_id].significant
assert any(results[uid].significant for uid in fx.hotspot_ids)
```

## Modules

| Module | What it provides |
| --- | --- |
| `honest_rates.rates` | `poisson_ci`, `rate_with_ci` (Byar), `wilson_ci` |
| `honest_rates.hotspot` | `getis_ord_star`, `two_sided_p`, `benjamini_hochberg` |
| `honest_rates.bias` | `characterize_bias` — report share vs. exposure share |
| `honest_rates.geometry` | `project`, `haversine_m`, `projection_margin_m` |
| `honest_rates.spatial_index` | `SpatialIndex` — the grid accelerator Gi* uses |
| `honest_rates.unit` | `Unit` protocol, `SimpleUnit`, `analyze` orchestrator |
| `honest_rates.fixtures` | `planted_cluster_fixture` — known-answer test harness |

## License

Apache-2.0, same as `nearmiss` — see `LICENSE` at the repository root.
