"""EXP-05 prototype — privacy-budgeted segment x time-band release (differential privacy).

STATUS: PROTOTYPE. Disabled by default (``dp_segment_time.enabled = false``) and,
even when enabled, hard-gated behind an explicit, human-entered SME sign-off
reference (``dp_segment_time.sme_signoff_ref`` in config) — see
``docs/privacy/exp-05-dp-segment-time-bands.md`` for the mechanism, epsilon
rationale, sensitivity analysis, and open questions a privacy reviewer must
check before that config field is ever set for a real (non-synthetic)
publication. Flipping ``enabled`` on without a sign-off reference raises
:class:`DPSignoffMissingError` rather than silently degrading privacy.

Today ``stats/temporal.py`` answers "when are hazards reported?" only as a
CITY-WIDE aggregate (see its module docstring), because a per-segment,
per-time-band cell is exactly the kind of low-count cell that can
re-identify a contributor's commute — k-anonymity suppression (hard rule #4,
``config.min_publish_n``) withholds it entirely rather than risk that. This
module prototypes the alternative the ideation doc (``docs/ideation/
03-expansions.md``, EXP-05) asks for: instead of an all-or-nothing
suppression threshold, add calibrated Laplace noise to every
(segment, part_of_day) cell so the *true* small count is never released, but
a noisy estimate can be — *if*, and only if, the noise is small enough
relative to the counts to be useful. The ideation doc names the risk of
"utility-theater" (noise so large the bands are meaningless) explicitly;
this module measures that risk (``utility_theater_risk``) rather than
assuming the mechanism is worth shipping.

Mechanism (epsilon-differential privacy, Laplace mechanism):
    For each cell c = (segment_id, part_of_day), the true count n_c is
    released as ``n_c + Lap(0, sensitivity / epsilon)``, then clamped to a
    non-negative integer for publication (``published_count``). Clamping at
    zero is a standard but *not* unbiased post-processing step — it slightly
    over-estimates near-zero true counts on average; this is a known,
    documented approximation, not a hidden one.

Sensitivity:
    Each report contributes to exactly one (segment, part_of_day) cell (see
    ``stats/temporal.py``'s ``_part_of_day`` and the pipeline's segment
    snapping), so adding or removing a single report changes exactly one
    cell's true count by exactly 1: global sensitivity = 1 per cell for a
    single-report add/remove. This is **event-level** DP: it bounds the
    influence of one *report*, not one *contributor*. This module does not
    cap how many reports a single contributor may have snapped into cells in
    a release, so a contributor who files k reports spends k times the
    per-report privacy loss on their own routine. Closing that gap (a
    per-reporter contribution cap, i.e. user-level DP) is an explicit open
    question for the SME sign-off in the design doc — it is exactly the kind
    of thing this hard gate exists to catch before anything ships.

Composition:
    Every published cell spends the same ``epsilon`` (this prototype does
    not split a global privacy budget across cells — see the design doc's
    "future refinement" section). Publishing C cells in one release composes,
    worst case, to ``C * epsilon`` total privacy loss by basic (sequential)
    composition; that upper bound is reported as
    ``composed_epsilon_upper_bound`` so nobody has to reconstruct it by hand.
    Tighter (advanced) composition bounds are a documented future refinement,
    not implemented here.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from ..config import Config
from ..errors import NearmissError
from ..models import CleanRecord
from .temporal import _parse_hour_weekday, _part_of_day

_MECHANISM = "laplace"
_SENSITIVITY = 1.0  # one report changes exactly one (segment, part_of_day) cell by 1


class DPSignoffMissingError(NearmissError):
    """Raised when ``dp_segment_time.enabled=true`` but no sign-off reference is set.

    This is the EXP-05 "hard SME gate" from the ideation doc, enforced as
    code: the mechanism can be built and tested freely, but it refuses to
    produce a release usable by ``publish.py`` until a human privacy
    reviewer's sign-off reference has been recorded in config. See
    ``docs/privacy/exp-05-dp-segment-time-bands.md``.
    """


@dataclass(frozen=True)
class DPCell:
    """One noised (segment, part_of_day) cell.

    ``true_count`` is PRIVATE — the exact reason this mechanism exists is to
    avoid ever publishing it directly. It is carried on this internal
    dataclass only so callers can compute utility diagnostics; ``to_metadata``
    below never serializes it.
    """

    segment_id: str
    part_of_day: str
    true_count: int
    noisy_count: float
    published_count: int


@dataclass(frozen=True)
class DPSegmentTimeRelease:
    """The (gated) DP segment x time-band release, plus its privacy accounting."""

    enabled: bool
    epsilon: float | None
    sensitivity: float
    mechanism: str
    sme_signoff_ref: str | None
    cells: tuple[DPCell, ...] = ()
    noise_scale: float | None = None  # Laplace b = sensitivity / epsilon
    composed_epsilon_upper_bound: float | None = None
    mean_absolute_noise: float | None = None
    utility_theater_risk: bool | None = None


def _laplace(rng: random.Random, scale: float) -> float:
    """Sample Lap(0, scale) via inverse-CDF sampling."""
    u = rng.uniform(-0.5, 0.5)
    if u == 0.0:
        return 0.0
    return -scale * math.copysign(1.0, u) * math.log1p(-2.0 * abs(u))


def true_segment_time_counts(records: list[CleanRecord]) -> dict[tuple[str, str], int]:
    """Real (un-noised) segment x part-of-day counts.

    PRIVATE: this is the mechanism's raw input, not something to publish or
    log. Mirrors the bucketing ``stats/temporal.py`` uses for its city-wide
    view, but keyed per segment instead of collapsed city-wide.
    """
    counts: dict[tuple[str, str], int] = {}
    for r in records:
        if r.segment_id is None:
            continue
        hw = _parse_hour_weekday(r.occurred_at)
        if hw is None:
            continue
        key = (r.segment_id, _part_of_day(hw[0]))
        counts[key] = counts.get(key, 0) + 1
    return counts


def dp_segment_time_release(
    records: list[CleanRecord],
    config: Config,
    rng: random.Random | None = None,
) -> DPSegmentTimeRelease:
    """Build the gated DP segment x time-band release.

    Returns a disabled/empty release unless ``config.dp_segment_time_enabled``
    is set — this is a strict no-op for every existing config, so nothing
    about current published output changes unless a config opts in. Raises
    :class:`DPSignoffMissingError` if enabled without a recorded SME sign-off
    reference; raises :class:`~nearmiss.errors.NearmissError` if epsilon is
    not a positive number.
    """
    if not config.dp_segment_time_enabled:
        return DPSegmentTimeRelease(
            enabled=False,
            epsilon=None,
            sensitivity=_SENSITIVITY,
            mechanism=_MECHANISM,
            sme_signoff_ref=None,
        )
    if not config.dp_segment_time_sme_signoff_ref:
        raise DPSignoffMissingError(
            "dp_segment_time.enabled is true but dp_segment_time.sme_signoff_ref is not set. "
            "EXP-05 requires a recorded privacy-SME sign-off reference before this mechanism "
            "may produce a release — see docs/privacy/exp-05-dp-segment-time-bands.md."
        )
    epsilon = config.dp_segment_time_epsilon
    if not (epsilon > 0):
        raise NearmissError(f"dp_segment_time.epsilon must be > 0, got {epsilon!r}")

    rng = rng if rng is not None else random.Random()
    scale = _SENSITIVITY / epsilon
    true_counts = true_segment_time_counts(records)

    cells: list[DPCell] = []
    abs_noise: list[float] = []
    for (segment_id, part), n in sorted(true_counts.items()):
        noise = _laplace(rng, scale)
        noisy = n + noise
        published = max(0, round(noisy))
        abs_noise.append(abs(noise))
        cells.append(
            DPCell(
                segment_id=segment_id,
                part_of_day=part,
                true_count=n,
                noisy_count=noisy,
                published_count=published,
            )
        )

    mean_abs_noise = (sum(abs_noise) / len(abs_noise)) if abs_noise else 0.0
    mean_count = (sum(c.true_count for c in cells) / len(cells)) if cells else 0.0
    # Rough utility-theater signal: on average, is the noise as large as (or
    # larger than) the signal it's being added to? A cheap, honest measure —
    # not a substitute for the SME's own utility analysis.
    utility_theater = bool(cells) and mean_abs_noise >= max(mean_count, 1.0)

    return DPSegmentTimeRelease(
        enabled=True,
        epsilon=epsilon,
        sensitivity=_SENSITIVITY,
        mechanism=_MECHANISM,
        sme_signoff_ref=config.dp_segment_time_sme_signoff_ref,
        cells=tuple(cells),
        noise_scale=scale,
        composed_epsilon_upper_bound=(epsilon * len(cells)) if cells else 0.0,
        mean_absolute_noise=round(mean_abs_noise, 4),
        utility_theater_risk=utility_theater,
    )


def to_metadata(release: DPSegmentTimeRelease) -> dict[str, object]:
    """Privacy-safe, JSON-serializable view for the published metadata sidecar.

    Never includes ``true_count`` — only the already-noised
    ``published_count`` per cell, alongside the epsilon/noise-scale
    disclosure the ideation doc requires ("statistical candor extends to the
    privacy math").
    """
    if not release.enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "status": "PROTOTYPE — not approved for a real (non-synthetic) publication",
        "mechanism": release.mechanism,
        "epsilon_per_cell": release.epsilon,
        "sensitivity_per_cell": release.sensitivity,
        "noise_scale_b": (
            round(release.noise_scale, 4) if release.noise_scale is not None else None
        ),
        "cells_published": len(release.cells),
        "composed_epsilon_upper_bound": release.composed_epsilon_upper_bound,
        "mean_absolute_noise": release.mean_absolute_noise,
        "utility_theater_risk": release.utility_theater_risk,
        "sme_signoff_ref": release.sme_signoff_ref,
        "privacy_level": "event-level DP (per-report), not user-level — see design doc",
        "cells": [
            {
                "segment_id": c.segment_id,
                "part_of_day": c.part_of_day,
                "published_count": c.published_count,
            }
            for c in release.cells
        ],
    }
