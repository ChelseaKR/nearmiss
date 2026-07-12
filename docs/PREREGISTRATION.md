# Pre-registered prospective evaluation (EXP-16)

`RE-01` (see the research backlog) is a *retrospective* validation study: it
checks the method against data that already exists, after the fact. That is
useful, but it is not immune to the garden of forking paths — with the data
already in hand, it is always possible, even unintentionally, to choose the
comparison that makes the method look best.

This is the prospective, unfakeable version. Before a period's evaluation
window opens, the currently FDR-significant corridors are **frozen** — hashed,
timestamped, and committed — so nobody, including the maintainers, can revise
the prediction after seeing how it turned out. One period later, those frozen
predictions are scored against independent held-out data (new reports; official
collision data once `RE-01`'s pipeline exists), and the score is committed as a
dated artifact **whether the method's predictions held up or not**. Publishing
a null or negative result with the same prominence as a positive one is the
whole point — it is what makes this different from every other claim in the
project's `README.md` and briefs.

If the scored result ever contradicts this document's framing, this document
is wrong and the scored result governs.

## The mechanism

```
nearmiss preregister --config config/<city>.toml
    -> data/published/preregistration/<slug>-<date>.json           (the frozen predictions)
    -> data/published/preregistration/<slug>-<date>.manifest.json  (hash + timestamp)

# ... one evaluation period later, run against the SAME config pointed at the
# next period's independent reports ...

nearmiss score-preregistration \
    --registration data/published/preregistration/<slug>-<date>.json \
    --config config/<city>-next-period.toml
    -> data/published/preregistration/<slug>-<date>-scored-<date2>.json
```

**Registration** (`nearmiss preregister`, `src/nearmiss/preregister.py:write_registration`)
runs the normal analysis and takes every segment currently flagged
`significant` *and* `publishable` (the same k-anonymity floor the public
GeoJSON uses — a registration is never a new privacy surface). It writes two
files, mirroring the split-artifact-then-hash idiom `nearmiss publish` already
uses for the public GeoJSON (a hash can't be embedded in the thing it hashes):

- the **artifact**: the flagged segment IDs and their predicted rates/CIs, the
  method params frozen at that moment (so a later config change can't quietly
  change what "the prediction" meant), and the scoring rule text itself;
- the **manifest**: the artifact's SHA-256 and the UTC registration timestamp.

Registering twice for the same city on the same day fails loudly rather than
overwriting — a pre-registration is a one-time freeze for a given evaluation
window, not a file to retry until the flagged set looks good.

**Scoring** (`nearmiss score-preregistration`,
`src/nearmiss/preregister.py:score_registration`) takes the registration and an
analysis bundle built from the held-out period's data, and computes:

- **`hit_rate`** — the fraction of flagged, evaluable segments that are *still*
  a Getis-Ord Gi\* / Benjamini-Hochberg-FDR-significant hotspot in the held-out
  period, with a Wilson 95% CI (`src/nearmiss/stats/rates.py:wilson_ci`).
- **`rank_correlation`** — Spearman's rho between each flagged segment's
  registered rate and its held-out rate, over the same evaluable subset
  (`src/nearmiss/stats/rank.py:spearman_rho`; `None`, not 0.0, if undefined).

A flagged segment that gets withheld for k-anonymity or loses its exposure
match in the held-out period is `unevaluable`, not a miss — it is reported
separately, and `n_flagged` always stays visible next to `n_evaluable` so a
shrinking evaluable set can never quietly inflate the hit rate.

The scored artifact is written unconditionally: there is no code path that
scores a registration and *doesn't* write the result.

## The SME gate — read this before citing a registration as evidence

**A statistician must review and sign off on the scoring rule above before any
registration produced under it is cited as evidence that near-miss data is a
leading indicator.** This is not a formality this codebase can satisfy on its
own. The sign-off is tracked in a human-edited file,
[`docs/preregistration/scoring-rule-signoff.json`](preregistration/scoring-rule-signoff.json),
which starts as:

```json
{
  "status": "pending_statistician_review",
  "reviewer_name": null,
  "reviewed_at": null
}
```

Every registration artifact stamps whatever that file's `status` was at
registration time into `scoring_rule.signoff_status`, so a reader checking a
registration never has to take "yes, this was reviewed" on faith — it's in the
artifact they're holding. **Registrations produced while `signoff_status` is
`"pending_statistician_review"` are valid dry runs of the mechanism and
nothing more** — they exercise the hashing, the freeze, and the scoring math
against real code, but they are not yet evidence of predictive validity, and
should not be described that way in a brief, a README claim, or a public
statement.

To actually sign off: a statistician reviews the `hit_rate` / `rank_correlation`
definitions in `SCORING_RULE_DESCRIPTION`
(`src/nearmiss/preregister.py`) — ideally against a real draft registration
artifact, not just this prose — and a maintainer records their verdict by
editing `scoring-rule-signoff.json` with the reviewer's name, affiliation, the
review date, and any notes (including a revised rule version if they require
changes; bump `SCORING_RULE_VERSION` to match). Only after that edit does a
subsequent `nearmiss preregister` run stamp `signoff_status` as approved.

## Why the effort estimate is "XL (elapsed)," not "XL (work)"

The registration and scoring code above is small — freeze a list, hash it,
score it later against the same statistics the rest of the pipeline already
computes. The cost is *time*: a registration is only meaningful once it sits
in front of a real, unmodified evaluation window, and scoring needs a second,
independent period of real accumulating reports (a live city config —
currently Sacramento — plus the source-adapter work that feeds it). Running
`nearmiss preregister` and `nearmiss score-preregistration` back-to-back
against the bundled demo fixtures (as the test suite does) proves the
mechanism works; it is explicitly **not** a real prospective evaluation, and
no such run should be represented as one.

## Excellence bar

A dated, hash-verifiable prediction artifact exists before a real evaluation
window opens (`verify_registration()` recomputes and checks the SHA-256), the
scoring rule carries a real statistician's sign-off before that registration
is cited as evidence, and the scored outcome — win or lose — is published
under `data/published/preregistration/` with the same prominence as the
prediction it scores.
