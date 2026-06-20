# What this can't tell you

nearmiss is built to survive a skeptical traffic engineer. Part of that is saying,
plainly and in one place, what the data and the method **do not** support — before
someone uses it to claim something it can't bear. If you came to attack the
numbers, this page is the list of attacks; for most of them, the honest answer is
"yes, and here is how we bound it."

This complements the [data card](DATA-CARD.md) (per-dataset biases and the schema
crosswalk) and the [methodology](METHODOLOGY.md) (how the numbers are computed).
The five [hard rules](../README.md) are referenced as HR1–HR5.

## The headline caveats

1. **A near-miss is not a crash.** The crowdsourced reports are self-reported
   near-misses and hazards, which by definition usually leave no police record.
   They are a *leading indicator*, not verified injuries or a KABCO/MMUCC-coded
   collision statistic, and are never presented as one. Severity is the
   reporter's assessment and is never republished per report. (HR3)

2. **Reporting is self-selected, so the numerator is biased.** People who report
   skew toward those who know the tool exists, have a phone, feel safe reporting,
   and report in a language we offer. Streets used by under-represented groups
   will be *under*-reported. We name this rather than hide it (HR3); the bias
   audit (`bias.py`, and the planned visible panel) characterizes who is over- and
   under-counted. Exposure normalization corrects for *volume*, not for *who
   chooses to report*.

3. **Exposure is the shakiest input, and we don't pretend otherwise.** A rate is
   only as good as its denominator. Where we have no trustworthy count, the
   segment is published as **"exposure unknown"** and never ranked as if certain
   (HR1). Where a denominator is *modeled* rather than measured, it is labeled
   `modeled …` in the data and flagged in the table — treat those rates as
   illustrative, not measured.

4. **The confidence interval covers the count, not the denominator.** The 95% CI
   is a Poisson/Wald interval on the *reports* given a fixed exposure value; it
   does **not** yet propagate uncertainty in the exposure estimate itself. So the
   true uncertainty on a rate is *wider* than the interval shown, especially where
   exposure is sparse or modeled. We state this rather than imply false precision
   (HR2). Propagating exposure uncertainty into the interval is tracked as
   roadmap item R28.

5. **The unit of analysis is a block, and blocks are arbitrary (MAUP).** Results
   can shift if you draw the segments differently — the modifiable areal unit
   problem. We split streets at intersections for a defensible, reproducible unit,
   but a hotspot at one granularity may dissolve at another. Rank *stability*
   under re-segmentation is a known open analysis (and an honest place to push).

## More specific limits

- **Small numbers are loud.** A single extra report can swing a low-`n` block.
  Segments below the minimum sample are marked uncertain or withheld for
  k-anonymity (HR4); a rate with a wide CI is telling you it doesn't know yet.
- **Significance is not magnitude.** "★ Significant" (Getis-Ord Gi\*, FDR-corrected)
  means *hotter than exposure and chance explain* — not "the worst." A significant
  block can have a modest rate; a scary-looking rate can be non-significant.
- **No time dimension is published.** To protect contributors, per-report
  timestamps are not released (HR4), so the public dataset cannot answer
  "dangerous at the 3pm school bell." Aggregated, privacy-safe temporal bands are
  a roadmap item, not a current capability.
- **Mode scope is per-city and often cyclist-only.** The main real source
  (BikeMaps.org) is cycling-centric. Pedestrian, wheelchair, and scooter hazards
  may be sparse or absent in a given city even though the schema supports them;
  the dataset should be read for the modes it actually covers (R33).
- **Geocoding and snapping are approximate.** Reports are snapped to the nearest
  segment within a threshold; a report just over the line, or a low-confidence
  location, is flagged, not silently forced onto a block.
- **It is a measurement, not a mandate.** A hotspot is evidence for a
  conversation, not an automatic verdict on cause or fix. Causes (sightlines,
  speed, signal timing, road design) require local engineering judgment.

## What it *can* tell you

Used within these limits, nearmiss answers one question well, that raw dot-maps
answer badly: **where the rate of reported near-misses per unit of cycling is
statistically higher than exposure and chance alone would explain** — with an
interval that admits its own uncertainty, a denominator that is never invented,
and a method that regenerates from raw inputs with `make reproduce` (HR5). That is
a narrower claim than "this is the most dangerous street," and a defensible one.

## How to attack this responsibly

If you want to stress-test a published dataset: re-segment and check whether the
top hotspots are stable (MAUP); compare against official collision data where it
exists and see if they agree where both are present; inspect the
`exposure_unknown`/modeled flags and the bias notes in the data card; and re-run
`make reproduce` to confirm the numbers fall out of the raw inputs. If something
here is overclaimed, that is a bug under HR3 — please file it.
