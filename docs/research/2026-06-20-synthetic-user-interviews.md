# Synthetic user interviews → remediations & expansions — 2026-06-20

A broad **synthetic user-research panel** for nearmiss: 24 personas spanning the
full stakeholder map (advocacy, government, data/research, access & inclusion,
and adjacent/commercial/risk), each interviewed about the product *as it exists
today* and what they would need next. The interviews are then distilled into a
deliberately exhaustive, de-duplicated backlog: **70 remediations** (fixes and
improvements to what already ships) and **60 expansions** (new capabilities),
each tagged with the personas who asked for it, a rough effort, a priority, and —
where relevant — the hard rule it serves or threatens.

This is written to the project's standard: it names what is genuinely missing,
does not flatter the current build, and explicitly marks the things we should
**refuse** to build (the anti-features) so the backlog has a conscience.

> Scope note: the product reviewed is the post-merge state of `main` — the
> two-map exposure-vs-counts view, the accessible sortable table, the bilingual
> chrome, the BikeMaps/OSM/exposure real-data tools, the Davis & Sacramento real
> configs, and the metadata-driven provenance banner. Personas are synthetic and
> perform expert cognitive walkthroughs, not live assistive-technology or field
> testing; their findings are hypotheses to validate, not measurements.

> **Implementation status (updated 2026-06-20).** A first and second cut of the
> self-contained, no-new-privacy-surface items are already shipped: **R1/R45**
> (FAQ), **R8** (screen-reader hotspot summary), **R16** (Spanish provenance
> banner), **R22** (dataset download), **R2** (header glossary tooltips), **R6**
> (modeled-exposure flag surfaced), **R10** (single-map toggle), **R11/R27**
> (earlier map stacking), **R20** (per-segment deep links from the summary),
> **R21** (table name filter), **R3 + partial R28** (the
> [limitations page](../LIMITATIONS.md), incl. the CI-scope caveat), **R4/R5** (a
> plain-language "bottom line" callout), **R24** (hazard-type breakdown column),
> **R31** (a segment-ID join crosswalk in REAL-DATA.md), and **R46** (a
> methodology TL;DR). The gated big-ticket **R40–R44 / E13–E16** (contributor
> intake + abuse defense) is now **scoped** in
> [INTAKE-AND-ABUSE.md](../INTAKE-AND-ABUSE.md). Still deferred pending live data
> sources: R36/E10 exposure adapters, E5 official-collision fusion, E2
> before/after evaluation, E17/E18 API & tiles.

## Contents

- [Method & how to read this](#method--how-to-read-this)
- [Persona roster](#persona-roster)
- [Part 1 — The interviews](#part-1--the-interviews)
- [Part 2 — Remediations (fix what ships)](#part-2--remediations-fix-what-ships)
- [Part 3 — Expansions (new capability)](#part-3--expansions-new-capability)
- [Part 4 — Cross-cutting themes](#part-4--cross-cutting-themes)
- [Part 5 — Prioritization](#part-5--prioritization)
- [Part 6 — Anti-features (what we should refuse to build)](#part-6--anti-features-what-we-should-refuse-to-build)
- [Appendix — interview protocol & limitations](#appendix--interview-protocol--limitations)

## Method & how to read this

Each persona was given the same five-question protocol (see appendix): first
impression, the one thing that would make them trust/abandon the tool, the task
they came to do and whether they could, what they'd fix, and what they wish
existed. Findings are merged across personas; an item asked for by many is not
automatically higher priority, but breadth is recorded.

- **Remediations** are numbered `R#`, **expansions** `E#`. IDs are stable
  references for the issue tracker.
- **Effort**: S (hours), M (days), L (weeks), XL (multi-month / research).
- **Priority**: P0 (trust-critical / correctness), P1 (high value), P2 (valuable),
  P3 (speculative / long tail).
- **HR** tags reference the [five hard rules](../../README.md): HR1 no rate
  without a denominator; HR2 no estimate without an interval; HR3 reporting bias
  named, not hidden; HR4 contributor privacy; HR5 open & reproducible.

## Persona roster

| # | Persona | Cluster | Core goal |
|---|---|---|---|
| P01 | Local bike/ped **advocacy org lead** | Advocacy | Win a specific street redesign at council |
| P02 | **Safe Routes to School** parent volunteer | Advocacy | Prove the school-route crossing is dangerous |
| P03 | **Everyday cyclist** who wants to report a near-miss | Advocacy | Contribute what just happened to them |
| P04 | **E-bike delivery rider** (gig worker, time-poor) | Advocacy | Flag a recurring hazard fast, on a phone |
| P05 | Neighborhood association **volunteer** (non-technical) | Advocacy | Understand their block at a glance |
| P06 | City **Vision Zero coordinator / traffic engineer** | Government | Defend a project list to a skeptical public |
| P07 | **City council member** (elected, non-technical) | Government | Decide where money goes, defensibly |
| P08 | **MPO/regional planner** (SACOG-type) | Government | Compare cities; feed a regional plan |
| P09 | Public works **GIS analyst** | Government | Join the data to the city basemap in QGIS |
| P10 | Public health **epidemiologist** | Government | Use rates + CIs in a health-equity report |
| P11 | **Open-data journalist** | Data/Research | Verify a claim and publish a story |
| P12 | **Academic transportation researcher** | Data/Research | Cite the method; reproduce the numbers |
| P13 | Civic-tech **open-source contributor** | Data/Research | Stand the tool up for their own city |
| P14 | **GIS power user** (QGIS/ArcGIS) | Data/Research | Style and analyze the GeoJSON |
| P15 | **Data skeptic / adversarial reviewer** | Data/Research | Find the flaw that discredits the map |
| P16 | **Blind screen-reader** user (NVDA/VoiceOver) | Access | Get every finding without the map |
| P17 | **Low-vision** user at 200% zoom | Access | Read rates and significance, reflowed |
| P18 | **Spanish-monolingual** resident | Access | Use the whole tool in Spanish |
| P19 | **Wheelchair / mobility-device** user | Access | Find sidewalk & crossing hazards |
| P20 | **Older adult**, low digital literacy | Access | Not get lost; trust what they see |
| P21 | **Micromobility operator** (bike-share/scooter) | Adjacent | Risk-flag their service area |
| P22 | **Insurer / actuary** | Adjacent | Sanity-check exposure-normalized risk |
| P23 | **Privacy/security researcher** | Risk | Try to re-identify a reporter |
| P24 | **Funder / grant program officer** | Risk | See evidence of impact before funding |

(Plus a standing **threat-model red-team** lens, folded into P23, that actively
tries to abuse intake and poison the data.)

## Part 1 — The interviews

Compact transcripts. Each: who they are, their read on the current build, what
they'd fix, what they want next, and one verbatim line.

### P01 — Advocacy org lead
- **Now:** "The two-map view is the argument I've been making for years — the
  busy street isn't the dangerous one. *That* I can put on a slide." But the live
  site is still the Davis synthetic demo, and she can't point councillors at her
  own city without engineering help.
- **Fix:** A share/export path — a clean PNG or PDF of the two maps + the ranked
  table for a specific corridor, with the caveats baked in. Right now she'd
  screenshot, losing the table and the CIs.
- **Next:** Before/after evaluation — "we got a bike lane on 5th; did the rate
  drop?" — and a permalink to a single segment she can paste into an email.
- **Quote:** "I don't need it to be pretty. I need it to survive cross-examination
  from a traffic engineer who doesn't want the project."

### P02 — Safe Routes to School parent
- **Now:** Cares about *one* crossing at *one* time of day. The published data has
  no time dimension (HR4 suppresses per-report timestamps), so "dangerous at the
  3pm bell" is invisible. The map is cyclist-framed; her kids walk.
- **Fix:** Make pedestrian/mode framing first-class, not cyclist-default; let her
  filter the table to her school's blocks.
- **Next:** A time-of-day / school-hours lens (aggregated, privacy-safe bands),
  and a "report on behalf of my kid's route" flow.
- **Quote:** "Everyone *knows* that corner is awful. I need the chart that makes
  the city admit it."

### P03 — Everyday cyclist (would-be contributor)
- **Now:** Wants to report the truck that just buzzed her. There is **no report
  form on the site** — intake is a JSON schema and a CLI. She has no path in.
- **Fix:** Ship an actual accessible, mobile-first report form wired to intake.
- **Next:** Offline capture (report in the dead zone, sync later), optional photo,
  and a "your report helped flag B St" acknowledgement.
- **Quote:** "I'm standing at the curb with adrenaline and a phone. If it's more
  than 20 seconds, it didn't happen."

### P04 — E-bike delivery rider
- **Now:** Time-poor, gloves on, often in Spanish. Even if a form existed, typing
  is the enemy. Worried that reporting could expose his route to a boss or a cop.
- **Fix:** Privacy explainer *before* the first field, not buried in a threat
  model doc; one-tap hazard-type + pin.
- **Next:** Voice/quick-tap report; SMS or low-data fallback; assurance that home
  and shift patterns are fuzzed (they are — HR4 — but he doesn't know that).
- **Quote:** "Tell me in one sentence you won't get me deported or fired, or I'm
  out."

### P05 — Neighborhood association volunteer
- **Now:** Finds the table authoritative but dense; "Getis-Ord Gi*" and "95% CI"
  are a wall. Doesn't know why his obviously-busy street ranks low.
- **Fix:** A plain-language "why isn't my street red?" explainer and a glossary
  tooltip on every stats term.
- **Next:** A neighborhood summary card in normal words ("3 of 12 blocks are
  statistically hotter than traffic explains").
- **Quote:** "I trust it more *because* it's careful, but I can't explain it to my
  neighbors yet."

### P06 — Vision Zero coordinator / traffic engineer
- **Now:** The skeptic the schema was written for. Respects exposure
  normalization, CIs, FDR, and the "exposure unknown" honesty. But: crowdsourced
  near-misses aren't his official KABCO collisions, and he won't swap them in.
- **Fix:** Show crowdsourced near-miss **next to** official collision data, not
  instead of it; expose the snapping/dedup thresholds and a sensitivity note.
- **Next:** SWITRS/TIMS (official CA collision) fusion; a documented crosswalk to
  MMUCC/KABCO; exportable methodology appendix for a staff report.
- **Quote:** "Show me it agrees with my collision data where I have it, and I'll
  believe it where I don't."

### P07 — City council member
- **Now:** 90 seconds of attention. The lede is good; the table is too much. Wants
  the bottom line and the catch.
- **Fix:** A one-screen "bottom line + top 3 hotspots + what this can't tell you."
- **Next:** A printable one-pager per district; a confidence badge they can
  defend ("statistically significant, not just loud").
- **Quote:** "Give me the sentence I say into the microphone, and the footnote for
  when someone challenges it."

### P08 — MPO / regional planner
- **Now:** Has Davis *and* wants Sacramento, Yolo, the whole region. Each city is
  a separate config and a separate published file; there's no regional roll-up or
  cross-city comparison, and `segment_id`s aren't comparable across cities.
- **Fix:** A multi-city index / directory page; consistent regional segment IDs.
- **Next:** Regional aggregation with per-jurisdiction breakdowns; a corridor that
  crosses city lines treated as one corridor.
- **Quote:** "My plan is regional. Your unit of analysis is one city's block."

### P09 — Public works GIS analyst
- **Now:** Loves that it's plain GeoJSON with embedded metadata. Loads in QGIS
  fine. But `osm-w<way>-<block>` IDs don't join to his city centerline file, and
  there's no stable join key or LRS measure.
- **Fix:** Document a join recipe; emit an optional crosswalk to OSM way IDs and a
  conflation hint to a local centerline.
- **Next:** Versioned releases with a changelog so he can diff quarter over
  quarter; a GeoPackage export option.
- **Quote:** "Your IDs are yours. Mine are mine. Give me the Rosetta stone."

### P10 — Public health epidemiologist
- **Now:** The rate+CI framing is exactly her language. But exposure is treated as
  a known constant — there's no uncertainty on the *denominator*, which she knows
  is the shakiest number.
- **Fix:** Propagate exposure uncertainty into the rate CI (or state explicitly
  that the CI is Poisson-on-counts only).
- **Next:** Empirical-Bayes / spatial smoothing for small areas; an equity overlay
  (income, race) done carefully to surface *under*-reporting, not to stigmatize.
- **Quote:** "Your numerator has error bars. Your denominator pretends it doesn't."

### P11 — Open-data journalist
- **Now:** Wants to verify and publish today. `make reproduce` is a dream come
  true. But there's no download button on the site, no per-segment permalink to
  cite, and the live data is still the demo.
- **Fix:** A visible "download this dataset (GeoJSON/CSV) + checksum" affordance;
  deep links to a segment and a sorted view.
- **Next:** A machine-readable changelog/version feed; an embeddable map for the
  article.
- **Quote:** "If I can't link to the exact row and re-run the number, I can't
  print it."

### P12 — Academic researcher
- **Now:** Pure-Python, documented methods, ADRs, CITATION.cff — she's delighted.
  Wants to cite a versioned release and a DOI.
- **Fix:** Tag releases; mint a DOI (Zenodo); pin method parameters in the
  citation.
- **Next:** A benchmark/validation set comparing crowdsourced near-miss against
  official collisions (the leading-indicator question); a documented power
  analysis for "how many reports until a block is rankable."
- **Quote:** "Reproducible is necessary. Citable and validated is what gets it
  into my paper."

### P13 — Civic-tech contributor
- **Now:** Can stand up a new city via config — but only if they can fetch
  BikeMaps + OSM + *exposure*, and exposure is a manual CSV they have to source.
  That's the wall.
- **Fix:** A guided "new city" wizard/checklist; a sample exposure file and a
  Strava-Metro/counts adapter stub.
- **Next:** One-command city bootstrap from a bbox; a public gallery of
  community-contributed cities with a quality badge.
- **Quote:** "I got two of three inputs in ten minutes. The third took a week of
  emails."

### P14 — GIS power user
- **Now:** Styling by rate works; wishes the `hazard_breakdown`, exposure source,
  and CI bounds were all attributes he could drive symbology from (some are
  suppressed for small-n, correctly).
- **Fix:** Document every published attribute and its null semantics in one table;
  ship a QGIS style file (.qml).
- **Next:** Vector tiles / PMTiles for big cities so it doesn't choke at regional
  scale.
- **Quote:** "Give me the attribute table and a .qml and I'll make you a better
  map than your website."

### P15 — Data skeptic / adversarial reviewer
- **Now:** Attacks the exposure layer (modeled fallback = "made up"), the snapping
  radius, MAUP (the block is an arbitrary unit), and crowdsourcing self-selection
  bias. The project already concedes most of these — which disarms him.
- **Fix:** A single "limitations & how to attack this" page that pre-states every
  objection and the project's answer; surface the modeled-fallback flag in the UI,
  not just the data.
- **Next:** MAUP sensitivity (re-segment and show rank stability); a bias-audit
  panel from `bias.py` made visible.
- **Quote:** "I came to dunk on it and it had already written my tweet for me.
  Annoying. Effective."

### P16 — Blind screen-reader user
- **Now:** The table-is-authoritative contract is the right architecture. Sort
  buttons + live region are good. But the two `<div>` maps are decorative noise to
  him, and there's no spatial text equivalent ("the hotspots are clustered on 5th
  between C and E").
- **Fix:** Confirm the maps are properly hidden/described; add a generated
  prose summary of the hotspot geography. Real NVDA/VoiceOver pass still pending.
- **Next:** "Hotspots near an address" text query; keyboard jump between table and
  a per-segment detail.
- **Quote:** "I don't need your map described pixel by pixel. I need the *finding*
  the map is for."

### P17 — Low-vision user (200% zoom)
- **Now:** Reflow and sticky headers help. Two side-by-side maps become tiny and
  the call-out labels collide at zoom.
- **Fix:** Stack maps earlier; let the user switch to a single-map toggle;
  ensure labels don't overlap at zoom.
- **Next:** A high-contrast theme and a text-size control independent of browser
  zoom.
- **Quote:** "Two maps is one map too many when each is the size of a stamp."

### P18 — Spanish-monolingual resident
- **Now:** The toggle covers chrome and legends — genuinely bilingual, rare and
  good. But the new provenance banner interpolates the dataset's English
  `dataset_note`/`exposure_unit` strings even in Spanish.
- **Fix:** Localize (or provide a Spanish field for) the provenance note and
  exposure unit; translate quality-flag and hazard-type vocab fully.
- **Next:** More languages (the bias doc already flags language under-reporting);
  a Spanish-first reporting flow.
- **Quote:** "Casi todo está en español. Then one important line switches to
  English — the one that says if it's real."

### P19 — Wheelchair / mobility-device user
- **Now:** The schema *has* a `wheelchair` mode and sidewalk/`surface_hazard`
  types, but the data is BikeMaps cycling-centric, so his world (curb cuts, broken
  sidewalk, blocked crossings) is nearly absent.
- **Fix:** Don't imply coverage that isn't there; label the dataset's mode scope
  honestly per city (HR3).
- **Next:** A pedestrian/rolling intake source; surface `hazard_type` so sidewalk
  hazards are findable; exposure for walking/rolling, not just bikes.
- **Quote:** "Your near-miss is a close pass. Mine is a curb with no ramp at the
  only crossing for three blocks."

### P20 — Older adult, low digital literacy
- **Now:** The lede is readable; the table scares him; the two maps with sync
  pan/zoom are confusing ("which one is real?").
- **Fix:** A guided default view; clearer one-line captions; remove or label the
  map-sync surprise.
- **Next:** A "just tell me about my street" search box that returns a sentence.
- **Quote:** "I moved the left map and the right one moved too. I thought I broke
  it."

### P21 — Micromobility operator
- **Now:** Sees commercial value in segment risk for their service area; worried
  about liability if they *use* a hazard they could see.
- **Fix:** Clear license + "not for safety-critical routing" disclaimer; stable
  API expectations.
- **Next:** A read API / bulk endpoint; webhook on new hotspots in a geofence.
- **Quote:** "If your data says a corner is bad and we route riders into it, that's
  discovery in a lawsuit. Help me not do that."

### P22 — Insurer / actuary
- **Now:** Likes exposure normalization (it's literally their job) but flags that
  self-reported near-misses aren't claims; severity is unverified.
- **Fix:** Keep the near-miss/collision distinction loud; never present severity
  as verified (already the stance — keep it).
- **Next:** Severity-weighted (KSI) rate option; linkage to official outcomes for
  calibration.
- **Quote:** "A near-miss is a signal, not a loss. Don't let anyone price it like
  one."

### P23 — Privacy/security researcher (red team)
- **Now:** Probes for re-identification: rare `hazard_type` on a low-traffic block,
  k-anon threshold, jitter, metadata leakage. The published artifact withholds
  timestamps/coords and suppresses small-n breakdowns — solid. He pushes on the
  *intake-to-scale* future: a public form invites floods and doxxing-by-report.
- **Fix:** Document the re-identification model for rare hazard types; make k and
  jitter parameters and their rationale visible.
- **Next:** Abuse/spam/astroturf defenses for any public intake; rate-limiting;
  a moderation queue; an outlier/poisoning detector — *before* opening a form.
- **Quote:** "Your published file is careful. The moment you accept public
  reports, your threat model triples. Plan it now, not after."

### P24 — Funder / grant officer
- **Now:** Impressed by rigor and openness; can't yet see *adoption* or *outcomes*.
- **Fix:** A short impact/usage page (cities live, datasets published, council
  citations) — privacy-respecting, not surveillance analytics.
- **Next:** Before/after intervention case studies; a logic model tying the tool
  to safer-street decisions.
- **Quote:** "Rigor gets you a meeting. Evidence that a city *acted* gets you the
  check."

## Part 2 — Remediations (fix what ships)

Grouped by theme. Each: `R# — what` · personas · effort · priority · notes.

### A. Trust, framing & explanation
- **R1 — "Why isn't my busy street red?" explainer** (the core counterintuitive
  message) as a first-class page + inline link. · P05,P07,P20,P01 · S · **P0**
- **R2 — Glossary tooltips** on Rate/1000, 95% CI, Gi*, FDR, exposure, n. · P05,P07,P10 · S · P1
- **R3 — "What this can't tell you" / limitations page** that pre-states every
  attack (MAUP, self-selection, exposure quality, near-miss≠collision). · P15,P06,P22 · M · **P0** · HR3
- **R4 — Council one-screen summary**: bottom line + top 3 + the catch. · P07,P01 · M · P1
- **R5 — Neighborhood/plain-language summary card** ("3 of 12 blocks hotter than
  traffic explains"). · P05,P20 · M · P1
- **R6 — Surface the modeled-exposure fallback in the UI**, not only in the data
  source string; flag affected segments visibly. · P15,P10 · S · **P0** · HR1/HR3
- **R7 — Make the near-miss≠collision distinction unmissable** in the UI, not just
  docs. · P06,P22 · S · P1 · HR3

### B. Accessibility (beyond current AA targets)
- **R8 — Generated prose hotspot-geography summary** for screen-reader users
  ("significant hotspots cluster on 5th St between C and E"). · P16 · M · **P0**
- **R9 — Confirm/repair map containers are correctly hidden or described** to AT;
  remove decorative noise. · P16 · S · **P0**
- **R10 — Single-map toggle** (show one map at a time). · P17,P20 · S · P1
- **R11 — Stack the two maps earlier / responsive at 200% zoom**; fix label
  collision at zoom. · P17 · S · P1
- **R12 — High-contrast theme + independent text-size control.** · P17,P20 · M · P2
- **R13 — Tame the map-sync surprise** (label it, or make it opt-in). · P20,P17 · S · P2
- **R14 — Keyboard jump between table ⇄ map ⇄ per-segment detail.** · P16,P17 · M · P2
- **R15 — Run the real NVDA + VoiceOver + zoom pass** still listed open in the
  ACR; convert structural predictions to measured results. · P16,P17 · M · **P0**

### C. Internationalization
- **R16 — Localize the provenance banner** (don't interpolate English
  `dataset_note`/`exposure_unit` into Spanish). · P18 · S · **P0**
- **R17 — Fully translate hazard-type & quality-flag vocab** (not just chrome). · P18,P04 · S · P1
- **R18 — Per-city / per-dataset localized metadata fields** (note_es, unit_es). · P18 · M · P2 · HR5
- **R19 — Spanish-first (and beyond-ES) reporting path** once intake exists. · P18,P04 · M · P2

### D. Map / web UX
- **R20 — Per-segment permalink + deep link to a sorted/filtered view.** · P11,P01,P09 · S · P1
- **R21 — Table filter/search** (by name, hazard type, significance, flags) — today
  it only sorts. · P02,P05,P14 · M · P1
- **R22 — Visible "download dataset (GeoJSON/CSV) + checksum"** affordance. · P11,P14,P12 · S · P1 · HR5
- **R23 — Print/PDF/PNG export** of the two maps + ranked table with caveats baked
  in (for council). · P01,P07 · M · **P1**
- **R24 — Surface `hazard_type` / breakdown** where not suppressed, so sidewalk &
  dooring hazards are findable. · P19,P02,P14 · S · P1
- **R25 — Offline/poor-connection grace**: when tiles fail, say so and keep the
  vector segments legible (mostly true today — make it explicit). · P04,P20 · S · P2
- **R26 — Dark mode / `prefers-color-scheme`.** · P17 · S · P3
- **R27 — Mobile layout pass** for the split view (stacking, label density). · P04,P17 · M · P1

### E. Data integrity & method honesty
- **R28 — State the CI's scope** (Poisson-on-counts; exposure treated as fixed) or
  propagate exposure uncertainty into it. · P10,P15 · L · **P0** · HR2
- **R29 — Snapping/dedup threshold transparency + sensitivity note** per city. · P06,P15 · M · P1 · HR5
- **R30 — Document every published attribute + null semantics** in one table; ship
  a `.qml` QGIS style. · P14,P09 · S · P1 · HR5
- **R31 — Stable, documented join key / crosswalk** from `osm-w…` IDs to OSM way
  IDs and a local centerline conflation hint. · P09,P08 · M · P1
- **R32 — Versioned releases + machine-readable changelog/diff** of published
  data. · P09,P11,P12 · M · P1 · HR5
- **R33 — Honest per-city mode-scope label** (this city is cycling-only; pedestrian
  coverage is sparse). · P19,P06 · S · **P0** · HR3
- **R34 — Power/"how many reports until rankable" note** per the small-n gate. · P12,P05 · M · P2 · HR2
- **R35 — Tag a release + mint a DOI** (Zenodo) with pinned method params. · P12 · S · P1 · HR5

### F. Pipeline & exposure (the gating input)
- **R36 — Exposure source adapters** beyond manual CSV: a Strava-Metro stub, a
  counts-portal (CA AT / SACOG) loader, documented. · P13,P06,P10 · L · **P1** · HR1
- **R37 — Sample exposure file + "new city" checklist/wizard** so the third input
  isn't a week of emails. · P13 · M · **P1**
- **R38 — Multi-city directory / index page** + consistent regional IDs. · P08,P13 · M · P1
- **R39 — One-command city bootstrap** from a bbox (streets+reports+exposure
  scaffold). · P13 · M · P2 · HR5

### G. Contributor intake (today: none on the web)
- **R40 — Ship an accessible, mobile-first report form** wired to `intake`. · P03,P04,P02 · L · **P0**
- **R41 — Privacy explainer *before* the first field** (one sentence, plain). · P04,P03 · S · **P0** · HR4
- **R42 — One-tap hazard-type + map pin; minimal typing.** · P04,P03 · M · P1
- **R43 — Reporter acknowledgement loop** ("your report helped flag B St"). · P03 · M · P2
- **R44 — Abuse/spam/rate-limit/moderation design _before_ opening intake.** · P23 · L · **P0** · HR4

### H. Documentation & comms
- **R45 — FAQ** (busy≠dangerous, near-miss vs collision, why "exposure unknown").
  · P05,P07,P15 · S · P1
- **R46 — Methodology one-pager** (exportable) for staff reports. · P06,P07 · S · P1
- **R47 — Re-identification model for rare hazard types** documented; k & jitter
  rationale visible. · P23 · M · P1 · HR4
- **R48 — Bias-audit panel** from `bias.py` made visible (who's over/under-
  represented). · P15,P10,P19 · M · P1 · HR3

*(R49–R70: the long tail — emit GeoPackage; .qml + Mapbox/Leaflet style presets;
embeddable iframe widget; per-district printable; "report on behalf of a route";
school-hours aggregated band; confidence badge component; segment detail page;
copy-as-citation button; keyboard shortcut help; reduced-motion audit of pan
animations; focus-trap audit on the maps; alt text for exported images;
hreflang tags; sitemap; OpenGraph share card; robots/AI-crawler policy;
"last updated" + freshness indicator; data-quality score per city; null-island/
outlier guard surfaced; unit tests for the web i18n template interpolation;
a11y regression CI on the real DOM, not just static. Each S–M, P2–P3, sourced
from the personas above.)*

## Part 3 — Expansions (new capability)

### I. Temporal & evaluation
- **E1 — Multi-period publishing + trend view** (rate over releases), privacy-safe
  bands only. · P02,P08,P12 · L · **P1**
- **E2 — Before/after intervention evaluation** ("did the 5th St bike lane cut the
  rate?") — the killer advocacy + funder feature. · P01,P24,P06 · XL · **P1**
- **E3 — Time-of-day / day-of-week aggregated lens** (k-anon bands, no per-report
  times). · P02,P06 · L · P2 · HR4
- **E4 — Seasonality / weather context** (BikeMaps carries weather). · P12 · L · P3

### J. Data fusion & validation
- **E5 — Official collision fusion (SWITRS/TIMS for CA)** → a tri-view: naive
  counts vs exposure-corrected near-miss vs official collisions. · P06,P12,P22 · XL · **P1**
- **E6 — Leading-indicator validation**: test near-miss density as a predictor of
  future collisions; publish the validation. · P12,P06 · XL · P1
- **E7 — Equity overlay** (income/race/ADA) to surface *under*-reporting bias,
  handled with care and consent. · P10,P19,P15 · L · P2 · HR3
- **E8 — Severity-weighted (KSI) rate option** alongside count-rate. · P22,P06 · M · P2
- **E9 — Empirical-Bayes / spatial smoothing** for small-area stability. · P10,P12 · L · P2 · HR2

### K. Exposure (deepen the denominator)
- **E10 — Strava Metro integration** (governments) + modeled-exposure model that
  beats the flat prior (network + population + land use). · P10,P13,P06 · XL · **P1** · HR1
- **E11 — Exposure uncertainty propagation** into the rate interval. · P10 · L · P1 · HR2
- **E12 — Pedestrian/rolling exposure** (walk/roll counts), not just bikes. · P19,P02 · L · P2

### L. Contributor platform
- **E13 — Reporting PWA**: offline capture, optional photo, voice/quick-tap,
  privacy-by-default, sync later. · P03,P04 · XL · **P1** · HR4
- **E14 — Low-tech intake paths** (SMS / QR-at-the-curb / printable card). · P04,P19 · L · P3
- **E15 — Moderation + anti-astroturf toolkit** (outlier/poisoning detection,
  reporter-token bias, rate limits, review queue). · P23 · XL · **P0-for-launch** · HR4
- **E16 — "Report on behalf of a route/school"** guided flows. · P02,P19 · M · P2

### M. Platform, API & distribution
- **E17 — Read-only API / bulk endpoints + webhooks** on new hotspots in a
  geofence. · P21,P11,P13 · L · P2 · HR5
- **E18 — Vector tiles / PMTiles** for regional-scale rendering. · P14,P08 · L · P2
- **E19 — Embeddable map widget + share-card image generator.** · P11,P01 · M · P1 · ✅ shipped 2026-07-02 (embed iframe/JS widget + framework-free client-side canvas share-card generator, `web/share-card.js`, wired into `index.html`/`app.js`)
- **E20 — Multi-city / regional roll-up portal** with per-jurisdiction breakdowns
  and a community-city gallery + quality badge. · P08,P13,P24 · L · P1
- **E21 — Opt-in alert areas / notifications** (BikeMaps-style geofenced alerts),
  privacy-preserving. · P21,P01 · L · P3 · HR4

### N. Decision-support & outcomes
- **E22 — Countermeasure catalog**: link a hotspot to evidence-based fixes (NACTO /
  CMF) with expected effect. · P06,P01 · L · P2
- **E23 — Export to 311 / city work-order systems.** · P06,P09 · L · P3
- **E24 — Impact/usage page** (cities live, datasets, citations) — privacy-
  respecting. · P24 · M · P1
- **E25 — "Safest route" (heavily caveated, opt-in research feature)** — see
  anti-features for the guardrails. · P21 · XL · P3

*(E26–E60: the long tail — DOI + release cadence; QGIS/ArcGIS plugin; R/Python
analysis package; Jupyter case-study notebooks; corridor (multi-segment) analysis
unit; intersection-level analysis; conflation to city centerlines; demographic
context layers; air-quality/noise co-mapping; school catchment overlay; transit-
stop overlay; crash-typing ML assist for free-text notes; multilingual NLP for
notes; image-based hazard classification (privacy-bounded); federated multi-city
benchmarking; data-trust / community governance model; contributor reputation
(privacy-safe); "adopt-a-corridor" advocacy campaigns; council-packet generator;
open-data portal harvesting (Socrata/ArcGIS Hub) adapters; international cities &
RTL; accessibility-of-the-network analysis for mobility-device users; sidewalk
inventory integration; signal-timing data joins; e-bike/scooter class breakdowns;
weather-normalized rates; pandemic/again-event baselining; synthetic-control
evaluation; a "confidence over time" view; a public methods changelog feed;
a teaching mode for classrooms. Each tagged to personas above; mostly P2–P3,
L–XL.)*

## Part 4 — Cross-cutting themes

1. **Exposure is the franchise and the bottleneck.** Nearly every government,
   research, and contributor persona hits the same wall: the denominator. The
   highest-leverage roadmap is *exposure depth* (E10, R36) — it's what separates
   this from a dot-map and what blocks every new city.
2. **The product is currently read-only; the community wants to write.** Three
   advocacy personas came to *contribute* and found no door (R40). Opening that
   door safely (R44/E15) is a privacy project, not a form — do it deliberately.
3. **Trust is mostly won, then quietly lost on one screen.** The careful stats
   build credibility; then the English provenance line in Spanish (R16), the
   unexplained "why isn't my street red" (R1), and the dense table (R5) leak it
   back out. Cheap fixes, outsized trust impact.
4. **"Next to," not "instead of."** The engineer, the actuary, and the skeptic all
   say the same thing: don't replace official collision data — *triangulate* with
   it (E5). The two-map view should become a three-source view.
5. **Accessibility is architecturally right and empirically unverified.** The
   table-authoritative design is excellent; the SR prose-summary (R8) and the
   actual NVDA/VoiceOver pass (R15) are the gap between "designed for" and
   "works for."
6. **Honesty scales worse than features.** Every expansion (intake, equity
   overlays, routing, alerts) multiplies the HR3/HR4 surface. The anti-features
   list is part of the roadmap, not separate from it.

## Part 5 — Prioritization

**Now (P0 — trust/correctness, do before anything shiny):**
R1, R3, R6, R8, R9, R15, R16, R28, R33, R40, R41, R44. These are mostly *honesty
and access* fixes plus the safe foundation for intake.

**Next (P1 — high value, mostly S–M):**
R2, R4, R5, R7, R10, R11, R17, R20, R21, R22, R23, R24, R27, R29–R32, R35, R36,
R37, R38, R45–R48; E1, E2, E5, E10, E19, E20, E24.

**Later (P2–P3 — depth, scale, speculation):**
the remaining E-series (fusion depth, smoothing, PWA polish, API, tiles,
countermeasure catalog, routing-with-guardrails) and the R49–R70 long tail.

**Suggested first cut (a coherent ~2–3 week slice that moves trust the most):**
R1 + R3 + R45 (the explainer/FAQ/limitations triad), R16 + R17 (finish the
Spanish promise), R8 + R9 + R15 kickoff (the SR equivalent), R6 + R33 (don't
overclaim exposure/mode), and R20 + R22 + R23 (link it, download it, print it for
council). No new data sources, no new privacy surface — pure credibility and
usability on what already ships.

## Part 6 — Anti-features (what we should refuse to build)

A backlog without a conscience becomes a liability. These were raised (sometimes
*wanted*) by personas and should be declined or built only with hard guardrails:

- **Turn-by-turn "safest route" as a product** (P21): self-reported near-misses
  are a biased signal; routing people on them invites both liability and a
  feedback loop. If ever built, ship as a clearly-labeled research toy with the
  near-miss≠collision caveat front and center (E25), never as guidance.
- **Per-reporter dashboards / gamification leaderboards**: re-identification and
  perverse-incentive risk (report flooding). Violates HR4 in spirit.
- **Pinpoint "dangerous driver / license-plate" reporting**: turns a safety tool
  into surveillance/harassment; out of scope, by design.
- **Real-time raw incident feed**: precise time+place is exactly what HR4
  withholds; aggregation is the product, not a limitation to remove.
- **Selling exposure-normalized risk to insurers for pricing** (P22): a near-miss
  is a signal, not a loss; pricing individuals on it is both invalid and harmful.
- **"AI predicts the next crash" as a marketing claim**: E6 is a *validation
  study with error bars*, not a crystal ball; never let the framing outrun the
  evidence (HR2/HR3).
- **Auto-publishing community cities without review**: a quality/abuse vector;
  the gallery (E20) needs a human-reviewed quality badge, not open write.

## Appendix — interview protocol & limitations

**Protocol (same five questions per persona):**
1. In one breath, what is this and is it for you?
2. The single thing that would make you trust it — or close the tab?
3. The task you came to do: could you finish it on the current build?
4. The first thing you'd fix.
5. The thing you wish existed next.

**Limitations.** Personas are synthetic expert walkthroughs, not live users or
field tests; the access findings (P16–P20) are structural predictions pending
real NVDA/VoiceOver and zoom sessions (R15). Effort/priority are first-pass
estimates for triage, not commitments. The backlog is intentionally over-complete
("wildly comprehensive" was the brief); Part 5 and the anti-features list are how
it stays honest about what's actually worth doing.
