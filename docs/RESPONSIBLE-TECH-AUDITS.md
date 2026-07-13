# Responsible-Tech Audits — nearmiss

Instantiates `docs/standards/RESPONSIBLE-TECH-FRAMEWORK.md`. **Last regenerated: 2026-07-05** (initial
version — this file did not exist before this date; see `audit-2026-07-05/nearmiss-REMEDIATION.md`
P2-1). Regenerate on each release per the framework's audit-as-artifact discipline.

## Applicability

- **A Ethics:** Applies. See [§A](#a-ethics--responsibility-audit).
- **B Bias:** Applies. Reporting bias (route-choice, reporter-pool, app-access, language,
  demographic/geographic, survivorship, salience, temporal) is a first-class, tested output
  (`stats/bias.py`) — not case-by-case here, because the whole project exists to counter one specific
  bias (raw counts confounding danger with traffic). See [§B](#b-bias--fairness-audit).
- **C Privacy:** Applies (DPIA: [`docs/DPIA.md`](DPIA.md)). See [§C](#c-privacy--data-protection-audit-dpia-style).
- **D Transparency:** Applies. See [§D](#d-transparency--explainability-audit).
- **E Accessibility:** Applies (ACR: [`docs/accessibility/ACR.md`](accessibility/ACR.md)). Three shipped
  HTML surfaces (`index.html`, `submit.html`, `embed.html`). See [§E](#e-accessibility-audit).
- **F Security:** Applies (threat model: [`docs/THREAT-MODEL.md`](THREAT-MODEL.md), residual-risk
  register: [`docs/THREAT-MODEL.md#residual-risk-register`](THREAT-MODEL.md#residual-risk-register)).
  See [§F](#f-security-audit).
- **AI-EVAL:** **N/A** — no LLM/AI SDK usage anywhere in the codebase (verified by grep). See
  [`docs/adr/0004-standards-applicability.md`](adr/0004-standards-applicability.md) for the dated ADR
  making this call and its trigger condition for re-evaluation.
- **I18N:** Applies (EN/ES) — civic-facing surface; see [`docs/I18N.md`](I18N.md).

---

## A. Ethics — responsibility audit

**What could go wrong?** A dataset framed as "where it's dangerous" could (a) be misread as an
official/complete record rather than a biased voluntary sample, (b) be used to target or embarrass
specific streets/residents rather than to advocate for infrastructure change, or (c) have its public
submission form abused to manufacture or suppress a hotspot (astroturfing).

**How do we test for it?**
- The "who could be hurt if this works exactly as intended" question: a city could point at a
  low-rate segment and de-prioritize it, even though "low rate" can mean "too few reports to say
  anything" (`confidence_label = uncertain`) rather than "safe." This is why the dataset never lets a
  sparse segment rank as if it were certain (hard rule 2) and why `docs/DATA-CARD.md` has an explicit
  "Out-of-scope and discouraged uses" section naming this exact misuse.
- `docs/LIMITATIONS.md` and `docs/DATA-CARD.md` name the non-goals ("not a 311 queue," "not for
  enforcement, surveillance, insurance, or punitive action against individuals") directly.

**What do we commit to?**
- An explicit non-goals statement (README "What it does," `docs/DATA-CARD.md` "Out-of-scope and
  discouraged uses," `docs/INTAKE-AND-ABUSE.md` "Non-goals").
- A misuse-resistance design for the public submission form (`docs/INTAKE-AND-ABUSE.md` Part B; the
  implemented subset in `docs/SUBMISSIONS.md`).
- A named accountable owner: Chelsea Kelly-Reif, sole maintainer (no diffusion of responsibility to
  hide behind).
- A kill-switch/rollback plan: `SECURITY.md`'s response process for privacy/integrity issues is
  "un-publish or roll back the affected GeoJSON... while a corrected... version is rebuilt" — this is
  the misuse/harm rollback plan, not just a security process.

**Enforcement:**
- **AUTO-GATE:** `tests/test_publish_privacy.py` (k-anonymity floor is mechanically enforced, not
  policy-only); `tests/test_moderation.py` (a public submission cannot bypass human review to reach the
  dataset).
- **REVIEW-GATE:** this document is the consequence-scan sign-off artifact (dated 2026-07-05). **Gap:**
  no *separate*, narrower "ethics sign-off" doc existed before this file — RTF-01 in the 2026-07-05
  audit noted this as PARTIAL; this section is intended to close it, but has not yet been re-audited
  against RTF-01's exact bar.

## B. Bias — fairness audit

**What could go wrong?** The published rate could read as an unbiased measure of danger when it is
actually a rate over a *self-selected, biased* sample, and the bias could systematically
under-represent exactly the people most at risk (people without smartphones, people who avoid
dangerous streets entirely, non-English speakers).

**How do we test for it?** `stats/bias.py` compares the reporter pool and the geographic spread of
reports against ridership/demographic baselines and reports over/under-representation per segment;
this is exercised by the test suite and surfaced in every brief (`brief.py` "Reporting bias" section,
never omitted).

**What do we commit to?** Eight named biases in `docs/DATA-CARD.md` § Known reporting biases
(route-choice, reporter-pool, app-access/digital-divide, language, demographic/geographic,
survivorship/avoidance, salience/severity, temporal/campaign) — not a generic disclaimer, but named
mechanisms with their direction of effect. EN/ES is treated as a first-class segment (a report's
`language` tag feeds the bias characterization), per the framework's explicit civic-repo guidance.

**Enforcement:**
- **AUTO-GATE:** the bias section is a required, non-optional part of every rendered brief
  (`render_brief` always calls `_render_bias_section`; there is no code path that omits it); i18n
  key-parity gates (`tools/check_catalog_parity.py`) ensure the EN/ES bias text stays in parity.
- **REVIEW-GATE:** a dedicated representational-harm review (who is over/under-represented in
  self-reported near-miss data, beyond the statistical-bias framing already in `stats/bias.py`) is
  **not yet a separately committed, dated artifact** — this is the same gap RTF-03 flagged in the
  2026-07-05 audit as PARTIAL. Recommended next step: a short dated addendum to `docs/DATA-CARD.md` or
  a new `docs/audits/representational-harm-review.md`, not yet written.

## C. Privacy & data-protection audit (DPIA-style)

**What could go wrong?** The public submission form (2026-06-29) accepts precise location data from
third parties for the first time; a bug or design gap in aggregation/withholding could re-identify a
reporter's home, workplace, or routine.

**How do we test for it?** See the full DPIA: [`docs/DPIA.md`](DPIA.md), and the threat model's T1/T2
and [residual-risk register](THREAT-MODEL.md#residual-risk-register) RR-1/RR-2. Data inventory,
retention, lawful-basis screening, and named gaps (including the currently-unaddressed lack of a
retention/deletion policy, Gap G1 in the DPIA) all live there rather than duplicated here.

**What do we commit to?** No identity field ever (structural, not policy); precise location discarded
after segment-snapping and never published (`assert_published_clean`, tested); k-anonymity floor;
env-only secrets, never committed (`gitleaks` pre-commit + CI).

**Enforcement:**
- **AUTO-GATE:** `tests/test_publish_privacy.py` (the "guaranteed absent" denylist), `server.py`'s
  `_redact_path` + `tests/test_observability.py` (no raw-store paths reachable or logged), `gitleaks`
  (pre-commit and CI, no mute).
- **REVIEW-GATE:** [`docs/DPIA.md`](DPIA.md), dated 2026-07-05, sign-off recorded there. **Named gap:**
  no automated retention/deletion job exists yet (DPIA Gap G1) — tracked, not hidden.

## D. Transparency & explainability audit

**What could go wrong?** A rate, ranking, or hotspot claim could be taken at face value without its
interval, its `n`, its exposure source/date, or its bias caveat — exactly the "heat-map lie" the whole
project exists to refuse.

**How do we test for it?** Every published rate carries `rate_ci_low`/`rate_ci_high`/`n`/
`exposure_source`/`exposure_date`/`confidence_label` (schema-enforced, `schema/dataset.schema.md`);
every brief states the bias caveat and a plain-language glossary before the numbers
(`brief._render_intro`/`_render_glossary`).

**What do we commit to?** Visible sourcing on every number (never a bare rate); explicit
uncertainty/confidence labeling (`certain`/`uncertain`/`exposure_unknown`, never silently omitted);
`docs/LIMITATIONS.md` stating plainly what the dataset cannot tell you; `docs/METHODOLOGY.md` recording
every statistical choice and its honest caveats (including several sections marked PLANNED rather than
overclaimed as implemented, per that document's own claim-tagging convention).

**Enforcement:**
- **AUTO-GATE:** `schema/dataset.schema.md`'s JSON Schema validation in CI rejects a published feature
  missing its interval/`n`/source fields; `tests/test_brief.py` checks the bias section is always
  present.
- **REVIEW-GATE:** `docs/DATA-CARD.md` and `docs/METHODOLOGY.md` are the committed transparency
  artifacts, both reviewed as part of this 2026-07-05 pass. No model card / datasheet-for-AI applies
  (AI-EVAL is N/A); `docs/DATA-CARD.md` already follows the Datasheets-for-Datasets shape this audit
  asks for.

## E. Accessibility audit

**What could go wrong?** A disabled road user — among the people most endangered by a bad street and
most likely to need this exact map — could be unable to read the findings.

**How do we test for it?** Structural gate (`tools/a11y_check.py`, merge-blocking) + automated
axe-core (jsdom, merge-blocking via `npm ci && npm run axe` in CI, fixed 2026-07-05 to install from the
committed lockfile — see P0-3 in the remediation log). Manual NVDA/VoiceOver review and browser-rendered
gates (Lighthouse, pa11y) are **not yet in place** — named honestly in the ACR rather than implied.

**What do we commit to?** WCAG 2.2 AA target; a non-visual table equivalent to every map finding; risk
conveyed in text/pattern, never color alone; a committed ACR (VPAT 2.5 Rev 508).

**Enforcement:**
- **AUTO-GATE:** structural + axe-core, both merge-blocking (`ci.yml` `accessibility` job).
- **REVIEW-GATE:** [`docs/accessibility/ACR.md`](accessibility/ACR.md) — **stale relative to the
  2026-06-29 submission form and embed widget** (report date 2026-06-17, predates both surfaces). Not
  re-issued as part of this pass — flagged explicitly as a carried-forward gap (P2-3 in the remediation
  plan is the full re-audit; that is M-effort and out of scope for this pass, so the honest move here
  is naming the staleness, not silently leaving the ACR looking current).

## F. Security audit

**Frame:** ASVS 5.0 target level and the narrative threat model, on top of the mechanical scanners
already running in CI.

**ASVS 5.0 level declaration:** **Level 2.** Rationale: nearmiss is not processing authentication
credentials or handling payment data (ASVS L2's classic trigger), but it now **ingests public
submissions of precise-location data from third parties** (2026-06-29) — data that is PII-adjacent
(location + timing can re-identify a person's routine) even though no name/email/identity field
exists. L1 (opportunistic) is judged insufficient for a system accepting third-party sensitive-adjacent
input from the open internet; L3 (the highest bar, aimed at systems handling high-value transactions or
requiring the highest degree of trust) is judged more than this project's risk profile warrants. This
is a **first declaration**, not yet checked line-by-line against every ASVS 5.0 L2 control — that
control-by-control mapping is future work, tracked as a P2/P3-scale item, not fabricated here as done.

**What could go wrong?** See `docs/THREAT-MODEL.md` T1–T6 in full; summarized: deanonymization,
report/dataset poisoning, exposure-source tampering, a naive consumer misreading volume as danger,
supply-chain compromise, secret leakage.

**How do we test for it?** STRIDE-shaped threat model (`docs/THREAT-MODEL.md`); abuse-case tests
(`tests/test_publish_privacy.py`, `tests/test_moderation.py`); dependency/secret/workflow scanning in
CI.

**What do we commit to?** A documented threat model with a dated review
([`docs/THREAT-MODEL.md`](THREAT-MODEL.md), reviewed 2026-07-05) and a residual-risk register with a
named owner (added 2026-07-05); no fixed HIGH/CRITICAL findings merged (`pip-audit --strict`,
merge-blocking, no mute).

**Enforcement:**
- **AUTO-GATE:** `pip-audit --strict` (blocking), `gitleaks` (pre-commit + CI, blocking), CodeQL
  (`python`, and as of 2026-07-05 also `javascript` and `actions` — closing the "web JS unscanned"
  finding open since 2026-06-21), `zizmor` (added 2026-07-05, blocking on `high` severity, see
  `ci.yml`'s `zizmor` job).
- **REVIEW-GATE:** threat-model + residual-risk-register sign-off — done, dated 2026-07-05
  ([`docs/THREAT-MODEL.md`](THREAT-MODEL.md)). Scheduled OpenSSF Scorecard
  (`.github/workflows/scorecard.yml`) and scheduled TruffleHog full-history verified-secret scan
  (`.github/workflows/secret-scan-scheduled.yml`) were also added 2026-07-05; **neither has run yet as
  of this writing** (they take effect once this branch is committed and pushed), so their results are
  not yet a committed artifact — that will be true after the first scheduled run.

### §F declarations (no blanks — SEC-40)

| Item | Declaration |
|---|---|
| **ASVS 5.0 level** | **L2** (declared above; control-by-control checklist not yet completed). |
| **Container / image scanning** | **N/A — no Dockerfile, no container image is built or published** (verified by `find . -iname Dockerfile*`). If a container image is ever added, this row must flip to a Trivy/Grype scanning commitment before that image ships. |
| **SBOM generation** | **Implemented but not yet exercised.** The tag-triggered release workflow builds a CycloneDX SBOM and attaches it to the release; no tag has run that path yet, so there is no published SBOM to claim or verify. |
| **Artifact signing** | **Implemented but not yet exercised.** The tag workflow performs keyless cosign signing and SLSA provenance, but no version has ever been tagged or signed. The first real release remains an owner/Trusted-Publishing gate, not a code gap. |
| **Secret management** | **Environment variables / CI secret store only, never committed.** Enforced by `gitleaks` pre-commit (bumped to v8.30.1 in this pass) and CI (blocking, full-history diff), plus the scheduled TruffleHog verified-secrets scan added 2026-07-05. No secrets manager / vault is in use or currently needed (no deployed always-on service holds credentials today). |
| **VEX (vulnerability exploitability exchange)** | **N/A — no known unfixed vulnerabilities exist to justify a waiver for.** `pip-audit --strict` is blocking with no mute; if a future unfixable finding needs a documented waiver, it is recorded here rather than silently suppressed. |
| **Branch protection / ruleset artifact** | **⛔ Not committed — this is a live GitHub repository setting, not a file this pass can create or verify from a local checkout.** See the remediation log's Execution Log entry for the exact command the maintainer must run (`gh api repos/ChelseaKR/nearmiss/rulesets` to configure, then export and commit as `docs/audits/branch-ruleset.json`). |

---

## See also

- [`docs/THREAT-MODEL.md`](THREAT-MODEL.md) — full adversary model + residual-risk register.
- [`docs/DPIA.md`](DPIA.md) — the privacy audit's dated artifact.
- [`docs/accessibility/ACR.md`](accessibility/ACR.md) — the accessibility audit's dated artifact
  (currently stale relative to the 2026-06-29 surfaces — see §E above).
- [`docs/DATA-CARD.md`](DATA-CARD.md), [`docs/LIMITATIONS.md`](LIMITATIONS.md) — the transparency
  audit's dated artifacts.
- [`docs/adr/0004-standards-applicability.md`](adr/0004-standards-applicability.md) — the AI-EVAL N/A
  declaration.
