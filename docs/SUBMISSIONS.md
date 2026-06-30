# Public submissions & the moderation queue

**Status:** implemented (phase-1 slice). This is the working subset of the
[contributor intake & abuse design](INTAKE-AND-ABUSE.md): a public way to submit
a near-miss, plus the moderation queue that gates it. The expensive
network-edge defenses in that design (rate limiting, proof-of-work, trust tiers)
remain future work and are called out below.

> One hard invariant governs everything here: **a public submission never
> reaches the dataset until a human approves it**, and even then it only becomes
> public through the normal aggregate-and-withhold publish path. Nothing a
> contributor sends is shown as-is.

## The contributor path (the form)

[`web/submit.html`](../web/submit.html) + [`web/submit.js`](../web/submit.js) is
a framework-free, WCAG 2.2 AA accessible form (native controls, full keyboard
operation, labels and error text, ≥ 24 px targets, no visual CAPTCHA — it passes
the same `tools/a11y_check.py` structural gate and the `axe-core` run as the rest
of the site). It collects exactly the fields the
[report schema](../schema/report.schema.json) defines:

- a **location** — "use my current location" (opt-in geolocation), manual
  lat/lon, or a free-text address/intersection;
- a **hazard type** and a **severity** (required);
- optional **mode**, **language**, and a **note**.

On submit, the form builds a schema-valid report (a fresh UUID, the local event
time with offset, `schema_version`) and — because the published site is static
and serverless by default — hands it back to the contributor to **download or
copy** and send to the maintainers (or a local advocacy org), who run
`nearmiss submit`. A deployment that has a serverless intake endpoint can instead
set `data-endpoint` on the `<form>` and the same payload is `POST`ed directly;
if that request fails, the form falls back to the offline copy so a curbside
submission is never lost.

### Privacy posture (what we collect, and don't)

- **No identity is collected.** There is no name, email, account, or phone
  field — by construction, not by policy. The note field explicitly warns
  against including names, plates, phone numbers, or emails.
- **Geolocation is opt-in** and never silently stored or transmitted; it only
  fills the lat/lon inputs the contributor can then edit.
- The precise report is **private**. It is published only after aggregation to a
  public street segment, with low-count blocks withheld (k-anonymity) and no
  per-report coordinate, time, note, mode, or severity ever emitted — the
  existing `publish.py` invariants (`assert_published_clean`), unchanged.
- Full adversary analysis and residual risk: [`THREAT-MODEL.md`](THREAT-MODEL.md).

## The moderation queue (server-side)

[`src/nearmiss/moderation.py`](../src/nearmiss/moderation.py) implements the
pending → approved/rejected lifecycle:

| Step | Command | Effect |
|---|---|---|
| Submit | `nearmiss submit <file> --config C` | validate against the schema; enqueue **PENDING** in the private store (`data/pending/`, gitignored like `data/raw/`); compute review flags |
| Review | `nearmiss moderate list --config C [--status pending]` | list submissions and their flags |
| Approve | `nearmiss moderate approve <id> --config C` | mark approved; append to the approved-reports store the pipeline can consume |
| Reject | `nearmiss moderate reject <id> --reason "…" --config C` | mark rejected; the report never enters the approved store |
| Export | `nearmiss moderate export <out> --config C` | write the **approved** reports as a pipeline-ready `reports.json` |

The approved file is then used like any other reports source (point a city
config's `reports` at it, or `nearmiss intake` it), so an approved submission
flows through exactly the same dedupe → snap → classify → exposure → rate →
publish path as every other report. There is no privileged path to publication.

### Abuse defenses implemented here (a testable subset)

Per the design doc's B-series, the controls that belong in this library module
are the reproducible, fixture-testable ones:

- **Schema validation at the boundary** (B-A2): a malformed or malicious
  submission is rejected at `submit`, never queued.
- **Identifier-leak heuristics** (B7): a note that looks like it contains an
  email, phone number, or license plate is **flagged for review** — never
  blocked, never auto-dropped, and never auto-approved.
- **Near-duplicate detection** (B4/B5): a submission matching an existing one on
  coarse location + hazard type + event hour is flagged `possible_duplicate`.

Flags surface a submission for a closer human look; approval is always an
explicit, recorded action.

### Out of scope here (network-edge, future work)

Rate limiting, proof-of-work / accessible challenges, trust tiers, and the
serverless endpoint itself live at the deployment edge, not in this library.
They are designed in [`INTAKE-AND-ABUSE.md`](INTAKE-AND-ABUSE.md) §B2–B3, B6 and
remain the maintainer's open decisions (hosting, identity, moderation SLA).

## Tests

[`tests/test_moderation.py`](../tests/test_moderation.py) covers the invariant
(pending/rejected submissions are never exported), idempotent approval,
schema rejection, the flagging heuristics, persistence to the private store, and
an end-to-end check that an approved submission still passes through k-anonymity
withholding at publish.
