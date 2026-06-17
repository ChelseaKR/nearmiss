# Threat model

This document states what `nearmiss` is trying to protect, who might try to break it, how, and what is
done about it. It is scoped to the system described in the README: report intake, a recorded pipeline,
the statistics layer, the published open dataset, and the read-only accessible map. It is written to
the same standard as the rest of the project — it should hold up when a skeptical reader, or a person
worried that contributing could expose them, pushes back.

Two things are true at once and shape every decision here. First, the dataset and the analysis are the
product, and their value is entirely a function of trust: a contributor who fears deanonymization will
not report, and a finding a traffic engineer can dismiss as a poisoned heat map is worthless. Second,
this is an open, low-budget, single-maintainer project with a static published artifact and a
scale-to-zero intake, so the threat model is honest about which classes of attack are simply out of
scope to fully defeat. Where that is the case, it is said plainly in **Residual risk** rather than
papered over.

Mitigations are tied to the five hard rules from the README (referenced as **HR1**–**HR5**), because
the hard rules are the project's primary security and integrity controls, not just its statistical
ones. The rules are enforced in CI and by policy, not treated as aspirations.

- **HR1** — No rate without a denominator.
- **HR2** — No estimate without an interval.
- **HR3** — Reporting bias is named, not hidden.
- **HR4** — Contributor privacy is protected (pseudonymous; aggregated to public street segments;
  low-count segments withheld; raw stays private).
- **HR5** — Open and reproducible end to end (`make reproduce` regenerates every figure and table).

## Assets

What is worth protecting, in priority order. Priority reflects both the harm if the asset is lost and
the project's stated values: a person can be harmed by deanonymization, whereas a wrong figure can be
corrected.

1. **Contributor privacy and identity.** The most sensitive asset. A near-miss report carries a
   location, a time, and a mode of travel, and a sequence of them traces a person's routine — where
   they live, when they commute, the route they take. Reporters are vulnerable road users who are
   trusting the project with exactly the data that, in aggregate, can identify them. Compromise here is
   not recoverable: a published precise track cannot be un-published, and it can expose a real person to
   real-world risk. Protecting this asset is **HR4**.
2. **Dataset integrity.** The cleaned internal dataset and the lineage from raw report to published
   GeoJSON. If reports can be forged, duplicated, or selectively dropped without trace, every downstream
   statistic is built on sand. Integrity is what lets a result be traced from figure back to raw input
   (**HR5**).
3. **Credibility of published findings.** The rates, rankings, intervals, hotspot surfaces, and briefs.
   This is the deliverable. It can be damaged by tampering (poisoned inputs, skewed exposure) *or* by
   honest-looking misreading (a raw-count map taken for a danger map). Both are in scope. The defenses
   are **HR1**, **HR2**, and **HR3**.
4. **Availability of the open data.** The published GeoJSON, data card, schema, notebooks, and the
   accessible map and table. The whole point is a community-owned evidence base that does not depend on
   a city's goodwill (**HR5**); if it is only reachable when one host is up, that promise is weaker than
   claimed.

## Actors and adversaries

Not everyone here is malicious. Naming the benign actors matters because two of the most damaging
outcomes — a misread map and a privacy leak through ordinary contribution — come from non-adversaries.

- **Contributor (benign).** A cyclist or pedestrian submitting a real report. Trusts the project with
  sensitive data. Not an adversary, but the party the privacy asset exists for.
- **Data consumer (benign).** An advocate, journalist, councilmember, or traffic engineer who reads the
  map, the briefs, or the GeoJSON. A *naive* consumer who misreads a raw-count surface as a danger map
  is a first-class threat to credibility even though they intend no harm.
- **Re-identification adversary.** Anyone — a curious neighbor, a harasser, an employer, or a data
  broker — who takes the public dataset and tries to single out a specific person, especially someone
  whose reports cluster at a home or workplace end.
- **Manipulator / astroturfer.** A party with an interest in the map saying a particular thing: a
  resident wanting their street flagged dangerous to win a calming project, or a party wanting a street
  to look *safe* to defeat one. Submits crafted or bulk reports to move a hotspot.
- **Exposure-source adversary.** A subtler manipulator who targets the denominator rather than the
  numerator — feeding or altering exposure inputs so that rates skew without any obviously fake report
  in the dataset.
- **Supply-chain adversary.** Whoever can land code in a dependency, a GitHub Action, or a build tool
  that the project pulls in, and thereby reach the pipeline or the published artifact.
- **Opportunistic attacker.** Scans public repos for leaked secrets, exposed endpoints, and known-CVE
  dependencies. Not targeting `nearmiss` specifically; finds it by automation.

Out of scope as adversaries: a nation-state or a well-resourced actor mounting a sustained, targeted
operation against this specific project; an attacker with physical access to the maintainer's machine.
These are acknowledged in **Residual risk**, not defended against here.

## Threats and mitigations

Each threat names the asset it attacks, the actor most likely to mount it, concrete mitigations tied to
the hard rules and the architecture, and where mitigation stops.

### T1 — Deanonymization via precise coordinates or timing

**Asset:** contributor privacy. **Actor:** re-identification adversary.

A report's location and timestamp are quasi-identifiers. The acute risk is the *home/work end* of a
trip and *repeat structure*: a single report aggregated into a busy segment is fairly safe, but several
reports from the same contributor that all originate near one address, at commute times, can be linked
and re-identified across segments even when no individual report location is published. Raw precision or
raw timing in any published artifact would defeat the whole privacy promise.

**Mitigations (HR4):**

- **Raw stays private and is gitignored.** Precise reports live only in `data/raw/`, which is
  gitignored and never committed; nothing in the public path (`publish.py`, `server.py`, the GeoJSON,
  the map) can read from it. The map server reads only published artifacts by design.
- **Aggregate to public street segments.** The open dataset is aggregated to public street segments, and
  the published geometry is the real public street centerline (public infrastructure) — never a report
  location and never a per-report point. The published unit is a place, not a person; snapping to a
  street segment in the pipeline discards sub-segment precision before publication.
- **Publish nothing per-report.** No per-report coordinate, timestamp, reporter token, note, mode,
  severity, or heading is ever published. This is enforced positively by an allowlist in
  `publish._feature` (only segment-level aggregate fields are emitted) and negatively by a forbidden-key
  denylist invariant in `assert_published_clean()`, with `assert_metadata_clean()` applying the same
  denylist to the sidecar metadata. The KDE report-intensity peak is published only as a segment id,
  never a coordinate.
- **Pseudonymity, not identity.** Reports are pseudonymous; no account, email, or device identifier is
  carried into the dataset, so reports cannot be trivially chained to a real person by an identifier
  field.
- **No per-report timestamp is published.** Because no timestamp leaves the private store, the published
  artifacts cannot reconstruct an individual's commute timing, and per-segment outputs do not expose an
  ordered per-contributor sequence.
- **Minimum occupancy (k-anonymity withholding).** Any segment with a non-zero report count below
  `min_publish_n` (default 3) is withheld entirely from the published GeoJSON, the metadata, and the
  brief — no published place can mean "one or two people reported an incident here." This is enforced by
  `assert_published_clean()` (which raises on violation) and covered by the test suite.
- **Small-sample suppression.** Hazard breakdowns for segments with a count below `small_n` are
  suppressed (emitted as `{}`), so a thin breakdown cannot single out a rare incident type at a
  near-home segment.

**Stops at:** the linkage / repeat-visitor problem (see **Residual risk**). Aggregation to public
segments and withholding low-count segments reduce but do not eliminate the risk from a contributor with
many reports concentrated near one location whose segments could be linked across the dataset, or from
an adversary who already knows a candidate address and is only confirming.

### T2 — Report spam / poisoning to manipulate hotspots

**Asset:** dataset integrity and the credibility of findings. **Actor:** manipulator / astroturfer.

Bulk or crafted reports aimed at the *numerator* — inflating one street to manufacture a hotspot, or
flooding a route to bury a real one. A naive count map is trivially poisoned by volume.

**Mitigations:**

- **Validate at the door.** `intake.py` validates every report against `schema/report.schema.json`; a
  malformed or out-of-range report is rejected at intake and never reaches the dataset. Per the README,
  a malformed or malicious report is rejected, "never silently corrupting the dataset."
- **Rate-limit the intake.** Intake is rate-limited to resist spam and bulk submission, raising the
  cost of moving a hotspot by volume.
- **Exposure normalization blunts volume attacks (HR1).** Because every risk claim is a *rate* over an
  exposure denominator and a raw count is never published as danger, simply adding reports to an
  already-busy street does not by itself produce a high *rate*. Volume poisoning has to overcome the
  denominator, not just the count.
- **Significance, not raw clustering (HR2).** Getis-Ord Gi\* surfaces clusters that are statistically
  significant given spatial structure and exposure, and every rate carries an interval and an n. A
  burst of injected reports on a small segment shows up as *uncertain*, not as a confident top ranking;
  small-sample segments are shown as uncertain, not ranked as certain.
- **Dedupe and quality-flag.** The pipeline deduplicates and quality-flags reports; near-identical
  bulk submissions are collapsed or flagged rather than counted as independent evidence.
- **Bias is named (HR3).** A finding that could be an artifact of who or where reporting happened is
  flagged, so a coordinated push that skews the reporter pool toward one area is surfaced as a
  reporting-bias caveat rather than presented as established danger.
- **Lineage makes tampering reviewable (HR5).** Recorded transforms and the trace from figure → raw
  report mean a suspicious hotspot can be drilled into; an injected cluster leaves a visible,
  inspectable trail in the cleaned dataset.

**Stops at:** a patient, distributed, low-and-slow campaign of *plausible* unique reports that pass
validation, dedupe, and rate limits. See **Residual risk**.

### T3 — Exposure-source tampering to skew rates

**Asset:** credibility of findings. **Actor:** exposure-source adversary.

The denominator is as powerful as the numerator: halving the exposure on a segment doubles its apparent
rate without touching a single report. An adversary who can influence an exposure input (a counts feed,
a demand model's parameters, an imported exposure layer) can skew rankings while the report data looks
clean. This is the harder attack to spot precisely because **HR1** makes exposure load-bearing.

**Mitigations:**

- **Sources are named and dated (HR1).** Every rate states which exposure source was used and its date.
  An exposure swap or stale layer is visible in the published metadata and the data card, not silent.
- **Exposure is config, not magic.** Exposure sources live in the versioned `config.py` / checked-in
  config behind one interface; changing a source is a reviewable commit, not an untracked runtime edit.
- **Corroboration / redundancy.** Multiple exposure sources can corroborate a denominator (per the
  README's redundancy attribute); a segment whose rate depends on a single unverifiable exposure value
  is weaker evidence and is treated as such.
- **Honest degradation.** A segment with no exposure data is shown as "exposure unknown," not silently
  dropped or falsely rated, so an adversary cannot make a segment look safe simply by removing its
  denominator.
- **Sensitivity analysis is part of the product.** The notebooks include exposure sensitivity analysis;
  a ranking that flips under a reasonable change of exposure assumption is reported as fragile rather
  than asserted.
- **Hashed, reproducible inputs (HR5).** `make reproduce` rebuilds every figure from raw inputs, and
  published artifacts are hashed; an exposure input that changed without a corresponding, reviewed
  config change and a regenerated artifact is detectable.

**Stops at:** a corrupted *upstream* exposure provider that ships plausible-but-wrong data the project
has no independent way to check. See **Residual risk**.

### T4 — A naive consumer misreading a raw-count map as danger

**Asset:** credibility of findings. **Actor:** data consumer (benign).

The most likely way the project's findings get misused is not an attack at all: someone screenshots a
kernel-density surface of *report volume*, captions it "the most dangerous streets," and the busiest
bike route — which is busy, not deadliest — gets called the worst. The README is explicit that "a naive
heat map will confidently point at the busiest bike route and call it the most dangerous one." Defending
credibility means making the honest reading the *easy* reading.

**Mitigations:**

- **Label volume as volume (HR1).** A map of raw counts is labeled "report volume," never "danger."
  Unnormalized KDE is always labeled as report intensity unless exposure-normalized. The label travels
  with the artifact.
- **Publish rates, intervals, and significance, not just a surface (HR1, HR2).** The deliverables are
  exposure-normalized rates with confidence intervals and Gi\* significance, distinguishing "hot
  because dangerous" from "hot because busy." The honest artifact is the one that is front and center.
- **Name the bias on the page (HR3).** Every brief states who is over- and under-represented and what
  that does to the conclusion, so a reader cannot take the surface at face value without meeting the
  caveat.
- **Equivalent table carries the caveats.** The accessible list/table view carries the same ranked
  locations, rates, intervals, and significance flags, so the honest numbers are reachable without the
  visual that invites misreading — and a screen-reader user is never handed a colored blob with no text.
- **The data card states limits.** The published data card states sources, methods, limits, and the
  exposure assumptions behind every rate, so a downstream republisher has the caveats in hand.
- **Convey level in text and pattern, not color alone.** Risk level and significance are conveyed in
  text and pattern (an accessibility requirement that doubles as an honesty one): the map cannot
  communicate "danger" through a heat gradient that has no normalization behind it.

**Stops at:** deliberate or careless re-cropping. Once a third party screenshots a surface and strips
its legend, the project cannot control the caption. The mitigation is to make the labeled, honest
version the most prominent and citable one, not to prevent all misuse. See **Residual risk**.

### T5 — Supply-chain compromise

**Asset:** dataset integrity, credibility, and availability. **Actor:** supply-chain adversary.

A malicious dependency, a compromised GitHub Action, or a tampered build tool could exfiltrate the
private raw store, alter the pipeline or statistics, or poison the published artifact at build time —
reaching everything at once.

**Mitigations:**

- **Pinned and hashed dependencies.** Deps are pinned and hash-locked, so an install resolves to
  exactly the reviewed artifact; a swapped or republished package fails the hash check rather than
  silently entering the build.
- **Scanners as CI gates.** `pip-audit` (known-vulnerable deps), `gitleaks` (secrets), and CodeQL
  (code analysis) run in CI as gates, with Dependabot proposing reviewed, pinned bumps.
- **Reproducible build as a tripwire (HR5).** `make reproduce` regenerates every figure and table from
  raw inputs deterministically (seeded pipelines, deterministic notebooks). A published artifact that
  does not match a clean reproduction from raw is evidence of tampering somewhere in the chain.
- **Hashed published artifacts.** Published artifacts are hashed so consumers and CI can verify the
  file they have is the file that was built, and signed releases tie a release to the maintainer.
- **Minimal, inspectable surface.** The stack is framework-free on the web side and uses a standard,
  small geospatial stack; fewer dependencies mean fewer places for a compromise to hide. Stages emit
  plain, inspectable data between them, so an anomalous transform output is visible.
- **Least privilege in the public path.** `server.py` (`nearmiss serve`) is read-only — it answers only
  `GET`/`HEAD` — and it refuses any request under `data/raw/` or any dotfile path with HTTP 403, even
  when launched on the repo root (HTTP-verified). A compromise of the serving layer cannot reach
  `data/raw/`.

**Stops at:** a compromise of a pinned dependency *at the version the hash already trusts* (a malicious
release that lands before any advisory), or a compromise of GitHub/CI infrastructure itself. See
**Residual risk**.

### T6 — Secret leakage

**Asset:** integrity and availability (and, transitively, privacy if a leaked credential reaches the raw
store). **Actor:** opportunistic attacker; supply-chain adversary.

API keys for geocoding or exposure providers, or any intake/deploy credential, committed to the repo or
printed in logs would let an attacker run up cost, tamper with the pipeline, or — worst case — reach
private data.

**Mitigations:**

- **Env-only secrets.** Secrets are provided via environment variables, never committed; configuration
  is config-over-code with credentials kept out of the checked-in config files.
- **`gitleaks` in CI.** Secret scanning runs as a CI gate (and as a pre-commit hook) and catches an
  accidental commit before it merges. The repository is **public**, so there is no privacy buffer: the
  control is that secrets never enter version control in the first place (env-only) and any leak is
  caught and must be rotated, not relied on to stay hidden.
- **Scoped, rotatable keys.** Provider keys are least-privilege and rotatable; the maintainer runbook
  includes rotating an exposure source, so a suspected leak has a defined response.
- **No secrets in logs.** Structured logging on intake and pipeline stages is written to avoid emitting
  credentials or precise report contents.
- **Cost containment limits blast radius.** Scale-to-zero serverless intake with a budget alarm means a
  leaked key that is abused trips a cost alarm rather than silently draining a budget.

**Stops at:** a secret leaked outside the repo (a misconfigured provider dashboard, a screenshot, a
reused password) — outside what repo scanning can see. See **Residual risk**.

## Residual risk

What is *not* fully mitigated. This section is the point of the document: an honest threat model names
the gaps. None of the following should be read as "handled."

- **Repeat-contributor linkage (from T1).** Aggregation to public segments and withholding low-count
  segments protect a single report well and a handful of scattered reports adequately, but a contributor
  who files many reports clustered near one origin still leaks a pattern that a motivated adversary with
  side knowledge could re-identify across segments. Aggregation and the minimum-occupancy threshold
  reduce this; they do not erase it. A contributor worried about this should report sparingly near home.
  This limitation belongs in the data card and in any contributor-facing guidance, stated plainly,
  because consent should be informed.
- **Patient, distributed poisoning (from T2).** Rate limiting, dedupe, exposure normalization, and
  significance testing defeat crude flooding. They do not defeat a determined actor who submits a
  modest number of *plausible, unique* reports over time from varied origins. The statistical defenses
  make the manufactured signal show up as *uncertain* rather than confidently dangerous, which is the
  honest outcome, but the underlying data is still polluted. There is no identity verification by
  design (it would break pseudonymity), so this trade-off is deliberate and permanent.
- **Upstream exposure corruption (from T3).** If an exposure provider ships plausible-but-wrong
  denominators, the project surfaces the source and date, runs sensitivity analysis, and seeks
  corroboration — but it cannot independently audit a third party's counts. A coordinated bad exposure
  layer that survives corroboration would skew rates. The mitigation is transparency (the assumption is
  always stated), not prevention.
- **Loss of control once republished (from T4).** The project can make the honest, labeled artifact the
  prominent one; it cannot stop someone from screenshotting a surface, stripping the legend, and
  captioning it "danger." Correcting a viral misread after the fact is slow and incomplete.
- **Trusted-version and infrastructure compromise (from T5).** Hash-pinning defeats post-hoc package
  tampering but not a malicious release that is already the trusted, hashed version, and it does not
  defend against a compromise of GitHub Actions, the package index, or CI itself. Reproducibility is
  the tripwire, but it is detection after the fact, not prevention.
- **Out-of-band secret and account compromise (from T6).** `gitleaks` sees the repo, not a leaked
  provider dashboard, a phished maintainer account, or a compromised laptop. Single-maintainer
  ownership means there is no second reviewer on every change and no separation of duties; this is an
  accepted limitation of a personal open-source project, not a solved problem.
- **Targeted and well-resourced adversaries.** This model defends against opportunistic attackers,
  manipulators, and re-identification by ordinary parties. It does not claim to withstand a
  nation-state, a data broker combining `nearmiss` data with large external datasets, or an attacker
  with physical access to the maintainer's machine. Those are explicitly out of scope.
- **Availability has a single host.** The published GeoJSON is a single static file anyone can mirror or
  fork (by design, so the evidence base survives), but the *canonical* site and the intake run on one
  account; an outage or takedown there reduces availability until a mirror is promoted. The portability
  of the artifact is the mitigation, not a guaranteed-up service.

## Maintenance

This threat model is a living document. It is revisited when the schema changes, when a new exposure
source or hazard type is added, when the intake or hosting model changes, and at minimum alongside each
significant release. Findings from the committed `docs/audits/` and from CI security gates
(`pip-audit`, `gitleaks`, CodeQL) feed back into the threats and residual-risk sections here. Changes to
this file are recorded through the project's normal conventional-commit and CHANGELOG process.
