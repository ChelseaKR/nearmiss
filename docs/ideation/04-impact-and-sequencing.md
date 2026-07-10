# Impact × effort and sequencing — drafted 2026-07-01

Covers FIX-01…FIX-14 (`02-large-scale-fixes.md`) and EXP-01…EXP-16
(`03-expansions.md`). Impact is judged against the project's own success criterion —
"holds up when a skeptical traffic engineer pushes back" — plus reach (who benefits)
and portfolio leverage. These are triage judgments from a code read, not commitments.

## Impact × effort matrix

**Impact key:** ★★★ = protects or extends the core credibility claim;
★★ = materially improves a major audience's outcome; ★ = valuable, narrower.

| ID | One-liner | Impact | Effort |
| --- | --- | :---: | :---: |
| FIX-01 | Land orphaned research branch (RR-02/RR-05) on main | ★★★ | M |
| FIX-02 | Network-topology Gi\* weights | ★★★ | L |
| FIX-03 | Doc-code claims-parity sweep + CI gate | ★★★ | M |
| FIX-04 | Exposure trust tiers / corroboration / staleness | ★★★ | L |
| FIX-05 | First-class analysis window | ★★★ | S–M |
| FIX-06 | Per-hazard-type rate layers | ★★ | M |
| FIX-07 | Quality-tier sensitivity split | ★★ | M |
| FIX-08 | Strict config validation | ★★ | S |
| FIX-09 | Run manifest + stage telemetry | ★★ | M |
| FIX-10 | Machine-readable dataset schema + contract gate | ★★ | M |
| FIX-11 | Hashed CI installs, release automation, signing | ★★ | L |
| FIX-12 | Spatial index for quadratic cores | ★★ | L |
| FIX-13 | Single-source web i18n | ★ | M |
| FIX-14 | Numerical hardening + property/coverage tests | ★★★ | M |
| EXP-01 | Publish-time null-calibration panel | ★★★ | M–L |
| EXP-02 | Versioned releases + change attribution | ★★ | M |
| EXP-03 | Corridor aggregation | ★★ | M–L |
| EXP-04 | Source-adapter framework (incl. SimRa rescue) | ★★★ | L |
| EXP-05 | DP segment×time-band release | ★★ | XL |
| EXP-06 | Contributor data-rights tooling | ★★ | M |
| EXP-07 | Moderation transparency report | ★ | S–M |
| EXP-08 | Extract "honest rates" library | ★★ | L |
| EXP-09 | Planted-truth benchmark suite | ★★ | L |
| EXP-10 | HR1–HR5 conformance verifier | ★★ | M |
| EXP-11 | QGIS plugin | ★ | L |
| EXP-12 | Heat-map-lie teaching module | ★★ | M |
| EXP-13 | Locale scaling kit | ★ | M |
| EXP-14 | Governed open data standard | ★★★ | XL |
| EXP-15 | Federated instance commons | ★★ | XL |
| EXP-16 | Pre-registered prospective evaluation | ★★★ | XL (elapsed) |

**Best value-per-effort quadrant:** FIX-01, FIX-03, FIX-05, FIX-08, FIX-14, EXP-01,
EXP-07, EXP-10.

## Dependency notes

- **FIX-01 unblocks the ledger.** Until the research branch lands, every document
  that cites RR-02/RR-05 as shipped is wrong on `main`. Do it first; carry the
  `msgpack>=1.2.1` pin through the merge.
- **FIX-03 depends on FIX-01** (the claims sweep must audit post-merge reality) and
  is cheaper if FIX-02/06/07 decisions (implement vs. reword) are made in the same
  pass.
- **Graph chain:** FIX-02 → EXP-03 (corridors need the street graph) and feeds
  FIX-12 (shared neighbor infrastructure). FIX-12 → EXP-01 at scale (200
  calibration re-runs) and EXP-09 (benchmark runtimes).
- **Provenance chain:** FIX-09 (manifests) → EXP-02 (change attribution) → FIX-11
  (releases to attribute between) → EXP-16 (frozen, verifiable predictions) and
  EXP-15 (signed federation).
- **Schema chain:** FIX-10 → EXP-10 (verifier validates against the schema) →
  EXP-11 (plugin), EXP-14 (standard), EXP-15 (federation entry gate).
- **Exposure chain:** FIX-04 + FIX-05 before serious real-city publication
  (Sacramento): trust tiers and windows are what make a real dataset honest, not just
  the demo. EXP-04 feeds FIX-04 with the multi-source reality it models.
- **i18n chain:** FIX-13 → EXP-13. Do neither between now and landing FIX-01 (the
  branch merge already collides with the gettext migration).
- **Stats safety net:** FIX-14 should precede FIX-02 and FIX-12 — refactor the
  numerical core only after the invariants are pinned.

## Suggested sequence (beyond the existing roadmaps)

The existing plans already sequence RR-01…RR-15/RE-01…RE-12 (see
`docs/RESEARCH-ROADMAP.md` on the research branch) and R/E items. This sequence
slots the *new* IDs around them.

**Now (ledger integrity + cheap correctness; ~2–3 weeks of focused work):**
1. FIX-01 — merge the branch; reconcile docs to code.
2. FIX-08 — strict config validation (an afternoon that removes a silent-wrong-number
   class).
3. FIX-03 — claims-parity sweep + gate (do the reword-vs-implement triage here).
4. FIX-14 — property/coverage harness (makes §9.2 true; safety net for everything
   later).
5. FIX-05 — analysis window (small, and every real-data step after it is dishonest
   without it).
6. EXP-07 — moderation transparency (small, pairs with the RR/RE intake work already
   sequenced).

**Next (make the statistics claims fully real; make real cities publishable):**
FIX-02 (network weights) → FIX-06 + FIX-07 (per-type rates, sensitivity split) →
FIX-04 (exposure tiers) with EXP-04 (adapter framework, SimRa rescue) → FIX-09 (run
manifests) → FIX-10 (dataset schema) → EXP-01 (calibration panel) → EXP-10
(conformance verifier). This block is what turns the Sacramento config from
aspiration into a defensible published dataset.

**Later (scale, reach, and bets):**
FIX-11 + FIX-12 (release engineering; performance headroom) → EXP-02, EXP-03,
EXP-08, EXP-09, EXP-12 (leverage the hardened core) → FIX-13 + EXP-13 (locale
scale-out) → EXP-11 (QGIS) → then, and only with their gates cleared: EXP-05 (DP),
EXP-16 (pre-registration), EXP-14/EXP-15 (standard, federation).

## Items gated on humans, SMEs, legal review, or real data — defer and say so

Per the portfolio ethos: these are **not** startable on synthetic effort alone. Each
should be reported as "designed, gated, waiting" rather than simulated or faked.

| Item | Gate | What specifically must happen first |
| --- | --- | --- |
| EXP-05 (DP time bands) | **Privacy SME** | A qualified privacy researcher reviews the mechanism, ε, and composition with the GeoJSON release; red-team pass (THREAT-MODEL T1 adversary). No synthetic sign-off counts. |
| EXP-16 (prospective eval) | **Statistician + real data** | A real statistician approves the frozen scoring rule; requires accumulating real reports (and `RE-01`'s official-collision path for the strong version — itself already deferred pending real data). Elapsed calendar time cannot be compressed. |
| EXP-14 (data standard) | **Human partners** | Real conversations with BikeMaps/SimRa maintainers and ≥1 agency data owner before a v1 draft; a standard with one implementer is a rename. |
| EXP-15 (federation) | **Legal/governance** | Written de-listing and liability policy for rogue instances; review of trademark/name-use for conformance claims. |
| EXP-04 upstream terms | **Legal-lite** | Confirm BikeMaps/SimRa data licenses permit redistribution in adapted form before publishing any real derived dataset (REAL-DATA.md notes BikeMaps points are public; verify terms, don't assume). |
| EXP-06 (data rights) | **Policy decision by maintainer** | Retention windows and deletion semantics are governance choices, not engineering defaults; document the decision in an ADR. |
| FIX-02/FIX-06/FIX-07 method changes | **Statistical review** | The research roadmap's own rule applies: "synthetic personas cannot certify a statistical method." Fixture validation is necessary but a real methodologist's review is the bar before published datasets switch over. |
| RR-14 (manual screen-reader pass) | **Human tester** | Already tracked; restated here because EXP-12/EXP-11 outputs inherit the same requirement — automated axe runs do not discharge it. |
| Real-city publication (Sacramento/Davis) | **Real data + community consent** | Exposure counts (SACOG/CA AT) must be real; the dataset_note/mode-scope labeling (RR-07) applied; and — per the community-ownership stance — a local advocacy contact who actually wants the dataset published. |

Everything else in this folder is executable with committed synthetic fixtures and
honest labeling, which is exactly how the repo has shipped its first two datasets.
