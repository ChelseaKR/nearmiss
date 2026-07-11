# Re-identification model for rare hazard types

This document is the detailed companion to [`THREAT-MODEL.md` T1 — Deanonymization via precise
coordinates or timing](THREAT-MODEL.md#t1--deanonymization-via-precise-coordinates-or-timing). The
threat model states the risk; this note works one specific attack all the way through — the
re-identification of a reporter from a **rare `hazard_type` on a low-traffic segment** — and then maps
each mitigation to the code and parameter that implements it, with the rationale for why each parameter
is set where it is. It also corrects a documentation error: earlier prose in `src/nearmiss/README.md`
described the public dataset as "jittered." **The pipeline does not jitter.** Privacy comes from
snap-to-segment aggregation and hard withholding, not from perturbing coordinates. That distinction
matters to anyone reasoning about the privacy guarantee, so it is spelled out below.

## Why rare hazard types are the sharp edge

Most of the privacy model is about the *location* quasi-identifier: a precise coordinate or a per-report
timestamp. Those are handled bluntly — they are simply never published (see T1). The subtler leak is a
low-cardinality *attribute* attached to a low-count place. A `hazard_type` drawn from a small closed
vocabulary is, on a busy street, harmless: "12 close-pass reports on 3rd St" describes a place, not a
person. On a street that sees one incident, the same attribute becomes a near-unique tag, and an
adversary who holds one more fact — who rides that street — can turn a place back into a person.

## Adversary model

The adversary this note targets is deliberately *ordinary*. Not a data broker, not a nation-state — a
**neighbor, a coworker, or an ex** who already knows two things the published dataset does not contain:

1. **A person's route.** They know that a specific individual bikes down a specific low-traffic segment
   — the quiet residential block the person leaves from every morning, the side street past a particular
   workplace.
2. **A rare event on it.** They either witnessed, were told about, or can plausibly guess a specific
   *kind* of near miss the person had there — a "dooring," a wrong-way driver, a specific unusual hazard
   type — the sort of thing a person mentions once and a listener remembers.

This adversary has no special access and no technical sophistication. Their entire capability is *side
knowledge* plus the public file. They are exactly the "curious neighbor" and "harasser" named in the
[THREAT-MODEL actor list](THREAT-MODEL.md#actors-and-adversaries), and they are the reason aggregation
alone is not enough.

## The attack

The attack is a join. The adversary takes three things and intersects them:

- a **rare `hazard_type`** (a value that appears once or a handful of times in the whole file),
- a **low-count segment** (a block with only a few reports, so the aggregate barely masks anyone), and
- their **side knowledge** (this person rides here; this is the sort of thing that happened to them).

If a thinly-populated segment publishes a `hazard_breakdown` that reveals `{"dooring": 1}` on the block
the adversary already associates with their target, the breakdown has done the adversary's work: it
confirms that *someone* reported that specific event on that specific block, and the adversary's side
knowledge supplies the name. Aggregation to the street segment did not stop this, because the leak was
never the coordinate — it was the **rare attribute in a thin cell**. The `report_count` alone is a
weaker version of the same attack: a segment showing a count of `1` on a block tied to one known rider
singles that rider out even without the hazard type.

So there are two doors to close: thin cells must not publish at all, and even cells that do publish must
not carry a rare-attribute breakdown that is itself thin.

## Mitigations, mapped to code and parameters

The published file is built by `src/nearmiss/publish.py` from the analysis in
`src/nearmiss/stats/__init__.py`, governed by two thresholds in `src/nearmiss/config.py`. Both doors
above map to one of those thresholds.

### `min_publish_n = 3` — the k-anonymity floor (closes the thin-cell door)

- **Where:** [`config.py:42`](../src/nearmiss/config.py) (`min_publish_n: int = 3`). Enforced by
  `assert_published_clean` in [`publish.py:99-116`](../src/nearmiss/publish.py), which *raises* a
  `PrivacyError` rather than emit a violating feature. The upstream decision is made in
  [`stats/__init__.py`](../src/nearmiss/stats/__init__.py) where a segment is marked
  `publishable = not (0 < count < config.min_publish_n)`.
- **What it does:** any segment with a non-zero report count below `min_publish_n` is **withheld
  entirely** — no geometry, no count, no breakdown, no metadata, no brief line. A published cell can
  therefore only mean "zero reports" or "at least three reports." It can never mean one or two.
- **Why the floor is 3, not 1 or 2:** the value the adversary wants to confirm is "exactly one person
  reported here." A floor of 1 publishes single-reporter cells and hands that confirmation over directly.
  A floor of 2 still publishes two-reporter cells, where either reporter, plus the adversary's knowledge
  that *the other* rider exists, re-identifies both. Three is the smallest floor at which a published
  cell provides no individual with certainty about any other individual — the minimum non-trivial
  k-anonymity guarantee (k = 3). It is the *floor*, chosen as small as the guarantee allows, precisely
  because of its cost below.
- **What it costs:** withholding is not free. Low-traffic streets — often exactly the residential blocks
  where a single scary near miss matters most to the person who lives there — fall below the floor and
  disappear from the published map entirely. The dataset systematically under-covers quiet streets.
  That suppressed coverage is the price of the guarantee, and it is stated here and in the data card so
  the gap is not mistaken for "no incidents here." Lowering the floor would recover that coverage only
  by trading away the k-anonymity guarantee, which is not an acceptable trade.

### `small_n = 5` — the rare-attribute floor (closes the thin-breakdown door)

- **Where:** [`config.py:41`](../src/nearmiss/config.py) (`small_n: int = 5`). Applied in
  [`stats/__init__.py`](../src/nearmiss/stats/__init__.py): `breakdown = dict(a.hazard_breakdown) if (a
  and count >= config.small_n) else {}`. Below `small_n` the `hazard_breakdown` is emitted as `{}` and
  the feature is flagged `low_sample`.
- **What it does:** even for a segment that clears the publication floor, the per-hazard-type breakdown
  is suppressed until the segment carries at least `small_n` reports. A rare `hazard_type` therefore
  cannot appear as a `{"dooring": 1}`-style entry in a thin cell — the exact join the attack depends on.
- **Why 5 is higher than the k-anonymity floor of 3:** the two thresholds guard different things and a
  breakdown needs a *higher* floor than a raw count. `min_publish_n` protects a single aggregate number:
  three reports is enough to keep any one of them from being singled out *as a count*. A
  `hazard_breakdown`, though, **partitions** that count across hazard types, and each partition cell is
  its own miniature aggregate that must independently resist singling-out. A segment with exactly three
  reports that clears `min_publish_n` could still break down into `{"dooring": 1, "close_pass": 1,
  "wrong_way": 1}` — three cells of size one, each as re-identifying as an un-withheld single-report
  segment. Requiring `small_n > min_publish_n` gives the partition headroom so its individual cells are
  not trivially thin, and 5 is the chosen margin: enough that a breakdown reflects a genuine local
  pattern rather than one memorable incident, while still low enough to publish breakdowns on
  moderately-reported streets. The breakdown floor is deliberately the more conservative of the two.

## Spatial precision: aggregation, not jitter

**The pipeline does not jitter, perturb, fuzz, or add noise to coordinates.** Any documentation that
says otherwise is wrong; the misleading "jittered" wording in `src/nearmiss/README.md` is corrected in
this change. Spatial privacy is achieved by two mechanisms, neither of which is perturbation:

- **Snap-to-segment aggregation (`snap_max_m = 25`).** [`config.py:38`](../src/nearmiss/config.py) sets
  `snap_max_m: float = 25.0`. The pipeline snaps each report to the nearest public street segment within
  25 m and then aggregates. Sub-segment precision is **discarded**, not scrambled: the published geometry
  is the real public street centerline — public infrastructure that describes a *place*, not a
  perturbed version of a *person's* location. There is nothing to reverse, because the fine coordinate
  was thrown away rather than moved. Jitter, by contrast, retains a perturbed coordinate that can be
  attacked statistically over repeat reports; snap-and-discard leaves no such coordinate.
- **The coordinate-leak assertion.** `publish.py` rounds published geometry vertices and never emits a
  per-report coordinate, and `assert_published_clean`
  ([`publish.py:99-116`](../src/nearmiss/publish.py)) checks every published vertex against the set of
  raw report points (rounded to 6 decimals) and **raises** `PrivacyError` if any published vertex
  coincides with a raw report location. `assert_metadata_clean` applies the same check (at 5 decimals)
  to the metadata sidecar. This is a hard, tested tripwire: publication fails closed rather than leak a
  point.

Framing this as "no jitter" is not a weaker claim — it is a stronger and more honest one. A jitter model
invites the question "how much noise, and can it be averaged out?" The snap-and-withhold model answers a
different, cleaner question: the precise coordinate is never in the published artifact at all, in any
form. See [`schema/dataset.schema.md`](../schema/dataset.schema.md) ("No jitter, no published
coordinate") for the same statement at the schema level.

## Residual risks

These mitigations bound the ordinary-adversary attack above; they do not eliminate every
re-identification path. Consistent with the [THREAT-MODEL "Stops at" text for
T1](THREAT-MODEL.md#t1--deanonymization-via-precise-coordinates-or-timing) and its
[Residual-risk section](THREAT-MODEL.md#residual-risk):

- **Repeat-visitor / linkage.** A contributor who files many reports clustered near one origin still
  leaks a *pattern*. Each report may sit in a well-populated, un-suppressed cell, yet the set of
  segments a single contributor touches can be linked across the dataset by an adversary with side
  knowledge, re-identifying the person even though no single cell violates a floor. Per-cell k-anonymity
  does not compose into whole-trajectory anonymity. Contributor-facing guidance therefore advises
  reporting sparingly near home, and the data card states this plainly so consent is informed.
- **Confirming a known address.** The thresholds stop an adversary from *discovering* that a specific
  person reported a specific incident. They are weaker against an adversary who already holds a candidate
  address and is only *confirming* a hypothesis: if that block clears the floors, the published
  aggregate is consistent with their guess, and absence below a floor is itself weak information
  ("fewer than three reports here"). The model reduces the adversary's certainty; it does not always
  drive it to zero.
- **Rare-combination residue above the floors.** `small_n` suppresses thin breakdowns, but a hazard type
  that is genuinely rare *city-wide* can still be locally unusual on a segment that clears `small_n`.
  Suppressing rare-attribute *combinations* more aggressively (extending the `small_n` breakdown rule)
  is tracked as intake-and-abuse item **B7**; this document is the "document the re-identification
  model" half of that item.

None of the above is claimed as solved. They are the acknowledged edges of a model that is honest about
where it stops.

## See also

- [`docs/THREAT-MODEL.md`](THREAT-MODEL.md) — T1 and Residual risk; this note is its detailed companion.
- [`docs/DATA-CARD.md`](DATA-CARD.md) — the published dataset's privacy section and parameters.
- [`docs/INTAKE-AND-ABUSE.md`](INTAKE-AND-ABUSE.md) — item B7 (privacy hardening for rare combinations).
- [`schema/dataset.schema.md`](../schema/dataset.schema.md) — the "no jitter, no published coordinate"
  guarantee at the schema level.
- `src/nearmiss/config.py`, `src/nearmiss/publish.py`, `src/nearmiss/stats/__init__.py` — the code and
  parameters this model maps to.
