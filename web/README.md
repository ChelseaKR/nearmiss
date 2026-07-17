# Web — the accessible map UI

A **dependency-light** set of map interfaces targeting **WCAG 2.2 Level AA**, built to be auditable.
The production artifact reads only reviewed nationwide FARS releases; it never touches a precise raw
report. Synthetic city interfaces remain in the source tree as local known-answer demonstrations.

**Production site:** [NearMiss Conflict Atlas](https://nearmiss.chelseakr.com) — the real-data national
FARS studio is the sole deployed product. Davis, Riverside, the report form, and the embed are not
copied into the production artifact.

## The two maps (local methods demonstration)

The page shows the **same reports mapped two ways** on a real [OpenStreetMap](https://www.openstreetmap.org/copyright)
basemap:

1. **Raw report count** — what most safety maps show. The busiest street looks the most dangerous.
2. **Exposure-normalized rate** — reports per 1000 units of exposure, with Getis-Ord Gi\* significance.
   The busiest street recedes; the statistically real hotspot emerges.

That contrast — a high-volume street that is *not* a significant hotspot, next to a lower-volume street
that *is* — is the original argument of this project, made visible. The map library is
[Leaflet](https://leafletjs.com) 1.9.4, **vendored locally** in `vendor/leaflet/` (no third-party CDN,
no runtime fetch of code), so the only third-party network call is the OSM tile request, attributed in
the footer.

## Local data source and provenance banner

The page defaults to the committed synthetic demo (`../data/published/davis.geojson`). An explicit
allowlist maps `?city=<slug>` or `?data=../data/published/<slug>.geojson` to the committed Davis and
Riverside fixtures. Unknown slugs, other origins or directories, queries, fragments, traversal, and
duplicate selectors fail closed to the Davis default; adding another local city requires adding
its constant artifact path to the allowlist. The
provenance banner and the page title are driven by the dataset's **own embedded `metadata`**, never hard-coded: a
`dataset_note` that mentions "synthetic"/"demo" shows the amber demo warning; any other note shows a
green **real data** banner naming the city, exposure unit, and source. The page can therefore never
mislabel what it is actually showing. See [`docs/REAL-DATA.md`](../docs/REAL-DATA.md).

These files are source and CI fixtures, not public evidence. Use `nearmiss serve` from a local checkout,
then open `/web/davis-demo.html` for the methods demonstration or `/web/us-coverage.html` for the
national preview. The production-only `/fars/national/` route does not exist on the source server. A
real city requires a separately reviewed publication decision; copying an artifact into
`data/published/` does not make it part of the production site.

Core commitments (see [`docs/ACCESSIBILITY.md`](../docs/ACCESSIBILITY.md) and the
[ACR](../docs/accessibility/ACR.md)):

- **A non-visual equivalent.** Every finding on the map is also reachable in an accessible, sortable
  **list and table** carrying the same ranked locations, rates, intervals, and significance flags.
  The nationwide studio likewise mirrors its map, matrix, rank, and comparison graphics in semantic
  state-by-mode, comparison, five-year profile, and complete-ledger tables.
- **Never color alone.** Risk level and statistical significance are conveyed in text and pattern, not
  only hue.
- **Keyboard-operable and labeled by design.** The report form uses native labeled controls with clear
  error text. Nationwide map states and comparison-plot points use a single roving tab stop with
  arrow/Home/End navigation and Enter/Space activation, with native selectors and table controls
  available for the same evidence.
- **Honest legends.** A raw-count layer is labeled "report volume," never "danger."

Automated accessibility is a **merge-blocking CI gate** (`make accessibility` + axe). The deployed
national page and retained source-only HTML prototypes are included in those checks. A targeted
rendered-browser keyboard and 390×844 reflow
review of the nationwide studio is recorded; the uninterrupted full keyboard/200% zoom checks and the
required human NVDA/VoiceOver release gate have not yet been completed.

## Pages

| File | Role | Production |
| --- | --- | --- |
| `index.html` | noindex compatibility redirect to the national route | Yes |
| `us-coverage.html` + `us-coverage.js` | nationwide annual FARS evidence studio | Yes |
| `davis-demo.html` + `app.js` + the synthetic city artifacts | Davis/Riverside two-map known-answer methods demonstration | No — local/CI only |
| `submit.html` + `submit.js` | schema-valid report-export prototype | No — local/CI only |
| `embed.html` + `embed.js` + `nearmiss-embed.js` | synthetic hotspot embed prototype | No — local/CI only |

## Embed prototype (local only)

A self-contained, framework-free widget remains available for local method development. It must not
be syndicated as evidence: its default Davis and Riverside inputs are synthetic planted-truth
fixtures, not historical reports.

**iframe** (simplest, fully sandboxed):

```html
<iframe src="/web/embed.html?city=davis"
        title="nearmiss hazard hotspot map" width="100%" height="380"
        style="border:1px solid #d3dae2;border-radius:6px"></iframe>
```

**script tag** (injects the sandboxed iframe for you):

```html
<script src="/web/nearmiss-embed.js"
        data-city="davis" data-height="380" async></script>
```

The local widget accepts `?city=`/`?data=` selectors from an explicit allowlist of the
Davis and Riverside fixtures, renders only aggregated data (no tracking, no cookies),
encodes magnitude by line thickness and significance by a dashed pattern **and** text
(never color alone), and ships a text list of the significant hotspots as the
non-visual equivalent. The script loader resolves `/web/embed.html` on the same local origin and
never calls the retired public demo URL; unsupported, conflicting, or malformed selectors fall back
to the Davis fixture. It is retained to exercise the implementation, not as a deployable claim.
