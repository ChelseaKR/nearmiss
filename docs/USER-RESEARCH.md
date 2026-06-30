# User Research — Research-Backed Synthetic Persona Panel

> [!WARNING]
> **These personas and interviews are SYNTHETIC.** They are a structured
> brainstorming device — composite users modeling real audience segments for
> nearmiss — *not* interviews with real people. No real user said any of this.
> Treat every "quote" as a hypothesis to validate, not evidence of demand. This
> is consistent with how the project labels its synthetic *datasets* (see
> [`docs/research/`](research/) and the planted-hotspot fixtures): a synthetic
> instrument is useful for pressure-testing and useless as proof.
>
> **Last assembled: 2026-06-30.**

This panel **complements** the earlier, deliberately exhaustive
[2026-06-20 synthetic user interviews](research/2026-06-20-synthetic-user-interviews.md)
(24 personas; a `R1–R70` / `E1–E60` backlog). That panel was an internal expert
walkthrough with **no external evidence base**. This one is narrower and
**research-backed**: a smaller, fully-covered stakeholder cast whose frictions
and wants are each anchored to the published literature on near-miss reporting,
underreporting of vulnerable-road-user injury, exposure normalization, and
spatial-hotspot statistics. Where a finding restates a prior backlog item it is
tagged **[corroborates R#/E#]** (independent triangulation — and now with a
citation behind it); where it is genuinely new it is tagged **[NET-NEW]**. The
companion [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md) turns these into a
sequenced, cited backlog.

---

## Method

- **Sampling frame.** Every stakeholder who touches the *dataset and the analysis*
  (the product — not an app): the people who **report and advocate**, the people
  who **plan and decide**, the people who **reuse and research**, the people who
  **assure and audit**, and the person who **operates** it. Each persona maps to a
  real audience the README, data card, and threat model already name.
- **Protocol.** For each persona: a goal; a walkthrough of the **real** surfaces
  they would touch today (the two-map exposure-vs-counts view, the authoritative
  sortable table, the Byar/Poisson confidence intervals, the Getis-Ord Gi\* +
  Benjamini-Hochberg hotspots, `bias.py`, the `exposure unknown` honesty, the
  k-anonymity withholding, the bilingual brief, `make reproduce`, the BikeMaps/OSM
  fetchers, the Davis/Sacramento real configs, the accessible submit form +
  moderation queue); where they get stuck; what they want next; and the one thing
  that makes them adopt or walk.
- **Research basis.** Each interview's friction is checked against the evidence
  below, so the panel cannot quietly invent a need the literature contradicts —
  and high-stakes statistical/epidemiological claims are cross-checked against
  **≥2 reputable sources**. Full citations and the roadmap mapping are in
  [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md#research-basis--evidence); the
  anchors most load-bearing for this panel (all accessed **2026-06-30**):
  - **Near-miss reporting & the official-data gap** — Nelson et al., *BikeMaps.org:
    A Global Tool for Collision and Near Miss Mapping*, **Frontiers in Public
    Health** (2015): "near miss incidents are not reported by standard traffic data
    collection systems, but are a critical aspect of safety management."
    <https://pmc.ncbi.nlm.nih.gov/articles/PMC4378118/>
  - **Underreporting of VRU injury in police data (≥2 sources)** — SafeTREC/UC
    review of data-linkage studies: police reporting levels for bicyclist injury
    estimated at **7–46%**
    (<https://safetrec.berkeley.edu/publications/evaluating-research-data-linkage-assess-underreporting-pedestrian-and-bicyclist-injury>);
    COST TU1101 international survey: **~10% average** reported to police (range
    ~0% to ~35%) (<https://pubmed.ncbi.nlm.nih.gov/29102034/>); Toronto police-vs-
    health-utilisation comparison, 2016–2021
    (<https://pubmed.ncbi.nlm.nih.gov/38195658/>).
  - **Exposure / "safety in numbers" (≥2 sources)** — Jacobsen, *Safety in numbers*,
    **Injury Prevention** (2003): doubling the number of cyclists is associated with
    only ~a third more collisions, so per-person risk falls
    (<https://pubmed.ncbi.nlm.nih.gov/26203162/>); Elvik & Bjørnskau,
    *Safety-in-numbers: an updated meta-analysis*, **Accident Analysis & Prevention**
    (2019): the effect is non-linear, **stronger at the macro than the micro level**,
    and causation is **not** established
    (<https://www.sciencedirect.com/science/article/pii/S0001457519303641>).
  - **Self-selection in crowdsourced cycling data** — app-recording cyclists
    oversample stronger/recreational riders and differ socio-demographically
    (<https://pmc.ncbi.nlm.nih.gov/articles/PMC6959852/>); review of crowdsourced
    bicycling data (<https://www.tandfonline.com/doi/full/10.1080/01441647.2020.1806943>).
  - **Spatial-hotspot pitfalls** — KDE is sensitive to bandwidth, ignores network
    topology, and does not natively incorporate exposure
    (<https://ieeexplore.ieee.org/document/9027448/>); MAUP makes hotspot results
    depend on the chosen areal unit
    (<https://www.sciencedirect.com/science/article/pii/S2095756415306322>);
    spatially-aware FDR control for local Gi\* tests (Caldas de Castro & Singer,
    *Geographical Analysis*, 2006)
    (<https://onlinelibrary.wiley.com/doi/10.1111/j.0016-7363.2006.00682.x>).
- **Synthesis.** Frictions → **remediations** (`RR-#`); wishes → **expansions**
  (`RE-#`), in [`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md). The `RR-/RE-`
  namespace is **deliberately distinct** from the prior panel's `R-/E-` so the two
  backlogs never collide; bare `R#/E#` references point at the 2026-06-20 panel.
- **Effort scale.** S ≈ an afternoon · M ≈ a day or two · L ≈ a week+ · XL ≈
  multi-month / research.

---

## Persona roster

| # | Persona | Group | Primary goal | Top friction (research-anchored) |
| --- | --- | --- | --- | --- |
| P1 | **Dana** — daily bike commuter, would-be reporter | Report & Advocate | Log the truck that just buzzed her | Near-misses leave no official record, yet the path in is a CLI/JSON to most users |
| P2 | **Marisol** — Safe-Routes-to-School parent (pedestrian) | Report & Advocate | Prove the school crossing is dangerous | Data is cyclist-centric; her kids walk; no time-of-day lens |
| P3 | **Theo** — manual-wheelchair pedestrian | Report & Advocate | Find curb-ramp / blocked-crossing hazards | Schema has `wheelchair` mode but BikeMaps coverage is near-zero for rolling |
| P4 | **Priya** — safe-streets advocate building a council campaign | Report & Advocate | Win a specific redesign, survive cross-examination | Live site is still the synthetic demo; screenshots strip the caveats |
| P5 | **Karim** — city traffic engineer / active-transport planner | Plan & Decide | Defend a project list with defensible evidence | Needs the method *next to* official data, not instead of it |
| P6 | **Dr. Okafor** — Vision Zero coordinator (self-report skeptic) | Plan & Decide | Not stake a plan on biased self-report | Crowdsourced near-misses ≠ KABCO collisions; wants validation |
| P7 | **Lena** — data / investigative journalist | Reuse & Research | Publish a claim she can defend | No download/permalink to cite; premise asserted, not sourced |
| P8 | **Prof. Halvorsen** — transport epidemiologist (dataset reuser) | Reuse & Research | Cite the method; reuse the rates+CIs | CI covers the count, not the denominator; no DOI |
| P9 | **Sam** — data scientist evaluating the statistics | Reuse & Research | Decide if the numbers survive scrutiny | Poisson assumed; overdispersion check not yet implemented |
| P10 | **Marcus** — open-data / reproducibility reviewer | Assure & Audit | Re-run and get byte-identical output | `requirements.lock` not committed; no tagged release |
| P11 | **Grace** — blind screen-reader user (NVDA), + low-vision lens | Assure & Audit | Get every finding without the map | Structural a11y is designed-for; manual SR pass still pending |
| P12 | **"the brigade"** — bad-faith reporter / astroturf threat | Assure & Audit | Manufacture (or bury) a hotspot | Public form invites flooding, doxxing-by-report, poisoning |
| P13 | **Chelsea** — owner / maintainer | Operate | Keep it honest, cheap, and unfundable-proof | Honesty scales worse than features; every expansion grows HR3/HR4 surface |

13 personas · 5 groups · every stakeholder type in the brief covered.

---

## Interviews

Compact transcripts. Each: **Goal · Values today** (real, shipped features) **·
Gets stuck · Wants next · Adopts / walks.** Frictions in *italics* are the ones
the literature directly supports.

### Group 1 — Report & Advocate

#### P1 — Dana, daily bike commuter (would-be contributor)
- **Goal.** Report the close pass that just happened, from the curb, in seconds.
- **Values today.** That the project exists at all: *near-misses leave no police
  report, so an official dataset literally cannot contain them* — Nelson et al.
  call this exactly the gap BikeMaps was built for. The accessible
  [`web/submit.html`](../web/submit.html) form + moderation queue is a real door
  in; the privacy posture (no name/email/account by construction) is reassuring.
- **Gets stuck.** The static-by-default deploy hands her report back to *download
  or copy and send to a maintainer* unless a serverless endpoint is wired — more
  than the "20 seconds with adrenaline" she has. The two-map view is framed for
  cyclists; fine for her, not for a friend on foot.
- **Wants next.** A one-tap hazard-type + pin with a true POST endpoint; offline
  capture; the "your report helped flag B St" acknowledgement.
- **Adopts if** reporting is genuinely sub-30s and her precise spot never goes
  public. **Walks if** it feels like a 311 queue that does nothing, or if she
  can't tell her exact location stays private. *(corroborates R40–R43)*

#### P2 — Marisol, Safe-Routes-to-School parent (pedestrian framing)
- **Goal.** Show the city that the 3 p.m. crossing by the school is dangerous.
- **Values today.** The exposure-normalized rate with a confidence interval is
  *exactly* the chart that beats "everyone knows that corner is bad" — and the
  bilingual (EN/ES) brief reaches her neighbors.
- **Gets stuck.** *The published dataset has no time dimension* — per-report
  timestamps are withheld under HR4, so "dangerous at the school bell" is
  invisible. The dataset is BikeMaps-sourced and *cyclist-centric*; pedestrian
  coverage in a given city may be sparse even though the schema supports it.
- **Wants next.** A privacy-safe aggregated time-of-day band; pedestrian framing
  as first-class; a table filtered to her school's blocks (the name filter
  shipped — extend to mode).
- **Adopts if** she can hand a council member one honest sentence + a footnote.
  **Walks if** the tool quietly implies pedestrian coverage it doesn't have.
  *(corroborates E3, R33)*

#### P3 — Theo, manual-wheelchair pedestrian
- **Goal.** Find the curb with no ramp, the blocked crossing, the heaved sidewalk.
- **Values today.** The report schema already carries a `wheelchair` mode and
  `surface_hazard` / `sightline` types; the honesty rules mean the project won't
  pretend to cover him if it doesn't.
- **Gets stuck.** *His world is nearly absent from the data.* BikeMaps is a
  cycling instrument; rolling and walking exposure aren't measured, so even if his
  hazards were reported there is no denominator to rate them against (HR1 →
  `exposure unknown`). Self-selection compounds it: the contributor pool skews to
  app-equipped, confident riders, not disabled pedestrians.
- **Wants next.** A pedestrian/rolling intake source; walk/roll exposure; an
  explicit per-city mode-scope label so absence isn't read as safety.
- **Adopts if** the dataset states plainly "this city is cycling-only; rolling
  coverage is sparse." **Walks if** it lets a city cite "no reports" on a sidewalk
  as evidence it's fine. *(corroborates R33, E12; HR3)*

#### P4 — Priya, safe-streets advocate building a council campaign
- **Goal.** Win a redesign on 5th St and survive a hostile traffic engineer.
- **Values today.** The two-map "busy ≠ dangerous" view *is the argument she's
  made for years*; the planted-fixture proof (the busy decoy `seg-03` ranks low on
  exposure-normalized rate while the genuinely-hot `seg-06` lights up) is the slide
  she wants. `make reproduce` means no one can wave it away.
- **Gets stuck.** The live site is still the **synthetic Davis demo**, so she
  can't point councillors at *her* city without engineering help. And a
  screenshot of the surface, *legend stripped*, becomes "the most dangerous
  street" — the exact misread the threat model (T4) warns about and cannot
  prevent once republished.
- **Wants next.** A council export (PNG/PDF of both maps + ranked table with the
  caveats baked in) and a per-segment permalink; the literature behind the premise
  cited so a skeptic can't call it activism with a map.
- **Adopts if** the export survives cross-examination. **Walks if** the only
  shareable artifact is a caption-less heat map. *(corroborates R23, E19; NET-NEW:
  cite-the-premise)*

### Group 2 — Plan & Decide

#### P5 — Karim, city traffic engineer / active-transport planner
- **Goal.** Add defensible evidence to a project list without overclaiming.
- **Values today.** He respects what most crowdsourced maps skip: exposure
  normalization, confidence intervals, Gi\* with FDR, the documented network
  spatial-weights, and the `exposure unknown` honesty. The GeoJSON loads straight
  into QGIS with embedded metadata.
- **Gets stuck.** He won't *swap* near-misses in for his KABCO/MMUCC collisions —
  and he's right not to: near-miss is a **surrogate** measure whose predictive
  validity for crashes is an open research question, not a settled one. He wants
  the snapping/dedup thresholds and a sensitivity note exposed.
- **Wants next.** Crowdsourced near-miss shown *next to* official collisions (a
  tri-view), a documented crosswalk to MMUCC/KABCO, an exportable methodology
  appendix for a staff report.
- **Adopts if** it agrees with his collision data where he has it. **Walks if** it
  asks him to treat self-report as ground truth. *(corroborates E5, R29; surrogate-
  safety literature)*

#### P6 — Dr. Okafor, Vision Zero coordinator (skeptical of self-report data)
- **Goal.** Build a High Injury Network she can defend, without staking it on a
  biased volunteer signal.
- **Values today.** That the project *names* its biases instead of hiding them
  (HR3, `bias.py`), refuses to publish a rate without a denominator (HR1), and
  withholds low-count segments (HR4). Vision Zero best practice is explicitly to
  **supplement** police data with health and community sources and to map
  under-representation — nearmiss is built in that spirit.
- **Gets stuck.** Self-selection is structural: the contributor pool oversamples
  confident, app-equipped, often recreational riders, so *streets used by
  under-represented groups are under-reported*, and exposure normalization fixes
  the **volume** confound, not the **who-reports** one. She also worries a low
  per-segment rate on a busy corridor will be read as "safe" — but safety-in-
  numbers is weak and contested at the **micro** (junction/segment) level even
  where it holds city-wide.
- **Wants next.** A validation against official collisions; an equity overlay that
  surfaces *under*-reporting (handled with consent, not stigma); the macro-vs-
  micro caveat written into the brief.
- **Adopts if** the dataset is positioned as a complement that admits its bias.
  **Walks if** it's pitched as a replacement for collision records. *(corroborates
  R48, E5, E7; NET-NEW: micro-SiN caveat)*

### Group 3 — Reuse & Research

#### P7 — Lena, data / investigative journalist
- **Goal.** Publish a checkable claim about where it's dangerous to ride.
- **Values today.** `make reproduce` is "a dream" — a number she can regenerate.
  The data card and limitations page pre-state the caveats so she won't get burned.
- **Gets stuck.** The site's *premise* — "vulnerable users absorb the risk and
  produce almost none of the data" — is asserted but **uncited**; her editor will
  ask for a source. There's a download affordance and per-segment deep links
  (shipped), but no DOI/version to cite, and the live data is still the demo.
- **Wants next.** The underreporting and safety-in-numbers literature cited in the
  data card; an embeddable map; a machine-readable version feed.
- **Adopts if** she can link the exact row, re-run the number, *and* footnote the
  premise. **Walks if** the central claim rests on the author's word.
  *(corroborates R22/R32; NET-NEW: cite-the-premise)*

#### P8 — Prof. Halvorsen, transport epidemiologist (would reuse the dataset)
- **Goal.** Reuse the per-segment rates + CIs in a peer-reviewed health-equity
  analysis, and cite the method.
- **Values today.** The rate-with-interval framing is *her* language; the choice
  of Byar's Poisson interval (well-behaved to count 0, never negative) over Wald is
  the right call; Benjamini-Hochberg FDR across segments is exactly what she'd
  demand; the planted-fixture coverage simulations are reassuring.
- **Gets stuck.** *The interval covers the numerator, not the denominator* — the
  CI is Poisson-on-counts with exposure treated as fixed, and "your numerator has
  error bars; your denominator pretends it doesn't." Report counts also cluster
  (one viral post, one active group), so the **Poisson assumption likely
  understates variance** — and the methodology itself flags that the overdispersion
  check is *not yet implemented*.
- **Wants next.** Exposure-uncertainty propagation (or a louder scope statement);
  the overdispersion/quasi-Poisson check landed; empirical-Bayes smoothing for
  small areas; a versioned DOI and a documented power analysis ("how many reports
  until a block is rankable").
- **Adopts if** the uncertainty is honest end-to-end and citable. **Walks if** the
  CI looks rigorous but silently fixes the shakiest input. *(corroborates R28/R34,
  E9/E11; NET-NEW: overdispersion)*

#### P9 — Sam, data scientist evaluating the statistics
- **Goal.** Decide, adversarially, whether the numbers hold up.
- **Values today.** Gi\* run on the **rate, not the raw count** (the crucial
  choice that stops it re-telling the heat-map lie with a p-value attached);
  network-based spatial weights, not straight-line; raw *and* FDR-adjusted
  significance reported; the banned-Wald discipline; the null-fixture test that a
  method finding hotspots in pure noise fails.
- **Gets stuck.** Three things the project already half-concedes: (1) **MAUP** — the
  block is an arbitrary unit and a hotspot at one segmentation can dissolve at
  another, and there's no rank-stability check yet; (2) Gi\* significance rests on
  the **normal approximation**, with conditional-permutation inference only noted as
  future work; (3) BH-FDR assumes a structure that **spatial dependence** strains —
  Caldas de Castro & Singer's spatially-aware FDR is the relevant refinement.
- **Wants next.** A re-segmentation sensitivity report; a permutation Gi\* option;
  a note on (or move to) spatial FDR; overdispersion handling.
- **Adopts if** the sensitivity analyses are published, not promised. **Walks if**
  significance is asserted on assumptions the data violates. *(corroborates R28;
  NET-NEW: MAUP sensitivity, permutation Gi\*, spatial FDR)*

### Group 4 — Assure & Audit

#### P10 — Marcus, open-data / reproducibility reviewer
- **Goal.** Independently re-run the pipeline and get **byte-identical** output.
- **Values today.** `make reproduce` asserting a clean `git diff` on
  `data/published/`; content-hashed artifacts + metadata sidecar; the committed
  planted-hotspot fixtures with known answers; ADRs and `CITATION.cff`; the
  read-only server that refuses any path under `data/raw/`.
- **Gets stuck.** The README admits `requirements.lock` is **generated but not
  committed yet**, so a from-scratch install isn't pinned/hashed for him; there's
  no tagged release or DOI to pin a citation to; "reproducible" is true on the
  maintainer's machine but not yet *push-button* for an outsider.
- **Wants next.** The committed hashed lock; a tagged release + Zenodo DOI; a
  documented "paste this to reproduce" path.
- **Adopts if** a clean clone reproduces the published bytes. **Walks if**
  reproduction needs the maintainer in the room. *(corroborates R35; NET-NEW:
  commit the lock)*

#### P11 — Grace, blind screen-reader user (NVDA) — also the low-vision lens
- **Goal.** Reach every finding the map shows, without the map.
- **Values today.** The architecture is *right*: the sortable data **table is
  authoritative**, not a second-class caption; sort buttons announce through an
  `aria-live` region; the segment-name column is sticky for 200% zoom; significance
  is conveyed in text and pattern, never color alone; a generated prose
  hotspot-geography summary shipped (R8).
- **Gets stuck.** It's *designed-for* but not yet *measured*: the README and ACR
  are honest that the **manual NVDA/VoiceOver pass is still pending** and some VPAT
  rows are "Partially Supports." At 200% zoom the two side-by-side maps get tiny
  (the single-map toggle helps). She can't yet confirm streamed/announced behavior
  by lived use.
- **Wants next.** The real NVDA + VoiceOver + zoom pass run and its results
  committed; "Partially Supports" predictions converted to measured PASS/FAIL.
- **Adopts if** the conformance claim is backed by a real assistive-tech session.
  **Walks if** she's handed a colored blob with a promise. *(corroborates R15)*

#### P12 — "the brigade", bad-faith reporter / astroturf threat (red-team lens)
- **Goal.** Manufacture a hotspot to push a project (or bury a real one to defeat
  one), or craft a report to expose where a specific person rides.
- **Values today (against them).** The published artifact is genuinely hard to
  abuse: exposure normalization blunts volume floods (you must beat the
  denominator, not just add counts); intervals + Gi\* show an injected burst as
  *uncertain*, not a confident top rank; dedupe collapses near-identical
  submissions; k-anonymity withholds low-count segments and no per-report
  coordinate/timestamp is ever published; the moderation queue means *no public
  submission reaches the dataset until a human approves it*, with identifier-leak
  and near-duplicate flagging.
- **Gets stuck (the gaps the project itself names).** The **network-edge** defenses
  — rate limiting, proof-of-work, per-source influence caps, burst/outlier
  detection, trust tiers — are **designed but not yet built**, so an open public
  endpoint is not yet safe to expose. A patient, distributed, low-and-slow campaign
  of *plausible unique* reports still passes (the threat model concedes this).
- **Wants next (what must exist before "open").** The full B2–B7 abuse stack
  shipped and fixture-tested *before* the form is opened beyond a closed/invite
  pilot.
- **Defeated if** intake stays gated until the toolkit lands. **Wins if** the form
  opens publicly before the defenses do. *(corroborates R44, E15; HR4)*

### Group 5 — Operate

#### P13 — Chelsea, owner / maintainer
- **Goal.** Keep nearmiss statistically honest, accessible, cheap, and survivable
  without a grant — and resist the gravity toward shiny features that erode the
  hard rules.
- **Values today.** Config-over-code (`config/*.toml`), `make verify` as one merge
  gate (lint, types, tests, a11y, security), the planted-hotspot fixtures, the
  scale-to-zero / static-friendly footprint, the audit-as-artifact discipline.
- **Gets stuck.** *Honesty scales worse than features.* Every expansion the cast
  wants — public intake, equity overlays, an API, before/after evaluation —
  multiplies the HR3 (bias) and HR4 (privacy) surface, and the anti-features list
  (no per-reporter dashboards, no plate-reporting, no "safest route" product, no
  selling risk to insurers) is part of the roadmap, not separate from it. Single-
  maintainer means no second reviewer on every change.
- **Wants next.** To ship the cheap, research-grounded **correctness and honesty**
  items first (they protect the franchise) and to keep the expensive, privacy-
  expanding ones gated behind proven defenses.
- **Adopts** the discipline of "cite the premise, fix the stats gap, then build."
  **Walks** from any feature that asks the project to overclaim. *(corroborates
  the prior panel's cross-cutting theme 6)*

---

## Cross-cutting themes

1. **The premise is true but uncited — fix that first, cheaply.** Every "reuse"
   and "decide" persona (P5, P6, P7, P8) independently wants the project's founding
   claim — that VRU near-misses and even injuries are massively under-recorded in
   official data — *sourced*. The literature is unambiguous and convergent (police
   reporting of cyclist injury ≈ 7–46%; an international average near 10%), yet the
   data card asserts it without a single citation. This is the highest-leverage,
   lowest-cost change: it converts the thesis from advocacy to evidence.
   **[NET-NEW]**
2. **Exposure normalization is the moat — and the literature warns it doesn't fix
   the bias people will assume it fixes.** Normalizing by exposure removes the
   *volume* confound (safety-in-numbers, Jacobsen/Elvik). It does **not** remove
   *self-selection* (who reports) and is **weak/contested at the micro level**, so a
   low per-segment rate on a busy street is not proof of safety. P6 and P9 both hit
   this; the brief should say it. **[NET-NEW caveat on a [corroborated] feature]**
3. **One real statistical-correctness gap, named by the project itself.** The
   methodology concedes the **overdispersion** check (quasi-Poisson / negative-
   binomial) is *not yet implemented*, so intervals on clustered report counts may
   be too narrow. The epidemiologist (P8) and data scientist (P9) both find it. The
   prior panel has no item for it. **[NET-NEW]**
4. **"Designed-for" vs "measured" recurs in two places: accessibility and
   reproducibility.** Grace (P11) and Marcus (P10) tell the same story from
   opposite ends — the architecture is excellent (table-authoritative a11y; `make
   reproduce`) but the *proof* is pending (the manual NVDA/VoiceOver pass; the
   committed hashed lock + DOI). Closing both is cheap and converts assertions to
   evidence. **[corroborates R15, R35]**
5. **Honesty about coverage is a feature, not a disclaimer.** Theo (P3), Marisol
   (P2), and Dr. Okafor (P6) all need the dataset to refuse to imply coverage it
   lacks (rolling/pedestrian modes; time-of-day; who's missing). A per-city
   mode-scope label and a literature-grounded representativeness panel are what keep
   "no reports here" from being misread as "safe." **[corroborates R33, R48]**
6. **The write path triples the threat model — keep it gated.** Three reporters
   (P1, P2, P3) want a door in; the brigade (P12) and the maintainer (P13) both say
   that door must stay invite-only until the network-edge abuse stack ships. This is
   a privacy project, not a form. **[corroborates R44, E15]**

---

## Honest limits of this exercise

This panel is **synthetic**. Role-playing a research-grounded cast surfaces gaps
and pressure-tests the framing, but it cannot tell you *which* needs are real, how
many of each stakeholder exist, or what they would actually do. It over-represents
the author's mental model and the literature's emphases, and it will miss what only
real users surprise you with — and the access findings (P11) are structural
predictions, not a substitute for the real NVDA/VoiceOver session. **Do not
prioritize off this alone.** Its job is to (a) attach external evidence to the
intuitions the [2026-06-20 panel](research/2026-06-20-synthetic-user-interviews.md)
already captured, and (b) design cheaper, sharper questions for real interviews
with ≥1 of each role — especially a real Vision Zero coordinator (P6), a disabled
pedestrian (P3), and a transport epidemiologist (P8), whose needs most shape the
statistics.

→ The triaged, cited, sequenced backlog is in
[`RESEARCH-ROADMAP.md`](RESEARCH-ROADMAP.md).
