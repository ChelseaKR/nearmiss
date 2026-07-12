"""Corridor-level aggregation: the unit advocacy asks are actually written in.

Briefs rank *blocks* (segments); campaigns and council motions target
*corridors* — "5th St from C to E." This module merges contiguous,
already-significant, already-publishable segments that share a street name
into named corridors, and recomputes an honest rate/CI/n at that larger unit.

Two segments are considered contiguous only if they share an endpoint
coordinate (within a small metric tolerance) AND carry the same base street
name (the text before a trailing "(cross street–cross street)" span). Both
conditions must hold, so a corridor never chains across a name change or a
geometric gap (a river, a freeway, a park with no through street) — those are
exactly the "barriers" a MAUP-aware aggregation must not paper over.

A corridor is published *alongside* block-level results, never instead of
them (EXP-03, ``docs/ideation/03-expansions.md``): every member segment keeps
its own ``SegmentStats`` entry; the corridor is a second, coarser view over
the same already-publishable data. Because a corridor's count and exposure
are sums of segments that individually already cleared the k-anonymity floor
and the significance test, the corridor can never *introduce* a privacy leak
that wasn't already published at the block level — it only re-aggregates
public numbers.

We deliberately do not attempt to re-run Getis-Ord Gi* at the corridor unit:
a corridor's shape is derived FROM segment-level significance, so re-scoring
significance on that same derived unit would double-count the evidence. A
corridor's ``getis_ord_z`` is left ``None``; its members' individual z-scores
remain the significance record of record.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..geometry import haversine_m
from ..models import Segment, SegmentStats
from .rates import rate_with_ci

# Endpoints within this many metres are treated as the same street-network node.
# Generous enough to absorb small digitization jitter between two segments drawn
# to meet at an intersection, tight enough that it never bridges a real gap.
_ENDPOINT_TOLERANCE_M = 2.0

# Matches a trailing parenthetical cross-street span, e.g. "5th St (C-D)" ->
# street="5th St", span="C-D". Segment names that don't match this shape
# (no parenthetical) are never merged — there is nothing to safely chain.
_NAME_RE = re.compile(r"^(?P<street>.+?)\s*\((?P<span>[^)]*)\)\s*$")

# Any of these characters separates the two cross streets inside the span.
_SPAN_SEP_RE = re.compile(r"[‒–—―-]")


@dataclass(frozen=True)
class CorridorStats:
    """Published corridor-level statistics: a second, coarser view over segments.

    Contains ONLY aggregates of already-publishable segment aggregates — no
    new information is introduced beyond what block-level publication already
    disclosed (hard rule #4 extends here by construction; see module docstring).
    """

    corridor_id: str
    name: str
    segment_ids: tuple[str, ...]
    report_count: int
    n: int
    exposure_estimate: float | None
    exposure_source: str | None
    exposure_date: str | None
    rate: float | None
    rate_ci_low: float | None
    rate_ci_high: float | None
    confidence_label: str
    # True for every corridor: only significant, publishable segments are ever
    # merged, so a corridor is significant-by-construction (see module docstring
    # for why Gi* is not re-run at this unit).
    significant: bool = True
    publishable: bool = True


def _street_and_span(name: str) -> tuple[str, str | None]:
    m = _NAME_RE.match(name)
    if not m:
        return name.strip(), None
    return m.group("street").strip(), m.group("span").strip()


def _span_ends(span: str | None) -> tuple[str, str] | None:
    if not span:
        return None
    parts = [p.strip() for p in _SPAN_SEP_RE.split(span) if p.strip()]
    if len(parts) != 2:
        return None
    return parts[0], parts[1]


_Point = tuple[float, float]


def _endpoints(coords: tuple[_Point, ...]) -> tuple[_Point, _Point]:
    return coords[0], coords[-1]


def _same_node(a: tuple[float, float], b: tuple[float, float]) -> bool:
    return haversine_m(a[0], a[1], b[0], b[1]) <= _ENDPOINT_TOLERANCE_M


def _connected_components(seg_ids: list[str], segments: dict[str, Segment]) -> list[list[str]]:
    """Group ``seg_ids`` (already filtered to one street name) by shared endpoints."""
    adjacency: dict[str, set[str]] = {sid: set() for sid in seg_ids}
    for i, a_id in enumerate(seg_ids):
        a0, a1 = _endpoints(segments[a_id].coords)
        for b_id in seg_ids[i + 1 :]:
            b0, b1 = _endpoints(segments[b_id].coords)
            if _same_node(a0, b0) or _same_node(a0, b1) or _same_node(a1, b0) or _same_node(a1, b1):
                adjacency[a_id].add(b_id)
                adjacency[b_id].add(a_id)

    seen: set[str] = set()
    components: list[list[str]] = []
    for start in seg_ids:
        if start in seen:
            continue
        stack = [start]
        component: list[str] = []
        while stack:
            cur = stack.pop()
            if cur in seen:
                continue
            seen.add(cur)
            component.append(cur)
            stack.extend(adjacency[cur] - seen)
        components.append(component)
    return components


def _order_chain(component: list[str], segments: dict[str, Segment]) -> list[str] | None:
    """Order a component along a simple path (degree <= 2 everywhere).

    Returns ``None`` if the component branches (a node touched by 3+ same-name
    segments) — real street networks rarely name three segments the same thing
    at one intersection, but if it happens we still aggregate the numbers (see
    :func:`_corridor_name`'s fallback) rather than guess at a linear order.
    """
    if len(component) == 1:
        return component
    adjacency: dict[str, list[str]] = {sid: [] for sid in component}
    for i, a_id in enumerate(component):
        a0, a1 = _endpoints(segments[a_id].coords)
        for b_id in component[i + 1 :]:
            b0, b1 = _endpoints(segments[b_id].coords)
            if _same_node(a0, b0) or _same_node(a0, b1) or _same_node(a1, b0) or _same_node(a1, b1):
                adjacency[a_id].append(b_id)
                adjacency[b_id].append(a_id)
    if any(len(v) > 2 for v in adjacency.values()):
        return None
    ends = [sid for sid, v in adjacency.items() if len(v) <= 1]
    start = ends[0] if ends else component[0]
    ordered = [start]
    prev: str | None = None
    cur = start
    while len(ordered) < len(component):
        nxt = [n for n in adjacency[cur] if n != prev]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        ordered.append(cur)
    return ordered if len(ordered) == len(component) else None


def _shared_node(a: Segment, b: Segment) -> _Point | None:
    """The endpoint ``a`` and ``b`` have in common, if any."""
    a0, a1 = _endpoints(a.coords)
    b0, b1 = _endpoints(b.coords)
    for x in (a0, a1):
        for y in (b0, b1):
            if _same_node(x, y):
                return x
    return None


def _outer_token(seg: Segment, shared: _Point) -> tuple[_Point, str] | None:
    """The (coordinate, cross-street name) of ``seg``'s end AWAY from ``shared``.

    Assumes a segment's own name span is written in the same order as its own
    ``coords`` (true of the synthetic fixtures and typical of well-formed street
    data); returns ``None`` if the name doesn't parse into two tokens.
    """
    ends = _span_ends(_street_and_span(seg.name)[1])
    if ends is None:
        return None
    c0, c1 = _endpoints(seg.coords)
    return (c1, ends[1]) if _same_node(c0, shared) else (c0, ends[0])


def _corridor_name(
    street: str, ordered: list[str] | None, component: list[str], segments: dict[str, Segment]
) -> str:
    """Name a corridor from the two OUTER cross streets of its ordered chain.

    Presented in a stable (lon, lat) order so the name doesn't depend on which
    end ``_order_chain`` happened to start its walk from — "5th St (C-F)" and
    never a direction-flipped or mismatched pairing like "5th St (E-D)".
    """
    if ordered is None or len(ordered) < 2:
        return f"{street} (merged: {', '.join(sorted(component))})"
    first_shared = _shared_node(segments[ordered[0]], segments[ordered[1]])
    last_shared = _shared_node(segments[ordered[-2]], segments[ordered[-1]])
    if first_shared is None or last_shared is None:
        return f"{street} (merged: {', '.join(ordered)})"
    first = _outer_token(segments[ordered[0]], first_shared)
    last = _outer_token(segments[ordered[-1]], last_shared)
    if first is None or last is None:
        return f"{street} (merged: {', '.join(ordered)})"
    ends = sorted([first, last], key=lambda e: (e[0][1], e[0][0]))  # by (lon, lat)
    return f"{street} ({ends[0][1]}–{ends[1][1]})"


def _corridor_id(segment_ids: tuple[str, ...]) -> str:
    digest = hashlib.sha256(",".join(sorted(segment_ids)).encode("utf-8")).hexdigest()[:12]
    return f"corridor-{digest}"


def build_corridors(
    stats: list[SegmentStats],
    segments: list[Segment],
    rate_per: float,
    confidence_z: float,
    small_n: int,
) -> list[CorridorStats]:
    """Merge contiguous significant+publishable same-name segments into corridors.

    Only segments that are BOTH ``significant`` (Getis-Ord Gi*, FDR-corrected)
    and ``publishable`` (cleared k-anonymity) are eligible — a corridor is a
    coarser view of already-published evidence, never a way to surface a
    segment that was withheld or non-significant on its own.
    """
    by_id: dict[str, Segment] = {s.id: s for s in segments}
    stats_by_id: dict[str, SegmentStats] = {s.segment_id: s for s in stats}
    eligible = [
        s.segment_id for s in stats if s.significant and s.publishable and s.segment_id in by_id
    ]

    by_street: dict[str, list[str]] = {}
    for sid in eligible:
        street, _span = _street_and_span(by_id[sid].name)
        by_street.setdefault(street, []).append(sid)

    corridors: list[CorridorStats] = []
    for street, seg_ids in sorted(by_street.items()):
        for component in _connected_components(seg_ids, by_id):
            if len(component) < 2:
                continue  # a lone segment is not a corridor; the block view already covers it
            member_stats = [stats_by_id[sid] for sid in component]
            count = sum(st.report_count for st in member_stats)
            n = sum(st.n for st in member_stats)
            exposures: list[float] = [
                e for sid in component if (e := stats_by_id[sid].exposure_estimate) is not None
            ]
            exposure_estimate: float | None = None
            rate: float | None = None
            ci_low: float | None = None
            ci_high: float | None = None
            if len(exposures) == len(component) and exposures:
                exposure_estimate = sum(exposures)
                if exposure_estimate > 0:
                    rate, ci_low, ci_high = rate_with_ci(
                        count, exposure_estimate, rate_per, confidence_z
                    )
            sources = {stats_by_id[sid].exposure_source for sid in component}
            dates = {stats_by_id[sid].exposure_date for sid in component}
            ordered = _order_chain(component, by_id)
            member_ids = tuple(sorted(component))
            corridors.append(
                CorridorStats(
                    corridor_id=_corridor_id(member_ids),
                    name=_corridor_name(street, ordered, component, by_id),
                    segment_ids=(tuple(ordered) if ordered is not None else member_ids),
                    report_count=count,
                    n=n,
                    exposure_estimate=exposure_estimate,
                    exposure_source=sources.pop() if len(sources) == 1 else "mixed",
                    exposure_date=dates.pop() if len(dates) == 1 else "mixed",
                    rate=rate,
                    rate_ci_low=ci_low,
                    rate_ci_high=ci_high,
                    confidence_label=("certain" if n >= small_n else "uncertain"),
                )
            )
    return sorted(corridors, key=lambda c: c.corridor_id)
