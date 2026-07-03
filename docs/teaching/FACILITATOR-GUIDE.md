# Facilitator guide — *"How to lie with heat maps"*

> Language: **English** · Español: [`FACILITATOR-GUIDE.es.md`](FACILITATOR-GUIDE.es.md)

A 90-minute, hands-on workshop for journalists, civic-data volunteers, community
advocates, and students on why a raw-count heat map misleads and how honest
spatial statistics — exposure normalization, confidence intervals, and
false-discovery-controlled hotspots — put it right. It is built on `nearmiss`'s
**synthetic Davis fixtures**, a known-answer street grid with a planted hotspot
and a deliberately *busy decoy*, so participants practice the reasoning with zero
real, sensitive data.

This module is the teaching-mode expression of the project's threat model
**T4 — a naive consumer misreading a raw-count map as danger**
([`docs/THREAT-MODEL.md`](../THREAT-MODEL.md)). The workshop's whole arc is T4's
core mitigation: *make the honest reading the easy reading.*

---

## Learning objectives

By the end of the session, participants can:

1. **Explain the lie.** Say precisely why a raw-count (or unnormalized
   kernel-density) heat map points at the *busiest* location and mislabels it the
   *most dangerous* one.
2. **Normalize by exposure.** Compute a rate as reports per unit of exposure and
   explain what the denominator is and why it changes the ranking.
3. **Read uncertainty.** Interpret a 95% confidence interval on a rate and use
   overlapping intervals to resist over-reading small differences.
4. **Distinguish "hot because dangerous" from "hot because busy."** Describe what
   the Getis-Ord Gi\* local statistic tests and why it runs on the rate, not the
   count.
5. **Respect multiple comparisons.** Explain why a Benjamini-Hochberg
   false-discovery-rate (FDR) correction is applied and what it protects against.
6. **Spot the modifiable areal unit problem (MAUP).** Show how re-drawing segment
   boundaries can manufacture or dissolve a "significant" hotspot, and name the
   defenses (pre-registration, sensitivity reporting, keeping the full
   comparison set).
7. **Apply the T4 mitigations** to a real map or chart they encounter in the
   wild: label volume as volume; publish rates, intervals, and significance; name
   the bias.

---

## Audience and prerequisites

- **Audience:** journalism / civic-data / advocacy workshops; no statistics
  background assumed. Works for undergraduates through newsroom data teams.
- **Comfort with:** reading a table; the idea of a rate (e.g. "per 1,000"). Some
  Python familiarity helps for the exercise notebook but is not required — a
  facilitator can drive the notebook while participants reason aloud.
- **Group size:** 4–30. Above ~12, use small groups of 3–4 for the exercises.

---

## Setup (facilitator, before the session)

```bash
git clone https://github.com/ChelseaKR/nearmiss && cd nearmiss
python -m pip install -e ".[teaching]"   # Jupyter execution stack (isolated extra)
make teach                                # execute all three notebooks into notebooks/_build/
```

The notebooks live in [`notebooks/teaching/`](../../notebooks/teaching/). They are
deterministic and offline: no RNG, no network, no real data. You can present them
live (run cell by cell) or hand participants the pre-executed copies from
`notebooks/_build/`. If projecting, the SVG heat map in notebook 01 scales
cleanly.

**Dataset honesty note to state aloud:** the Davis data is *synthetic
demonstration data, not real reports.* The point is the reasoning, not Davis.

---

## The 90-minute plan

| Time | Segment | What happens |
| ---: | --- | --- |
| 0:00–0:10 | **Frame the lie** | Show a raw-count heat map with no legend. Ask the room to point at "the most dangerous street." Reveal that it is simply the *busiest* one. Introduce T4 in one line: the most common misuse of this project's findings is not an attack — it is an honest misreading. |
| 0:10–0:30 | **Notebook 01 — The naive map** | Run it live. Sit on the two-panel figure: the decoy `seg-03` is brightest on the raw-count map (left) and dissolves on the exposure-normalized map (right); the planted `seg-06` corridor emerges. End on the published ranked table — the honest artifact is a table with rates, intervals, and a text-marked significant cluster, not a colored blob. |
| 0:30–0:55 | **Notebook 02 — Find the decoy (exercise)** | In small groups: rank by raw count (Step 1), compute rates + 95% CIs with the real pipeline function (Step 2), measure the rank fall (Step 3). Groups commit to an answer *before* the Solution cell. Debrief: who found `seg-03`? What in the exposure column gave it away? |
| 0:55–1:20 | **Notebook 03 — Break the CI** | Run the baseline cluster, then the *split* that manufactures a hotspot on the borderline `seg-05`, then the *merge* that dissolves the real `seg-06` corridor. Emphasize: same reports, same statistics, three "truths." Draw out that the CI and the FDR correction are real but cannot save you from a rigged unit of analysis. |
| 1:20–1:30 | **Close — the honest defaults** | Recap the T4 mitigations as a checklist participants can apply to any map they meet next week. Assign the take-home prompt. |

Running short? Drop the notebook-03 *merge* demo (keep the *split*). Running long
or advanced? Add the "extend it" prompts below.

---

## Discussion prompts (keyed to threat model T4)

Each prompt maps to a specific **T4 mitigation** in
[`docs/THREAT-MODEL.md`](../THREAT-MODEL.md). Use them at the segment breaks.

- **After notebook 01 — "Label volume as volume."** *Where have you seen a
  raw-count or "heat" map presented as danger, risk, or crime? What one label
  would have made the honest reading the easy reading?* (Mitigation: unnormalized
  surfaces are labeled *report intensity*, never *danger*; the label travels with
  the artifact.)
- **After notebook 01 — "Publish rates, intervals, and significance, not just a
  surface."** *Why is a ranked table with intervals harder to screenshot out of
  context than a colored map? What does that buy the honest version?*
- **After notebook 02 — "Name the bias on the page."** *Who is over- and
  under-represented in a crowd-sourced near-miss dataset? A rate fixes the
  denominator — what does it still not fix?* (Mitigation: every brief states who
  is over/under-represented and what that does to the conclusion.)
- **After notebook 02 — "The equivalent table carries the caveats."** *A
  screen-reader user never sees the colored blob. What must the table contain so
  they reach the same honest conclusion?*
- **After notebook 03 — MAUP and the limits of statistics.** *The confidence
  interval and the FDR correction are real protections. Name something each one
  does NOT protect against.* (Answer: the CI addresses sampling noise, not a
  chosen unit; FDR addresses multiple-comparison luck, not a unit chosen after
  seeing the data.)
- **After notebook 03 — "Make the honest version the citable one."** *T4 "stops
  at" re-cropping: once someone screenshots a surface and strips its legend, the
  project cannot control the caption. If you cannot prevent misuse, what is the
  realistic goal?* (Answer: make the labeled, honest artifact the most prominent
  and citable one.)

**Take-home prompt.** Bring one real heat map from the news or an agency
dashboard. Answer: (a) is it counts or a rate? (b) what is the denominator, or is
one missing? (c) what would you have to know to trust the "hotspot"?

---

## Answer key

**Notebook 01 — The naive map.**
- Raw-count "worst" street: **`seg-03`, "3rd St (B–C)"** — it simply has the most
  reports (12 close passes + 5 surface hazards + 3 debris = 20).
- Exposure-normalized worst street: **`seg-06`, "5th St (C–D)"** — the planted
  hotspot (low exposure, high rate).
- Why it flips: `seg-03`'s exposure denominator (8,000 bike trips) is ~27× the
  hotspot's (300), so its rate (2.50 /1,000) is far below `seg-06`'s (20.0
  /1,000). This is the exact behavior pinned by
  `tests/test_hotspot.py::test_busy_decoy_has_most_raw_reports_but_low_rate`.

**Notebook 02 — Find the decoy.**
- The decoy is **`seg-03`, "3rd St (B–C)"**: it tops the raw-count ranking but
  falls the furthest to near the bottom of the rate ranking, is **not** in the
  top three by rate, and is **not** flagged as a significant Gi\* cluster.
- The true hotspot is **`seg-06`, "5th St (C–D)"**: highest rate and the centre of
  the only significant cluster.
- Tell participants the reveal cell *asserts* these facts against the pipeline, so
  the answer is not the facilitator's opinion — it is the same code that gates the
  project's tests.

**Notebook 03 — Break the CI.**
- Baseline significant hotspots: **`seg-02`, `seg-06`, `seg-07`, `seg-10`** (the
  5th St corridor and its cross streets). `seg-05` is *borderline*: its raw
  two-sided p-value is ~0.029 (below 0.05), yet FDR correctly holds it back.
- **Manufacture (split):** cutting `seg-05` into two co-located blocks makes both
  halves cross into "significant" — a hotspot conjured purely by re-segmentation,
  with no new reports.
- **Dissolve (merge):** merging the real corridor (`seg-02/05/06/07/10`) into one
  averaged block leaves **zero** significant segments — Gi\* needs high-rate
  neighbors to detect a cluster, and the merge erases them.
- Defenses: pre-register the segmentation; report sensitivity to the unit; keep
  the whole comparison set (dropping "boring" segments shrinks `m` and loosens the
  FDR threshold); anchor significance to the reports, not the geometry.

**Common misconceptions to correct.**
- *"A bigger number means more danger."* Only after dividing by exposure.
- *"Statistical significance means it is real."* Significance is conditional on
  the chosen unit and the set of tests; a Gi\* star that survives only one
  hand-drawn segmentation is a MAUP artifact.
- *"A confidence interval tells me the map is right."* It quantifies sampling
  noise for a fixed segmentation; it says nothing about a rigged denominator or a
  rigged boundary.

---

## Extend it (for longer or advanced sessions)

- Have participants change `fdr_alpha` or the Gi\* band (`gi_band_m`) in
  `config/davis-demo.toml` and predict, then observe, the effect on the
  significant set.
- Point real inputs at the same notebooks via
  [`docs/REAL-DATA.md`](../REAL-DATA.md) and discuss what breaks when the
  known answer disappears.
- Compare with the project's other reproducibility notebooks in
  [`notebooks/`](../../notebooks/README.md) and `make reproduce`.

## Further reading (in this repository)

- [`docs/THREAT-MODEL.md`](../THREAT-MODEL.md) — T4 in full, with all mitigations.
- [`docs/METHODOLOGY.md`](../METHODOLOGY.md) — rates, CIs, Gi\*, and FDR as the
  project uses them.
- [`docs/LIMITATIONS.md`](../LIMITATIONS.md) — what the analysis does not claim.
- [`tools/make_fixtures.py`](../../tools/make_fixtures.py) — how the planted
  hotspot and the busy decoy are constructed.
