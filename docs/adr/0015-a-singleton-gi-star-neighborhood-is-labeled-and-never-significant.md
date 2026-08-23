# 15. A singleton Gi\* neighborhood is labeled, and can never be significant

- Status: Accepted
- Date: 2026-08-19
- Deciders: Chelsea Kelly-Reif (maintainer)
- Tags: statistics, published-contract, honesty

## Context

Getis-Ord Gi\* is published here as a **local** statistic: a high z means a segment's rate, *together
with its neighbors'*, is higher than spatial structure alone would produce. The brief renders that as
a ★, and `schema/dataset.schema.md` tells consumers `getis_ord_significant` "is the field a map should
use to mark a cluster as significant."

That reading silently fails for a unit whose neighborhood is only itself. With binary weights and a
singleton neighborhood, `w_sum == w2_sum == 1`, and the Gi\* denominator collapses:

```
denom = s * sqrt((n*1 - 1*1) / (n - 1)) = s * sqrt((n-1)/(n-1)) = s
z     = (x_i - mean) / s
```

That is a plain **global** z-score — one segment against the whole city's rate distribution — emitted
through the Gi\* code path, carried into `getis_ord_significant`, and rendered as a ★. It answers a
different question than the one the label promises, and nothing downstream could tell the two apart.

A unit lands in a singleton neighborhood three different ways, and only the first is documented
anywhere:

1. **A genuine graph island** — no adjacent segment at all.
2. **The band-versus-length arithmetic.** `nearmiss/network.py` weights an edge as
   `len(a)/2 + len(b)/2`, so a segment longer than `2 * gi_band_m` can never reach *any* neighbor: its
   own half-length exceeds the band before the neighbor's is added. Deterministic, undocumented until
   now, and it selects for exactly the long arterials most likely to carry reports.
3. **No usable value at the neighbors.** `getis_ord_star` ignores neighbor ids absent from `values`, so
   a segment with three real network neighbors, none of which has an exposure denominator, is
   *effectively* alone without being structurally so.

Measured on the real Potsdam run (`docs/findings/2026-08-15-potsdam-real-run.md`, `gi_band_m = 300`),
148 of 8,129 segments had a singleton neighborhood — but only **20** were genuine islands and **128**
were the arithmetic, median length 675 m. Every segment ≥ 600 m was a singleton, without exception.
The headline ranked segment reported `z = 5.407`, which is exactly `(228.5714 − 18.6435) / 38.8214`;
re-segmentation gave it reachable neighbors and the statistic fell to 2.258.

The committed fixtures did not catch it, and the reason is instructive:

| fixture | segments | structural singletons | **effective** singletons | max segment length |
| --- | ---: | ---: | ---: | ---: |
| `config/davis-demo.toml` | 180 | 0 | **2** | 177.9 m |
| `config/riverside-demo.toml` | 6 | 6 | **6** | 147.6 m |

`davis` is a dense synthetic grid whose longest segment is under a third of the 600 m threshold, so
case 2 is structurally unreachable there — but case 3 is not, and `seg-03` and `seg-11` were already
publishing global z-scores. `riverside` is entirely islands, so *every* Gi\* z it publishes is a global
z-score; it shipped no ★ only because Benjamini-Hochberg happened to reject all of them. The
correctness of the published output rested on a multiple-comparisons correction coming out a
particular way, not on the statistic being the one the label named.

## Decision

Both remedies from issue #193, through the one mechanism the published contract already has.

1. **Label it.** `singleton_neighborhood` joins the published `quality_flags` vocabulary (schema
   **1.2.0**, an additive MINOR change). The z-score is still published. Withholding a number because
   it is awkward would be its own distortion; the defect was never that the number existed, it was that
   the number went out unlabeled.
2. **Never star it.** `getis_ord_significant` is forced `false` for any feature carrying that flag, so
   a ★ always means a cluster, and no significance claim anywhere rests on a global z-score.

"Singleton" means **effective** — the neighborhood after adding the focal unit and dropping ids absent
from `values` — so case 3 cannot slip through. `honest_rates.hotspot.singleton_neighborhoods` is the
single definition, sharing its `_effective_neighbors` helper with `getis_ord_star` itself so the two
can never disagree about what a unit's neighborhood was.

The rule is applied at **every** site that turns a z-score into a published significance claim, not
only the dataset:

- `nearmiss.stats.analyze` — the published GeoJSON and the ranked brief;
- `nearmiss.stats.maup.rank_stability` — coarsening *increases* the chance of a singleton, so exempting
  the re-segmentation check would let it answer a laxer question than the one it audits;
- `nearmiss.stats.calibration` — a null model that counted discoveries the pipeline cannot make would
  report the false-positive rate of a procedure nobody runs;
- `honest_rates.unit.analyze` — the standalone library path, which reaches the same degeneracy through
  the straight-line `band_neighbors` map and now returns `singleton_neighborhood=True` alongside
  `significant=False`.

## Consequences

- **The published demos changed.** `riverside`: all 5 published features gain the flag (all 6 segments
  are singletons; `rs-4` is withheld for k-anonymity). `davis`: `seg-03` gains it. No ★ changed in
  either demo — davis's 5 significant segments (`seg-02`, `seg-05`, `seg-06`, `seg-07`, `seg-10`) all
  have real neighborhoods, and riverside published none. The published dataset now *says* what was
  previously only true by luck.
- **Consumers pinned to schema 1.1.0** see one new flag value. It is additive and ignorable per the
  versioning policy; a consumer that treats an unknown flag as an error was already out of contract.
- **A `false` significance is now slightly more conservative.** A genuinely isolated unit with a
  genuinely extreme rate no longer gets a ★. That is the intended trade: the ★ means one thing, and a
  reader who wants the global comparison can read `getis_ord_z` next to the flag that says what it is.
- **This does not fix the underlying arithmetic.** A 700 m arterial still gets no neighbors at
  `gi_band_m = 300`; it is now labeled rather than silently mis-analyzed. Making long segments reachable
  (re-segmentation, or an edge weight that is not half-length) is a separate change to the *statistic*,
  and issue #193's config-time check for `gi_band_m < max_segment_length / 2` remains open.

## Alternatives considered

- **Suppress `getis_ord_significant` only, no flag.** Safer output, but a reader seeing `z = 5.407` with
  `significant: false` and no explanation would reasonably conclude the FDR correction rejected it. The
  flag is what makes the suppression legible.
- **Flag only, leave significance alone.** Keeps the most information, but leaves a ★ on the map that
  does not mean what the schema says a ★ means, and depends on every downstream consumer reading
  `quality_flags` before trusting `getis_ord_significant`. The QGIS renderer, for one, does not.
- **Publish `getis_ord_z` as `null` for singletons.** Rejected: this is the project's own dominant
  defect class in reverse — an absence rendered as a value is the bug, but so is discarding a real
  computed number rather than describing it. The z is real; what it measures is what needed saying.
- **Fix the edge weight so long segments have neighbors.** Changes every `getis_ord_z` in every city and
  is a genuine methodology change deserving its own ADR and its own validation. It also would not
  address case 1 or case 3, which are properties of the data rather than of the weighting.
