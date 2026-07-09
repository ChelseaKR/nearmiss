# Research-Backed Roadmap

> Companion to [`USER-RESEARCH.md`](USER-RESEARCH.md) (the synthetic,
> research-grounded persona panel, last assembled 2026-06-30). This roadmap turns
> that panel's frictions and wishes into a sequenced, **cited** backlog.

## Framing — what this complements

nearmiss already has **three** planning layers, and this roadmap is built to slot
*beside* them, not over them:

1. The **README Roadmap** (Phases 1–4: schema/intake/pipeline → exposure & honest
   statistics → publish & advocate → generalize). Largely delivered at beta.
2. The **2026-06-20 synthetic user-interview backlog**
   ([`research/2026-06-20-synthetic-user-interviews.md`](research/2026-06-20-synthetic-user-interviews.md)):
   24 personas, `R1–R70` remediations and `E1–E60` expansions, with a shipped-items
   list and an anti-features list.
3. The **per-doc known-gap notes** baked into
   [`METHODOLOGY.md`](METHODOLOGY.md) (the overdispersion check, the permutation
   Gi\* option, the exact-Poisson option) and [`LIMITATIONS.md`](LIMITATIONS.md)
   (CI scope, MAUP, mode scope, no time dimension).

This document's job is **not** to re-derive that 130-item backlog. It is the thin,
high-leverage slice the *external research literature* singles out — the items that
are about **statistical correctness, honest framing, and evidentiary grounding**,
each tied to a real source. Its IDs use a distinct namespace — **`RR-#`**
(remediations) and **`RE-#`** (expansions) — so they never collide with the prior
panel's `R-/E-`. Throughout, **[corroborates R#/E#]** means "independently
re-surfaced a prior backlog item, now with a citation behind it" and **[NET-NEW]**
means "the prior panels did not have an item for this."

Nothing here overturns the existing strategy; it sharpens the order and supplies
the evidence the earlier panel lacked.

---

## Research basis / evidence

All URLs accessed **2026-06-30**. High-stakes statistical/epidemiological claims
are corroborated by **≥2 independent sources**, as flagged.

**A. Near-miss reporting & the official-data gap**
- Nelson, Denouden, Jestico, Laberee, Winters. *BikeMaps.org: A Global Tool for
  Collision and Near Miss Mapping.* **Frontiers in Public Health**, 2015.
  "Near miss incidents are not reported by standard traffic data collection
  systems, but are a critical aspect of safety management."
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC4378118/>
- Branion-Calles, Nelson, Winters. *Comparing Crowdsourced Near-Miss and Collision
  Cycling Data and Official Bike Safety Reporting.* 2017.
  <https://www.researchgate.net/publication/321584062>

**B. Underreporting of vulnerable-road-user injury in police data — ≥2 sources**
- SafeTREC / UC Berkeley review of data-linkage studies: police reporting levels
  for bicyclist/pedestrian injury estimated at **~7–46%**.
  <https://safetrec.berkeley.edu/publications/evaluating-research-data-linkage-assess-underreporting-pedestrian-and-bicyclist-injury>
- COST TU1101 international survey: average **~10%** of bicycle crashes reported to
  police (range ~0% to ~35% across countries). **Accident Analysis & Prevention**.
  <https://pubmed.ncbi.nlm.nih.gov/29102034/>
- Toronto police-vs-health-service-utilisation comparison, 2016–2021.
  <https://pubmed.ncbi.nlm.nih.gov/38195658/>

**C. Exposure normalization & "safety in numbers" — ≥2 sources**
- Jacobsen. *Safety in numbers: more walkers and bicyclists, safer walking and
  bicycling.* **Injury Prevention**, 2003. (Per-person risk falls as numbers rise;
  doubling cyclists ≈ +32% collisions.) <https://pubmed.ncbi.nlm.nih.gov/26203162/>
- Elvik & Bjørnskau. *Safety-in-numbers: an updated meta-analysis of estimates.*
  **Accident Analysis & Prevention**, 2019. (Non-linear; **stronger at macro than
  micro level**; **causation not established**.)
  <https://www.sciencedirect.com/science/article/pii/S0001457519303641>
- Elvik. *"Safety in Numbers" re-examined.* 2010. (Confounding caveats.)
  <https://www.sciencedirect.com/science/article/abs/pii/S0001457510002484>
- FHWA. *Methods for estimating pedestrian and bicyclist exposure.* (Why exposure
  is the hard, decisive input.)
  <https://highways.dot.gov/safety/pedestrian-bicyclist/safety-tools/synthesis-methods-estimating-pedestrian-and-bicyclist-6>

**D. Self-selection / reporting bias in crowdsourced data**
- *Comparing bicyclists who use smartphone apps to record rides with those who do
  not: implications for representativeness and selection bias.* (App users
  oversample stronger/recreational riders; differ socio-demographically.)
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC6959852/>
- Nelson et al. *Crowdsourced data for bicycling research and practice.* **Transport
  Reviews**, 2021. <https://www.tandfonline.com/doi/full/10.1080/01441647.2020.1806943>

**E. Spatial-hotspot statistics & their pitfalls**
- Getis & Ord. *The analysis of spatial association by use of distance statistics.*
  **Geographical Analysis**, 1992. (The Gi\* statistic.)
  <https://onlinelibrary.wiley.com/doi/10.1111/j.1538-4632.1992.tb00261.x>
- Caldas de Castro & Singer. *Controlling the False Discovery Rate: ... Local
  Statistics of Spatial Association.* **Geographical Analysis**, 2006. (Spatially-
  aware FDR for many dependent local tests.)
  <https://onlinelibrary.wiley.com/doi/10.1111/j.0016-7363.2006.00682.x>
- *A Case Study on Kernel Density Estimation and Hotspot Analysis Methods in Traffic
  Safety Management.* IEEE. (KDE is sensitive to bandwidth, ignores network
  topology, doesn't natively use exposure.) <https://ieeexplore.ieee.org/document/9027448/>
- *The modifiable areal unit problem in traffic safety.* **J. Traffic &
  Transportation Engineering**, 2016. (Scale + zoning effects; do sensitivity
  analysis.) <https://www.sciencedirect.com/science/article/pii/S2095756415306322>

**F. Near-miss as a surrogate / leading indicator**
- Review of conflict-based surrogate safety measures: conflicts occur far more often
  than crashes, but predictive validity for crashes is an open question.
  <https://pmc.ncbi.nlm.nih.gov/articles/PMC10943440/>

**G. Vision Zero data practice & open-data ethics**
- Vision Zero Network. *Achieving Equity in Vision Zero Planning.* (Supplement
  police data with health & community sources; map under-representation.)
  <https://visionzeronetwork.org/achieving-equity-in-vision-zero-planning-a-framework-for-transformative-change/>
- SANDAG. *Systemic Safety: The Data-Driven Path to Vision Zero.*
  <https://www.sandag.org/-/media/SANDAG/Documents/PDF/projects-and-programs/regional-initiatives/vision-zero/systemic-safety-the-data-driven-path-to-vision-zero-2019-04-01.pdf>
- D'Ignazio & Klein. *Data Feminism* — counter-data / "the numbers don't speak for
  themselves." <https://data-feminism.mitpress.mit.edu/>
- *Enacting Data Feminism in Advocacy Data Work.* **CSCW**, 2023.
  <https://dl.acm.org/doi/10.1145/3579480>
- Gebru et al. *Datasheets for Datasets.* (Dataset-documentation ethic the data card
  already follows.) <https://arxiv.org/abs/1803.09010>

---

## Remediation backlog (sharpen / correct what ships)

Priority: **P0** trust/correctness · **P1** high value · **P2** valuable · **P3**
opportunistic. Effort: S ≈ afternoon · M ≈ day or two · L ≈ week+ · XL ≈
multi-month.

| ID | Remediation | Personas | Pri | Effort | Evidence / tag |
| --- | --- | --- | --- | --- | --- |
| RR-01 | **Cite the premise.** Add a referenced evidence base to `DATA-CARD.md`/`README` (and/or a short `RESEARCH.md`): VRU injury is recorded in police data at only ~7–46% (intl avg ~10%); near-misses by definition leave no official record. Turns the thesis from assertion to evidence. | P4,P6,P7,P8 | **P1** | S | B (≥2 srcs), A · **[NET-NEW]** |
| RR-02 | **Implement the overdispersion check** the methodology flags as a known gap: detect variance>mean and widen intervals via quasi-Poisson / negative-binomial instead of pure Poisson. Clustered report counts are otherwise too-narrow. | P8,P9 | **P0** | M | METHODOLOGY §4 · HR2 · **[NET-NEW]** |
| RR-03 | **Propagate exposure uncertainty into the CI** (or state the Poisson-on-counts scope louder, at each finding). The denominator is the shakiest input and currently treated as fixed. | P8,P9,P6 | **P0** | L | C, FHWA · HR2 · **[corroborates R28/E11]** |
| RR-04 | **Macro-vs-micro safety-in-numbers caveat in the brief.** State that exposure normalization removes the volume confound but a low per-segment rate on a busy corridor is **not** proof of safety (SiN is weak/contested at the micro scale). | P6,P9 | P1 | S | C (Elvik) · HR3 · **[NET-NEW]** |
| RR-05 | **MAUP rank-stability sensitivity.** Re-segment the network and report whether the top Gi\* hotspots survive; publish the rank-stability result, not just a caveat. | P9,P6,P10 | P1 | M | E (MAUP) · HR5 · **[NET-NEW]** (panel raised only in interview) |
| RR-06 | **Representativeness panel grounded in a named external baseline.** Make `bias.py` output visible and compare the reporter pool to a cited baseline (app users oversample strong/recreational riders; geographic age/gender skew), not just an abstract "bias exists." | P6,P8,P3 | P1 | M | D (≥2 srcs) · HR3 · **[corroborates R48/E7]** |
| RR-07 | **Honest per-city mode-scope label.** Mark each published dataset's real mode coverage (e.g. "cycling-only; pedestrian/rolling sparse") so "no reports" is never read as "safe." | P3,P2,P6 | **P0** | S | D, VZ-equity · HR3 · **[corroborates R33]** |
| RR-08 | **Spatially-aware FDR.** Justify (or move to) a spatial-dependence-aware FDR for the many local Gi\* tests, per Caldas de Castro & Singer, rather than vanilla Benjamini-Hochberg. | P9 | P2 | M | E (CdC&S 2006) · HR2 · **[NET-NEW]** |
| RR-09 | **Gi\* inference robustness.** Add a conditional-permutation reference distribution alongside the normal-approximation z-score (methodology already lists this as future work). | P9 | P2 | L | E, METHODOLOGY §8.2 · HR2 · **[NET-NEW]** |
| RR-10 | **Commit the hashed `requirements.lock`** so a clean clone reproduces published bytes for an outside reviewer (README admits it's generated-but-not-committed). | P10,P8 | P1 | S | G (datasheets), HR5 · **[NET-NEW]** |
| RR-11 | **Tag a versioned release + mint a Zenodo DOI** with pinned method params, so the dataset and method are citable. | P8,P10,P7 | P1 | S | G · HR5 · **[corroborates R35]** |
| RR-12 | **Document the re-identification model** for rare hazard-type combinations on low-traffic blocks; surface the `min_publish_n`/jitter rationale. | P12,P10 | P1 | M | THREAT-MODEL, G · HR4 · **[corroborates R47]** |
| RR-13 | **Finish the Spanish promise.** Localize the provenance/`exposure_unit` strings and hazard/quality vocab — the one English line in an otherwise-Spanish view leaks trust precisely with the LEP group that is already under-reported. | P2,P4 | P1 | S | D, VZ-equity · HR3 · **[corroborates R16/R17/R18]** |
| RR-14 | **Run the real NVDA/VoiceOver + 200% zoom pass** and commit results; convert ACR "Partially Supports" predictions to measured outcomes. | P11 | **P0** | M | ACCESSIBILITY/ACR · **[corroborates R15]** |
| RR-15 | **Open-data ethics / counter-data statement.** Name nearmiss as community counter-data, cite the framework, and state the consent + power posture (who the data is *for*, who it must not be used against). | P4,P13,P7 | P2 | S | G (Data Feminism) · HR3/HR4 · **[NET-NEW]** |

---

## Expansion backlog (new capability)

| ID | Expansion | Personas | Pri | Effort | Evidence / tag |
| --- | --- | --- | --- | --- | --- |
| RE-01 | **Official-collision validation study.** Fuse SWITRS/TIMS (CA) collisions and test whether exposure-normalized near-miss density predicts future collisions; publish **with error bars**, framed as a surrogate-safety leading indicator — never as a crystal ball. The single biggest credibility unlock for skeptical agencies. | P6,P8,P7,P5 | **P1** | XL | F, A · HR2/HR3 · **[corroborates E5/E6]** |
| RE-02 | **Empirical-Bayes / spatial smoothing** for small-area rate stability (borrow strength across neighbors to stabilize sparse segments). | P8,P9 | P2 | L | E, HR2 · **[corroborates E9]** |
| RE-03 | **Vision Zero "next to, not instead of" tri-view:** naive counts vs exposure-corrected near-miss vs official collisions, with a documented MMUCC/KABCO crosswalk. | P6,P5 | **P1** | XL | F, G (VZ) · **[corroborates E5]** |
| RE-04 | **Equity overlay** (income/race/language/ADA) to surface **under**-reporting, handled with consent and a data-feminism framing — to find who's missing, not to stigmatize a place. | P6,P8,P3 | P2 | L | D, G · HR3 · **[corroborates E7]** |
| RE-05 | **Pedestrian/rolling intake + walk/roll exposure** so disabled-pedestrian and walking hazards become first-class (not absent), with their own denominator. | P3,P2 | P2 | L | D, FHWA · HR1/HR3 · **[corroborates E12]** |
| RE-06 | **Council/advocacy export + permalink.** PNG/PDF of the two-map view + ranked table with caveats baked in, and a per-segment permalink — so a shared artifact can't have its legend stripped (the T4 misread defense). | P4,P5,P7 | **P1** | M | THREAT-MODEL T4 · **[corroborates R23/E19]** |
| RE-07 | **Exposure depth.** Strava-Metro / counts-portal (CA AT, SACOG) adapters + a modeled-exposure model that beats the flat prior — the input that distinguishes this from a dot-map. | P5,P8 | **P1** | XL | C, FHWA · HR1 · **[corroborates E10/R36]** |
| RE-08 | **Before/after & multi-period evaluation** ("did the 5th St lane cut the rate?"), with a synthetic-control / trend method and an honest confounding caveat. | P4,P6 | **P1** | XL | F, C · **[corroborates E1/E2]** |
| RE-09 | **Power / MDE note.** Publish "how many reports until a segment is rankable" per the small-n gate, so users know what the silence at low n means. | P8,P9 | P2 | M | E, HR2 · **[corroborates R34]** |
| RE-10 | **Anti-astroturf / abuse toolkit before any open form:** rate-limit, proof-of-work, per-source influence caps, burst/outlier detection, trust tiers — extend the shipped phase-1 moderation slice. **Gate the public form until this lands.** | P12 | **P0-for-launch** | XL | INTAKE-AND-ABUSE B2–B7 · HR4 · **[corroborates E15/R44]** |
| RE-11 | **Researcher reuse kit:** QGIS `.qml` style, an attribute + null-semantics table, GeoPackage/CSV export, and a machine-readable changelog/version feed. | P8,P10,P5 | P1 | M | G · HR5 · **[corroborates R30/R32]** |
| RE-12 | **Read-only API / embeddable widget** for journalists & operators, shipped *with* a prominent "not for safety-critical routing" disclaimer (honoring the anti-features list). | P7,P4 | P2 | L | F, panel anti-features · **[corroborates E17/E19]** |

---

## Sequenced roadmap

**Now — correctness & evidentiary grounding (cheap, protects the franchise).**
RR-01 (cite the premise), RR-02 (overdispersion), RR-04 (micro-SiN caveat), RR-07
(mode-scope label), RR-10 (commit the lock), RR-14 (real SR pass). These are mostly
S–M, lean entirely on what ships, add no new privacy surface, and answer the
skeptics (P6, P9) and the reviewers (P8, P10, P11) directly.

**Next — defensibility & reuse.** RR-03 (exposure-uncertainty CI), RR-05 (MAUP
sensitivity), RR-06 (cited bias panel), RR-11 (release + DOI), RR-13 (finish
Spanish), RE-06 (council export + permalink), RE-09 (power note), RE-11 (reuse kit).

**Later — depth & scale (mostly XL, several gated).** RE-01 (collision validation),
RE-03 (VZ tri-view), RE-07 (exposure depth), RE-08 (before/after), RE-02 (EB
smoothing), RR-08/RR-09 (spatial FDR, permutation Gi\*), RE-04 (equity overlay),
RE-05 (pedestrian/rolling). **RE-10 (abuse toolkit) is a hard gate on opening
intake** — sequence it before any public-form expansion regardless of its size.

---

## Recommended first sprint

A coherent ~2-week slice that maximizes credibility per hour and ships nothing that
overclaims. All lean on existing infrastructure; none open a new privacy surface.

1. **RR-01 — Cite the premise.** Drop the underreporting and safety-in-numbers
   literature into the data card and README. One afternoon; it converts the whole
   project's thesis from "the author says" to "the field shows," and it's the thing
   the journalist (P7), the advocate (P4), and both planners (P5, P6) all asked for.
2. **RR-02 — Land the overdispersion check.** The one genuine statistical-
   correctness gap the methodology *itself* flags. Until it lands, intervals on
   clustered counts are too narrow — exactly what the data scientist (P9) and
   epidemiologist (P8) will catch. Highest-priority code change.
3. **RR-04 + RR-07 — Two honesty refinements.** The micro-vs-macro safety-in-
   numbers caveat in the brief, and the per-city mode-scope label. Afternoon-sized;
   they pre-empt the two most likely misreads ("busy street is safe", "no reports =
   safe sidewalk").
4. **RR-05 — MAUP rank-stability report.** Re-segment, show whether the top
   hotspots survive, publish it. This is the skeptic's (P9) strongest *live* attack;
   a reproducible artifact disarms it the way the limitations page already disarms
   the others.
5. **RR-10 + RR-11 — Commit the hashed lock + tag a DOI'd release.** Turns
   "reproducible in principle" into "reproducible and citable" for the reviewer
   (P10) and the academic (P8) — small, and it unblocks reuse and citation.

Bundle the afternoon-sized **RR-13** (finish Spanish) and **RR-15** (counter-data
statement) if time allows.

---

## Traceability matrix (persona → items)

| Persona | Remediations | Expansions |
| --- | --- | --- |
| P1 Bike commuter | — | RE-10 |
| P2 SRTS parent | RR-07, RR-13 | RE-05, RE-08 |
| P3 Wheelchair pedestrian | RR-06, RR-07 | RE-04, RE-05 |
| P4 Advocate | RR-01, RR-13, RR-15 | RE-06, RE-08, RE-12 |
| P5 Traffic engineer | — | RE-01, RE-03, RE-06, RE-07, RE-11 |
| P6 Vision Zero coord. | RR-01, RR-03, RR-04, RR-05, RR-06, RR-07 | RE-01, RE-03, RE-04, RE-08 |
| P7 Journalist | RR-01, RR-11, RR-15 | RE-06, RE-12 |
| P8 Epidemiologist | RR-01, RR-02, RR-03, RR-06, RR-10, RR-11 | RE-01, RE-02, RE-04, RE-09, RE-11 |
| P9 Data scientist | RR-02, RR-03, RR-04, RR-05, RR-08, RR-09 | RE-02, RE-09 |
| P10 Reproducibility reviewer | RR-05, RR-10, RR-11, RR-12 | RE-11 |
| P11 Screen-reader user | RR-14 | — |
| P12 Brigade / red-team | RR-12 | RE-10 |
| P13 Owner/maintainer | RR-15 | RE-10 |

---

## Validate with real users / risks

- **What would falsify this roadmap.** Real interviews could show planners (P5/P6)
  won't touch crowdsourced near-miss *at all* until RE-01's validation exists —
  which would promote RE-01 from "Later" to keystone. Or that the premise is already
  accepted in their world and RR-01 is wasted effort. Test RR-01, RE-01, and the
  mode-scope concern (RR-07) with **one real Vision Zero coordinator** first.
- **Highest-risk item: RE-10 (abuse toolkit) and anything that opens intake.** The
  threat model is explicit that public intake **triples** the attack surface
  (flooding, astroturf, doxxing-by-report, poisoning). Do **not** ship a public form
  ahead of the network-edge defenses; keep the closed/invite pilot until B2–B7 are
  built and fixture-tested. A red-team review (P12) gates the "open" phase.
- **Statistical items need a statistician's sign-off, not a persona's.** RR-02
  (overdispersion), RR-03 (exposure-uncertainty), RR-08 (spatial FDR), RR-09
  (permutation Gi\*), and RE-02 (EB smoothing) are correctness changes; validate
  them against the planted-hotspot fixtures and interval-coverage simulations, and
  have a real transport epidemiologist (P8) review the method — synthetic personas
  cannot certify a statistical method.
- **Equity work (RE-04) carries its own harm risk.** An equity overlay done badly
  stigmatizes neighborhoods instead of surfacing under-reporting; build it with the
  consent/co-design posture the data-feminism literature requires, or not at all.
- **Don't let validation framing outrun the evidence.** RE-01/RE-08 are *studies
  with error bars*, not "AI predicts the next crash." Near-miss is a surrogate whose
  predictive validity is an open question; the framing must say so (the anti-features
  list already forbids the crystal-ball pitch).

---

## Honest limits

This roadmap is derived from a **synthetic** panel and a literature scan, not field
research. The literature grounds *whether a need is real in the world* (e.g.,
underreporting is unambiguously real); it does **not** tell you *how many of each
stakeholder will adopt nearmiss* or *what they'd pay or do*. Effort and priority are
first-pass triage estimates, not commitments. The backlog is intentionally the thin,
research-defensible slice — it omits the long tail of UX, distribution, and
ecosystem items the [2026-06-20 panel](research/2026-06-20-synthetic-user-interviews.md)
already enumerates; consult that for breadth. Where this roadmap and the code or the
methodology disagree, **the code and its tests are authoritative** and this document
is the bug. Corrections and challenges are welcome via the repository — the analysis,
and the plan for it, are meant to be checked.

---
## Implementation status — 2026-06-30 (working tree, uncommitted)
Shipped this pass: **RR-02** overdispersion check (quasi-Poisson / negative-binomial — the methodology's flagged gap) · **RR-05** MAUP rank-stability artifact (`stats/maup.py`) · **RR-01** literature citations behind the underreporting premise. Verify: ruff + mypy + tests green (the `security` step flags a pre-existing `msgpack` CVE — bump to 1.2.1). Deferred: RE-01 official-collision validation (external data).
