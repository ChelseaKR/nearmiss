# Web — the accessible map UI

A **dependency-light** map interface targeting **WCAG 2.2 Level AA**, built to be auditable and to load
fast on a phone from the roadside. It reads only published artifacts; it never touches a precise raw
report.

## The two maps (this is the point)

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

## Data source and the honest provenance banner

The page defaults to the committed synthetic demo (`../data/published/davis.geojson`) but is
source-agnostic: `?city=<slug>` loads `../data/published/<slug>.geojson` and `?data=<relative-path>`
loads an explicit file, so a real city goes live by URL with no code change. The provenance banner and
the page title are driven by the dataset's **own embedded `metadata`**, never hard-coded: a
`dataset_note` that mentions "synthetic"/"demo" shows the amber demo warning; any other note shows a
green **real data** banner naming the city, exposure unit, and source. The page can therefore never
mislabel what it is actually showing. See [`docs/REAL-DATA.md`](../docs/REAL-DATA.md).

Core commitments (see [`docs/ACCESSIBILITY.md`](../docs/ACCESSIBILITY.md) and the
[ACR](../docs/accessibility/ACR.md)):

- **A non-visual equivalent.** Every finding on the map is also reachable in an accessible, sortable
  **list and table** carrying the same ranked locations, rates, intervals, and significance flags.
- **Never color alone.** Risk level and statistical significance are conveyed in text and pattern, not
  only hue.
- **Keyboard-operable and labeled.** The report form and all controls are fully keyboard-operable with
  clear labels and error text.
- **Honest legends.** A raw-count layer is labeled "report volume," never "danger."

Accessibility is a **merge-blocking CI gate** (axe + manual NVDA/VoiceOver review). All four pages
below are checked by `make accessibility` and the `axe` run.

## Pages

| File | What it is |
| --- | --- |
| `index.html` + `app.js` | the Davis two-map view + authoritative data table (above) |
| `us-coverage.html` + `us-coverage.js` | the nationwide 2024 FARS state × involved-mode evidence ledger, with explicit suppression and release provenance |
| `submit.html` + `submit.js` | the **public submission form** — accessible, serverless-honest; builds a schema-valid report for the moderation queue (see [`docs/SUBMISSIONS.md`](../docs/SUBMISSIONS.md)) |
| `embed.html` + `embed.js` + `embed.css` | the **embeddable hotspot widget** (below) |
| `nearmiss-embed.js` | one-line `<script>`-tag loader that injects the widget as a sandboxed iframe |

## Embeddable hotspot widget

A self-contained, framework-free widget an advocacy site can drop in to show the
exposure-normalized hotspot map. Two ways to embed:

**iframe** (simplest, fully sandboxed):

```html
<iframe src="https://nearmiss.report/web/embed.html?city=davis"
        title="nearmiss hazard hotspot map" width="100%" height="380"
        style="border:1px solid #d3dae2;border-radius:6px"></iframe>
```

**script tag** (injects the sandboxed iframe for you):

```html
<script src="https://nearmiss.report/web/nearmiss-embed.js"
        data-city="davis" data-height="380" async></script>
```

The widget is source-agnostic the same way the main page is (`?city=`/`?data=`),
renders only the published, aggregated dataset (no tracking, no cookies), encodes
magnitude by line thickness and significance by a dashed pattern **and** text
(never color alone), and ships a text list of the significant hotspots as the
non-visual equivalent plus a link back to the full map, data, and methods.
