# nearmiss (honest symbology) — QGIS plugin

**EXP-11** from [`docs/ideation/03-expansions.md`](../../docs/ideation/03-expansions.md): a small QGIS
plugin that loads any conforming nearmiss GeoJSON (see
[`schema/dataset.schema.md`](../../schema/dataset.schema.md)) with the correct visual grammar
pre-wired, so a GIS analyst working directly in QGIS cannot innocently rebuild the report-count
heat-map lie in two clicks the way they could starting from the raw attributes.

Goes beyond a static `.qml` style file: a plugin can enforce the legend text, load the `metadata`
foreign member into layer properties, and run an invariant check on load.

## What "honest" means here

Concretely, loading a dataset through this plugin (instead of adding the GeoJSON as a generic vector
layer and styling it by hand) gets you, automatically:

- **Rate, not count, drives the color ramp (HR1).** The graduated symbology classes are computed from
  `rate` (`report_count` normalized by `exposure_estimate`), never from raw `report_count`. A feature
  with `exposure_estimate: null` — no denominator available — is never coerced into the coolest color
  on the ramp or silently treated as zero: it gets its own always-present, neutral-gray class labeled
  **"exposure unknown"** in the legend, matching the schema's `confidence_label: "exposure_unknown"`.
- **Significance is a pattern, not just a color (accessibility + honesty).** Getis-Ord Gi\*
  significance (`getis_ord_significant`) is drawn as a distinct line/marker pattern (e.g. a dash-dot
  line for a significant hot spot vs. a solid line for "not significant"), layered on top of the rate
  color, so a reader without color vision — or a black-and-white printout — still sees which features
  are statistically significant. `false` is drawn distinctly and labeled "not significant at
  threshold," not "safe."
- **CI-labeled tooltips (HR2).** The maptip for every feature states the rate, its 95% confidence
  interval, its sample size `n`, and its `confidence_label` (`certain` / `uncertain` /
  `exposure_unknown`) as text — never just a number with an implied precision it doesn't have.
- **Reporting-bias caveats travel with the feature (HR3).** `quality_flags` (e.g. `low_sample`,
  `geocode_low_confidence`) are shown in the tooltip.
- **The dataset's own metadata rides along.** The GeoJSON's top-level `metadata` foreign member
  (license, exposure unit, significance method, privacy statement, schema version) is copied into the
  QGIS layer's metadata (Layer Properties → Metadata) and custom properties, so it survives saving a
  `.qgs`/`.qgz` project and is visible without opening the raw file.
- **A lightweight invariant check runs on every load.** Before styling, the plugin checks the file
  against the handful of HR1/HR2 invariants its own rendering relies on (e.g. "a rate is never
  published without a confidence interval," "a null exposure implies a null rate") and logs any
  violation to the QGIS log panel (`nearmiss-honest`) plus a message-bar warning, instead of silently
  mis-rendering a malformed or hand-edited file. This is a small, in-plugin echo of the project's
  broader HR1–HR5 conformance goals — not a replacement for the project's own full conformance gate
  (tracked separately in the roadmap as the HR1–HR5 conformance verifier).

## Layout

```
integrations/qgis/
├── README.md                    — this file
├── nearmiss_honest/
│   ├── __init__.py               — classFactory() entry point QGIS calls
│   ├── metadata.txt               — QGIS plugin metadata (name, version, description)
│   ├── icon.png                   — plugin icon
│   ├── rules.py                   — pure-Python honest-symbology decisions (no PyQGIS import;
│   │                                 unit-tested directly)
│   ├── verify.py                  — standalone CLI: `python -m nearmiss_honest.verify some.geojson`
│   ├── qgis_layer.py               — PyQGIS glue: rules.py decisions -> QgsRuleBasedRenderer /
│   │                                 maptip / layer metadata
│   ├── plugin.py                   — QGIS plugin class (menu action, file dialog)
│   └── sample_data/
│       ├── davis.geojson           — bundled demo dataset (mirrors data/published/davis.geojson)
│       └── riverside.geojson       — bundled demo dataset (mirrors data/published/riverside.geojson)
└── tests/
    ├── conftest.py
    ├── test_rules.py               — unit tests for rules.py, run against both bundled datasets
    └── test_verify_cli.py          — unit tests for the verify.py CLI
```

`rules.py` and `verify.py` have **no PyQGIS dependency** and are exercised by plain pytest (see
[Running the tests](#running-the-tests) below) — that's where the actual "what counts as honest"
logic lives and is verified. `qgis_layer.py` and `plugin.py` import `qgis.core`/`qgis.PyQt` and are
thin glue that turns those decisions into real QGIS API calls; they can only run inside a QGIS Python
environment.

## Installing (development / manual use)

QGIS plugins are not installed via `pip`; QGIS looks for them in its own plugins directory.

1. Copy or symlink `nearmiss_honest/` into your QGIS profile's plugin directory, e.g. on Linux/macOS:
   ```
   ln -s "$(pwd)/integrations/qgis/nearmiss_honest" \
       ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/nearmiss_honest
   ```
   (Windows: `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\nearmiss_honest`.)
2. In QGIS Desktop: **Plugins → Manage and Install Plugins → Installed**, enable "nearmiss (honest
   symbology)".
3. Use the new **nearmiss (honest symbology)** menu: "Load bundled sample data (Davis)…" to try it
   immediately, or "Load honest nearmiss dataset…" to pick any conforming GeoJSON (e.g. a freshly built
   `data/published/<city>.geojson` from `make publish`, or a fork/derivative dataset).

## Running the tests

The pure-Python rules (the part that decides what "honest" means) are covered by plain pytest and do
**not** require a QGIS install:

```
cd integrations/qgis
python -m pytest tests/ -q
```

The tests run `verify_dataset` against both bundled sample datasets (they must be invariant-clean),
and exercise `significance_marker`, `rate_class`/`compute_rate_breaks` (confirming a `null` rate is
never coerced into a numeric class), `confidence_text`/`tooltip_html` (confirming "exposure unknown"
is always rendered as that phrase, never as a bare `0` or `None`), and the `verify.py` CLI's exit
codes.

`qgis_layer.py` and `plugin.py` are **not** covered by this pytest run, because there is no
pip-installable `qgis` package — PyQGIS only exists inside a QGIS install. See
[Manual QA before release](#manual-qa-before-release) below.

## Manual QA before release

This is the one piece of this item that is inherently a manual, human, one-time action and is
deliberately **not** claimed as done by this change: before tagging a release or submitting to the
[official QGIS Plugin Repository](https://plugins.qgis.org/), a maintainer needs to:

1. Install the plugin into a real QGIS Desktop (≥ 3.28, per `metadata.txt`'s `qgisMinimumVersion`) per
   [Installing](#installing-development--manual-use) above.
2. Load both bundled sample datasets and visually confirm: the rate ramp (not a count ramp), the
   "exposure unknown" gray class, the significance line/marker pattern change, the maptip content, and
   Layer Properties → Metadata showing the dataset's `metadata` fields.
3. Load a deliberately malformed GeoJSON (e.g. a copy of `davis.geojson` with a `rate` value edited in
   without also setting `rate_ci_low`) and confirm the invariant-violation warning appears in the
   message bar and the `nearmiss-honest` log panel.
4. Only then: package (`Plugins → Plugin Reviewer` or `qgis-plugin-ci`) and submit for the QGIS Plugin
   Repository's review cycle, which is a third-party, human review process outside this repo's control.

## Relationship to other roadmap items

- Supersedes the older idea of a static `.qml` style file (`RE-11`): a plugin can enforce legend text
  and load the metadata block, which a `.qml` alone cannot.
- Depends on the published dataset schema (`schema/dataset.schema.md`) for its field names; a schema
  MAJOR bump that renames/removes a field this plugin reads (`rate`, `rate_ci_low`, `rate_ci_high`,
  `n`, `confidence_label`, `getis_ord_z`, `getis_ord_significant`, `quality_flags`,
  `exposure_estimate`/`exposure_source`/`exposure_date`) would need a matching update here.
- The in-plugin invariant check in `rules.py`/`verify.py` is intentionally small and scoped to what
  this plugin's own rendering relies on. It is not a reimplementation of the project's broader
  HR1–HR5 conformance verifier tracked elsewhere in the roadmap.
