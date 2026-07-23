# Product expansion and differentiation plan

Drafted 2026-07-18. This is a product strategy, not an engineering commitment.
It evaluates what is useful and differentiated now, identifies the product gap,
and sequences the smallest credible path from a strong methods repository to a
tool that real advocates and planners repeatedly use.

> **Implementation update, 2026-07-22:** the first public thin slice now exists. The gateway shows
> a complete fictional dossier before the machinery; `/studio/` runs a browser-local CSV/JSON
> readiness audit and fixes the controlled-language claim tier from that result; the Atlas can
> carry saved official context into `/dossier/`; and Studio uses browser-local session state so
> dossier claim text is regenerated from the canonical tier template rather than trusted from a
> URL. The dossier exposes its tier, boundary, source context, and local fingerprint. This does
> **not** satisfy the partner-validation exit gates below. The readiness
> result remains a preflight heuristic, the default dossier is fictional, and real-data dossier
> generation still requires the full pipeline and human review.

## Executive verdict

**NearMiss is technically distinctive, but it is not yet a uniquely useful
product.**

The repository has an unusually defensible analysis and publication core:
exposure-normalized rates, uncertainty, spatial significance with false-discovery
control, explicit reporting-bias findings, privacy floors, content-addressed
provenance, per-dataset calibration, planted-truth benchmarks, and a conformance
checker. The combination is rare.

The public job, however, is unclear. The deployed product is a national FARS count
atlas; the local near-miss analysis surfaces are synthetic and not deployed; the
README also describes intake, an analysis engine, a reusable library, teaching
materials, a QGIS plugin, and a future standard. A visitor cannot quickly tell which
one is the product or what decision it helps them make.

Nor are collection, mapping, exposure normalization, or near-miss detection unique
on their own:

- [BikeMaps](https://www.bikemaps.org/) collects collisions, near misses, and
  hazards and already exposes Strava ridership; its own
  [Strava Metro case study](https://metro.strava.com/pb/case-studies/using-strava-data-for-active-transportation-planning)
  explains why exposure changes hotspot conclusions.
- [SimRa](https://simra-project.github.io/) collects rides and near misses with a
  data-minimizing app and publishes regional analysis dashboards.
- [Close Call](https://www.closecall.report/report) offers a very simple public
  report-to-map experience across walking, biking, wheelchairs, and scooters.
- [dashcam.bike](https://dashcam.bike/311/) combines video, phone sensors, 311
  integration, and automated surface and close-call signals.
- [Viva](https://info.vivacitylabs.com/near-miss-feature-smart-road-safety) and
  other sensor vendors automatically detect conflicts and sell before/after
  analysis to authorities.
- [FHWA SSAM](https://highways.dot.gov/turner-fairbank-highway-research-center/software/ssam)
  evaluates conflicts from traffic-simulation trajectories.
- NHTSA already publishes the FARS files on which the national preview is based;
  state-by-state FARS exploration is a useful demonstration, not a durable wedge.

Current adoption is also unproven. The public repository is one month old and, as
of this draft, has one star and no forks. The documented user panels are explicitly
synthetic. That is not a negative verdict on a young project; it means usefulness
must now be demonstrated with people and decisions rather than inferred from
implementation quality.

### The opportunity

Reposition NearMiss as the **open evidence-to-action compiler for street-safety
decisions**:

> Bring community reports, exposure, and official outcomes. Leave with a citable,
> privacy-safe corridor case that states what the evidence supports, what it does
> not support, what should be investigated, and how to measure what happens next.

The ownable output is a **Decision Dossier**, not another map. A dossier is a
portable evidence package for a council memo, grant application, public meeting,
engineering scoping conversation, or intervention evaluation. It carries the
finding and its caveats together and can be independently reproduced.

This direction turns the repository's strongest technical choices into visible
user value:

| Existing capability | User-visible promise |
| --- | --- |
| Exposure normalization | “Busy is not automatically dangerous.” |
| Confidence intervals, FDR, calibration | “This priority survives a skeptical methods review.” |
| Source tiers and bias findings | “You can see where the evidence is strong, weak, or missing.” |
| Corridor aggregation | “The result is expressed in the unit an intervention uses.” |
| Privacy floors and local processing | “Community evidence can be used without publishing a person's trip.” |
| Manifests, hashes, and conformance | “A third party can audit exactly how the claim was made.” |
| Change attribution and preregistration | “A later ranking change cannot be casually presented as impact.” |

## Product focus

### Primary user

Start with a safe-streets advocacy group, mobility coalition, or small public-interest
research team that:

- has reports, a BikeMaps/SimRa export, a spreadsheet, or access to official data;
- needs to influence a specific planning, funding, or council decision;
- lacks a staff statistician and may have limited GIS capacity;
- cares about credibility because its evidence will be challenged; and
- can accept a periodic analysis workflow rather than a real-time service.

The traffic engineer or Vision Zero coordinator is the **trust audience**, not the
initial operator. Contributors are a data source, not the primary product customer.
This keeps NearMiss from competing head-on with mature reporting apps and city 311
systems.

### Job to be done

> When we need a city or funder to act on a corridor, we want to combine the
> incomplete evidence we can access into a defensible case, so we can make a
> specific ask without overstating what community reports prove.

Functional success is not “viewed a map.” It is “used the output in a real decision
process.” Emotional success is confidence under scrutiny. Social success is being
seen as a credible community partner rather than a source of anecdotal complaints.

### Product architecture

Use three clearly separated surfaces:

1. **Studio — make the case.** A local-first guided workflow that audits inputs,
   runs analysis, helps select a corridor, and assembles the dossier. Raw reports do
   not need to leave the operator's machine.
2. **Dossier — carry the case.** A printable, linkable, accessible artifact with
   claim, evidence, uncertainty, missingness, source provenance, maps and tables,
   a specific requested next step, and a measurement plan.
3. **Atlas — inspect published cases.** A gallery of consented, conforming dossiers
   and official reference layers. The current FARS studio becomes a reference-data
   explorer inside this surface, not the home page or the whole identity.

The CLI, `honest_rates`, schemas, benchmarks, QGIS plugin, and verification tools
remain the engine and reuse layer. They should support the product rather than
compete for top-level positioning.

## The Decision Dossier

Every dossier should answer nine questions in a fixed order:

1. **What decision is being requested?** Named owner, jurisdiction, corridor,
   intervention class, and requested next action.
2. **What is the finding?** One controlled-language claim selected from what the
   evidence tier permits.
3. **Why this corridor?** Rate, interval, sample size, spatial result, and comparison
   set—not only a color on a map.
4. **What kinds of harm recur?** Hazard-type rates and the dominant conflict pattern.
5. **What evidence agrees?** Community reports, exposure, official crashes, and
   other declared sources shown as separate tracks before any synthesis.
6. **What evidence is absent or weak?** Coverage gaps, source bias, stale or proxy
   exposure, sensitivity to geography, and small samples.
7. **What can and cannot be claimed?** A generated claim boundary, not a footer
   disclaimer.
8. **What should happen next?** Investigate, collect more data, conduct a field
   audit, pilot an intervention, or fund a treatment. Do not auto-prescribe
   engineering designs from observational data.
9. **How will change be evaluated?** Baseline window, follow-up window, frozen
   metric, minimum data, comparison corridor where feasible, and a commitment to
   publish null results.

The dossier should ship as accessible HTML, print-ready PDF, CSV/GeoJSON, and a
small machine-readable manifest. A short “verify this dossier” command or link
should reproduce its conformance verdict.

### Evidence ladder and controlled claims

Make the analysis engine's honesty legible through four product states:

| Tier | Minimum evidence | Permitted language | Next action |
| --- | --- | --- | --- |
| 0 — Coverage gap | Insufficient reports or no usable denominator | “Evidence is insufficient to rank this corridor.” | Collect or repair data. |
| 1 — Community signal | Publishable reports; denominator absent or weak | “Repeated reports warrant investigation.” | Field audit or targeted count. |
| 2 — Elevated rate | Aligned exposure, interval, quality and sensitivity gates pass | “The observed report rate is elevated in this window.” | Scope a treatment or deeper study. |
| 3 — Triangulated priority | Tier 2 plus an independent source or official outcome agrees | “Independent evidence supports prioritizing this corridor.” | Advance a specific decision and evaluation plan. |

The tool must refuse stronger language than the tier supports. “Dangerous,” “caused
by,” “will prevent crashes,” and “the intervention worked” require evidence the
current observational pipeline generally does not provide.

## What to build—and what to stop building

### Build

- A no-code project wizard around existing config, adapters, coverage audit, and
  analysis commands.
- A source-readiness check before analysis: field mapping, spatial coverage,
  temporal overlap, denominator trust, report quality, and expected suppression.
- A corridor workspace that explains ranking changes and allows a user to pin the
  corridor relevant to the decision instead of treating rank 1 as destiny.
- The Decision Dossier builder and controlled-claim system.
- A “methods in context” explainer attached to each result: why this rate differs
  from raw count, why uncertainty matters, and what changed across versions.
- A real evaluation workflow: baseline, follow-up, preregistration, change
  attribution, and a null-result path.
- Interoperability around the data people already have: BikeMaps, SimRa, standard
  spreadsheets, common 311 exports, official crash data, OSM, and declared exposure
  layers.
- A consented public registry of dossiers only after real partner use exists.

### Do not build

- Another general-purpose incident reporting network.
- Turn-by-turn “safe routing” or a personal risk score.
- A real-time raw-report feed, public point map, or individual reporter profile.
- Automated engineering prescriptions or causal claims.
- Cross-city safety leaderboards that pool incompatible exposure units.
- Engagement gamification, reporter bounties, or streaks.
- A national standard or federation before at least two independent adopters exist.
- More national FARS visualizations unless a validated user task specifically
  requires them.

## Roadmap

Dates below assume one primary maintainer. Use outcomes and gates, not shipped
feature count, to advance between phases.

### Now: prove the job and sharpen the story (weeks 0–4)

**Goal:** determine whether real organizations will use a defensible dossier in an
actual decision.

1. Recruit 8–12 interviewees across 5–7 organizations: at least four advocates,
   two planners/engineers, one journalist or researcher, and one accessibility or
   disability-justice participant. Do not count existing synthetic personas.
2. Ask for a recent or upcoming corridor decision and the artifacts actually used:
   staff memo, council packet, grant form, map, spreadsheet, testimony, or field
   audit. Study the workflow, not feature preferences.
3. Select three design partners with a live decision in the next six months and
   permission to use their real, appropriately governed inputs.
4. Manually produce one dossier per partner with the existing pipeline. This is a
   concierge test: learn the missing workflow before building UI.
5. Observe whether the partner can explain the claim and caveat, whether the trust
   audience accepts the artifact as reviewable, and where manual work dominates.
6. Rewrite the public home page around “reports to defensible corridor case.” Put
   the FARS atlas under “Explore official reference data”; label synthetic methods
   demos as demos.
7. Add one end-to-end, fully synthetic sample dossier so the promised output is
   visible without implying real community adoption.

**Exit gate:** three partners commit data and a real decision; at least two say they
would use the resulting dossier; at least one trust-audience reviewer says it is
materially easier to audit than the organization's current artifact.

### Next: ship the thin evidence-to-action workflow (weeks 5–12)

**Goal:** a non-programmer can produce and understand a conforming dossier from a
supported input.

1. Build a local-first Studio shell with four steps: define decision, add sources,
   inspect evidence quality, build dossier.
2. Support one deliberately narrow golden path first: CSV or BikeMaps-like reports,
   OSM streets, one exposure layer, and optional official outcome data.
3. Generate a source-readiness report before the expensive analysis. Estimate how
   much will be unsnapped, excluded, or privacy-suppressed.
4. Surface the evidence ladder, claim boundary, rate-vs-count contrast, sensitivity,
   calibration, and MAUP stability in plain language.
5. Build the corridor and intervention-measurement sections around the already
   shipped corridor, change-attribution, and preregistration machinery.
6. Export accessible HTML and print output; include data and manifest downloads and
   a verifier result.
7. Instrument only privacy-safe product events: sample project opened, readiness
   check completed, analysis completed, dossier exported, dossier shared, and
   follow-up evaluation created. Make telemetry opt-in for local projects.

**Exit gate:** five observed users complete the golden path; median active time to a
first sample dossier is under 20 minutes and to a real-data readiness result is
under 30 minutes; four of five can accurately state the key caveat without help;
all dossiers pass conformance.

### Then: make messy real data survivable (months 4–6)

**Goal:** reduce the expert labor required to onboard a second and third community.

- Add a visual crosswalk builder backed by the existing adapter manifests.
- Add reusable import recipes for BikeMaps, SimRa, generic 311 CSV, and local
  spreadsheets; treat upstream licenses and redistribution rights as explicit
  gates.
- Add temporal and spatial coverage diagnostics and an exposure-assistance guide.
- Make “no denominator available” a supported Tier 1 outcome with a targeted data
  collection plan, not a failed run or a fabricated proxy.
- Add official-outcome context as a separate evidence track; do not let verified
  FARS lineage automatically promote community evidence.
- Publish a project bundle format containing config, crosswalks, source declarations,
  hashes, and the dossier recipe without containing protected raw reports.
- Create a maintainer review queue for partner dossiers only if partners want
  publication.

**Exit gate:** three distinct organizations complete real projects, at least two use
different input recipes, and median maintainer assistance falls below two hours per
new project after data access is resolved.

### Later: prove repeated decision value (months 7–12)

**Goal:** show that NearMiss is part of an evidence cycle, not a one-off map.

- Run a small design-partner cohort through baseline and follow-up dossiers.
- Add a treatment log that records what actually changed, when, and by whom.
- Generate pre/post change reports that separate input drift, method drift,
  reporting change, exposure change, and observed outcome change.
- Add citation and meeting-packet modes tuned to council, engineering, grant, and
  journalism workflows without changing the underlying claim.
- Publish case studies that include failed, inconclusive, and null-result examples.
- Open a reviewed dossier registry with opt-in community ownership, removal policy,
  version history, and no cross-city leaderboard.
- Package the Studio for a dependable install and exercise the existing signed
  release pipeline.

**Exit gate:** at least five dossiers are used in real staff, funding, council, or
  community processes; at least three partners return for a second analysis; one
  partner completes a follow-up evaluation; no published dossier is corrected for
  an avoidable claim-boundary failure.

### Horizon: infrastructure only after adoption (year 2+)

Pursue the governed standard and federation only when two or more independent
implementers want to exchange artifacts. At that point:

- move the evidence-tier vocabulary, dossier schema, source declarations, and
  conformance rules into a governed specification;
- recruit BikeMaps/SimRa maintainers and at least one agency data owner;
- define de-listing, trademark, liability, corrections, and version policy;
- federate signed aggregate artifacts, never private reports; and
- keep cross-city comparison disabled unless exposure units and methods are truly
  comparable.

## Priorities

| Priority | Initiative | Value | Effort | Confidence | Decision |
| --- | --- | --- | --- | --- | --- |
| P0 | Real decision interviews and concierge dossiers | Very high | Low–medium | Medium | Start now |
| P0 | Positioning and navigation split: Studio / Dossier / Atlas | High | Low | High | Start now |
| P0 | Sample Decision Dossier and controlled claims | Very high | Medium | Medium | Prototype now |
| P1 | Local-first Studio golden path | Very high | High | Medium | Build after validation |
| P1 | Source-readiness and coverage diagnostics | Very high | Medium | High | Build with Studio |
| P1 | Accessible HTML/print dossier export | High | Medium | High | Build with Studio |
| P2 | Visual crosswalks and additional import recipes | High | High | Medium | After three partner datasets |
| P2 | Evaluation cycle and treatment log | High | Medium | Medium | After first dossiers are used |
| P2 | Reviewed dossier registry | Medium | Medium | Low | After opt-in demand |
| P3 | Governed standard and federation | Potentially high | Very high | Low | Gated on external adopters |
| Stop | Additional generic atlas views or reporter-network features | Low strategic value | Variable | High | Deprioritize |

Capacity guideline for the next six months: 50% partner discovery and workflow,
30% product thin slice, 20% statistical/reliability/accessibility health. The
codebase is already ahead of its adoption evidence; more than half the next phase
should not be another methods expansion.

## Metrics

### North-star outcome

**Decision Dossiers used in a real decision process per quarter.** “Used” means
attached, cited, presented, or explicitly reviewed in a staff memo, council or board
meeting, funding application, field-audit plan, engineering scoping discussion, or
intervention evaluation.

### Product funnel

- **Qualified starts:** organizations begin with a named decision and window.
- **Data readiness:** percentage that reach a usable Tier 1+ evidence state.
- **Activation:** percentage that export a conforming dossier.
- **Comprehension:** percentage who correctly explain the finding and its strongest
  caveat without prompting.
- **Use:** percentage of dossiers carried into the named decision process.
- **Repeat:** organizations that create a second dossier or follow-up evaluation
  within six months.

Initial targets after the thin slice:

| Measure | Target |
| --- | --- |
| Sample-dossier completion | ≥ 80% of observed pilot users |
| Real-data readiness result | median < 30 minutes of active use |
| Correct claim-and-caveat comprehension | ≥ 80% |
| Exported dossiers passing conformance | 100% |
| Design partners using dossier in named process | ≥ 3 of first 5 |
| Six-month partner repeat | ≥ 50% |
| Published privacy or claim-boundary incidents | 0 |

Do not use report count, map views, repository stars, or raw dataset downloads as
the primary success metric. They are useful reach signals but do not prove the
decision job is being done.

## Riskiest assumptions and cheapest tests

| Assumption | Why it could kill the direction | Cheapest credible test |
| --- | --- | --- |
| Advocates have a recurring evidence-to-decision job | The product may be an impressive one-off analysis | Interview around a live decision and ask for prior artifacts; secure three design-partner commitments. |
| They can obtain usable exposure | Without a denominator, the strongest promise often cannot activate | Run readiness audits on ten real candidate datasets before building broad UI. |
| A dossier is better than a map or GIS export | Users may only need a picture or raw layer | Hand-build both and observe which artifact is used in the meeting. |
| Trust audiences value the audit trail | Engineers may prefer their own established method regardless | Put one dossier through a skeptical planner/statistician review and record required changes. |
| Local-first operation is usable | Privacy architecture may impose too much setup | Test a packaged prototype with non-programmers on their own machines. |
| Corridor claims lead to a specific next action | Analysis may stop at “interesting” | Require a named ask before the analysis and see whether the dossier changes or advances it. |
| Partners return for evaluation | The repeat loop may be aspirational | Pre-commit the follow-up window in the first dossier and track completion. |

## Kill, pivot, and expansion criteria

After the first 8–12 interviews and three concierge dossiers, **stop or pivot the
Studio direction** if any two are true:

- fewer than three organizations will bring real inputs and a live decision;
- fewer than one in three interviewees describes a recurring evidence workflow;
- usable exposure is unavailable for more than 70% of candidate projects and Tier 1
  dossiers are not valuable on their own;
- trust audiences say the audit trail adds no material value over an existing GIS
  memo;
- no dossier is used in its named decision within six months; or
- users consistently want immediate service requests or a simple public report map
  instead.

If that happens, do not clone BikeMaps, Close Call, or 311. Narrow NearMiss into the
parts already most defensible: `honest_rates`, the planted-truth benchmark,
conformance tooling, and a reference implementation for researchers and civic-data
teams.

**Expand** toward a standard or federation only when all are true:

- at least five real organizations have completed dossiers;
- at least three have repeated;
- two independent implementations need artifact exchange;
- a data owner and an external methods reviewer participate in governance; and
- correction, de-listing, liability, and accessibility ownership are explicit.

## Immediate next ten actions

1. Freeze new broad expansion work for four weeks except correctness, security,
   privacy, and accessibility defects.
2. Write a one-page interview guide around a recent decision, evidence used,
   objections received, and what happened next.
3. Recruit the first eight real interviews through local advocacy groups, MPO or
   city active-transportation staff, journalism/research contacts, and disability
   mobility advocates.
4. Define the first Decision Dossier schema and controlled-claim vocabulary on
   paper.
5. Create one synthetic end-to-end sample dossier from an existing fixture.
6. Ask three interviewees for a real, time-bounded design-partner case.
7. Run source-readiness audits and document every manual step and failure.
8. Produce three concierge dossiers before building the Studio shell.
9. Test each dossier with both its operator and one skeptical trust-audience
   reviewer.
10. Decide after the evidence: build the thin Studio, narrow to a methods toolkit,
   or partner with an existing collector and own only the evidence layer.

## Bottom line

NearMiss should not try to be the place where everyone reports every hazard or the
place where anyone can browse another crash map. Those categories are occupied, and
the repository currently has no adoption advantage in them.

It can become genuinely unique and useful by owning the difficult middle between
raw community evidence and public action: an open, privacy-safe, statistically
defensible way to make a corridor case, survive scrutiny, and later determine
whether anything actually changed. The repository already contains most of the hard
technical ingredients. The next risk is not capability. It is whether the workflow
matters enough to real people—and the roadmap must now optimize for learning that.
