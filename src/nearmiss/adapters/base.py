# SPDX-License-Identifier: Apache-2.0
"""SourceAdapter framework: a small protocol plus declarative TOML crosswalks so
each new real-data source (BikeMaps, SimRa, another crowdsourced near-miss
platform, an advocacy-group spreadsheet, ...) becomes a manifest and a thin
fetch/parse module instead of a bespoke one-off script.

Eligibility is narrower than "any dataset with points on a map". An intake
report is a *conflict event experienced by a person*, so it carries ``mode``
(who was involved) and ``severity`` (what happened to them). A source of
*condition* records — a 311/SeeClickFix service request, a pavement-inspection
export, an asset inventory — describes infrastructure with no person in it and
can supply neither field honestly: ``mode`` has no ``unknown`` member, and
``occurred_at`` is event time, not the moment somebody filed a complaint. Such
a source does not become an incident source by way of a crosswalk. See
``docs/REAL-DATA.md`` ("What this does not license") for the full argument.

Every adapter maps its source's own vocabulary onto the *closed* intake enums in
``schema/report.schema.json`` and returns reports in that contract, never
inventing exposure/rate data — that stays downstream in ``exposure.py`` and
``stats/`` and is never claimed at intake, per the project's "no rate without a
denominator" rule. Every adapter also returns a :class:`Provenance` block: which
real-world dataset the reports came from, that source's own reporting-bias
profile (so ``stats/bias.py``'s narrative and the data card can *name* a
source's skew rather than average it away across sources), and attribution.

Field crosswalks — the source-vocabulary-to-intake-enum mapping that used to be
a hardcoded dict per fetch tool — are data, not code: a TOML manifest under
``crosswalks/`` per source (see ``crosswalks/bikemaps.toml`` and
``crosswalks/simra.toml``). :func:`load_crosswalk` validates every mapped target
value against the intake schema's enums at load time, so a typo in a manifest
fails fast instead of surfacing as a runtime schema rejection deep in a
pipeline run. Adding a new source is meant to touch no pipeline code: write a
crosswalk TOML, a small adapter module that reads its source's file format, and
a conformance test (see ``tests/test_adapters_conformance.py``).
"""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ..validation import find_report_schema

CROSSWALK_DIR = Path(__file__).resolve().parent / "crosswalks"

#: The bias axes every source must answer, mirroring the named biases in
#: ``docs/DATA-CARD.md`` ("Known reporting biases"). Hard rule #3 is "reporting
#: bias is named, not hidden"; before this list existed the only thing enforced
#: was that ``bias_notes`` was non-empty, so ``["some reports"]`` passed. A
#: source's skew is only useful downstream if it is answered axis by axis, in
#: that source's own terms, so two sources' profiles can be compared rather than
#: blended. Keep this tuple in sync with the data card's section.
BIAS_AXES: tuple[str, ...] = (
    "route_choice",
    "reporter_pool",
    "app_access",
    "language",
    "demographic_skew",
    "survivorship",
    "salience",
    "temporal_campaign",
)

#: Shortest acceptable answer for one bias axis. Not a quality bar -- it only
#: catches the empty string and one-word dismissals like "none" or "n/a". A
#: genuinely inapplicable axis still has to say *why* it does not apply, which
#: does not fit in 40 characters.
_MIN_BIAS_ANSWER_CHARS = 40

#: Answers that assert nothing. An axis that truly does not apply must explain
#: the reason ("SimRa has no free-text field, so language bias cannot ..."),
#: because "n/a" is exactly the non-answer this check exists to reject.
_PLACEHOLDER_BIAS_ANSWERS = frozenset(
    {"", "-", "--", "n/a", "na", "none", "tbd", "todo", "unknown", "not applicable", "?"}
)


@dataclass(frozen=True)
class Provenance:
    """Per-source honesty block returned alongside every batch of reports.

    Not part of the intake report itself — ``schema/report.schema.json`` sets
    ``additionalProperties: false`` on a report, deliberately, so provenance
    never gets tangled with the payload the schema validates. This travels
    beside the reports instead, for intake tooling, the data card, and
    ``stats/bias.py``'s narrative to cite.
    """

    source_id: str
    source_name: str
    source_url: str
    license: str
    bias_label: str
    bias_profile: dict[str, str]
    counts_by_kind: dict[str, int] = field(default_factory=dict)

    @property
    def bias_notes(self) -> tuple[str, ...]:
        """The bias profile as a flat tuple, in :data:`BIAS_AXES` order.

        Kept so callers that just want to print a source's caveats do not have
        to know the axis vocabulary. The profile is the source of truth.
        """
        return tuple(self.bias_profile[axis] for axis in BIAS_AXES if axis in self.bias_profile)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_id": self.source_id,
            "source_name": self.source_name,
            "source_url": self.source_url,
            "license": self.license,
            "bias_label": self.bias_label,
            "bias_profile": dict(self.bias_profile),
            "bias_notes": list(self.bias_notes),
            "counts_by_kind": dict(self.counts_by_kind),
        }


@runtime_checkable
class SourceAdapter(Protocol):
    """What a source adapter must provide.

    ``fetch`` talks to the network or reads a local export and returns the
    source's raw payload; ``parse`` turns that payload into intake-schema
    dicts plus a :class:`Provenance` block. Keeping the two separate is what
    makes offline testing free for every adapter: a conformance test calls
    ``parse`` directly on a small fixture payload and never touches the
    network (mirroring the existing ``--from-file`` offline path).
    """

    source_id: str

    def fetch(self, **kwargs: Any) -> Any:
        """Return this source's raw payload (a network call or a file read)."""
        ...

    def parse(self, raw: Any, **kwargs: Any) -> tuple[list[dict[str, Any]], Provenance]:
        """Turn a raw payload into ``(intake reports, provenance)``."""
        ...


# --- Declarative crosswalks (TOML) ------------------------------------------

_INTAKE_SCHEMA_CACHE: dict[str, Any] | None = None


def _intake_enum(field_name: str) -> set[str]:
    """The closed enum for one intake field, read from the schema itself so the
    crosswalk validator never drifts from ``schema/report.schema.json``."""
    global _INTAKE_SCHEMA_CACHE
    if _INTAKE_SCHEMA_CACHE is None:
        _INTAKE_SCHEMA_CACHE = json.loads(find_report_schema().read_text(encoding="utf-8"))
    return set(_INTAKE_SCHEMA_CACHE["properties"][field_name]["enum"])


@dataclass(frozen=True)
class Crosswalk:
    """A loaded, schema-validated field-crosswalk manifest for one source.

    TOML shape (see ``crosswalks/*.toml`` for the real ones)::

        [source]
        id = "bikemaps"
        name = "BikeMaps.org"
        url = "https://bikemaps.org"
        license = "..."
        bias_label = "..."

        [source.bias_profile]   # every axis in BIAS_AXES, no exceptions
        route_choice = "..."
        reporter_pool = "..."
        app_access = "..."
        language = "..."
        demographic_skew = "..."
        survivorship = "..."
        salience = "..."
        temporal_campaign = "..."

        [hazard_type]
        default = "other"
        [[hazard_type.rules]]
        when = "Vehicle, passing"
        value = "close_pass"
        rationale = "..."

        [severity]
        default = "near_miss"
        [[severity.rules]]
        contains = "hospital"
        value = "serious"
        rationale = "..."

    ``hazard_type`` rules match the source value exactly (closed source enums);
    ``severity`` rules match case-insensitive substrings (source injury/outcome
    text is free-ish text in both BikeMaps and, potentially, future sources).
    Every ``rationale`` documents a judgment call inline, per the existing
    crosswalk's "honesty over precision we don't have" rule (see
    ``docs/REAL-DATA.md``) — unmapped values fall back to ``default`` rather
    than overstate a distinction the closed intake vocabulary cannot represent.

    ``[source.bias_profile]`` must answer every axis in :data:`BIAS_AXES`;
    :func:`load_crosswalk` rejects a missing, blank, or placeholder answer.
    """

    source_id: str
    source_name: str
    source_url: str
    license: str
    bias_label: str
    bias_profile: dict[str, str]
    hazard_default: str
    hazard_rules: tuple[tuple[str, str, str], ...]  # (when, value, rationale)
    severity_default: str
    severity_rules: tuple[tuple[str, str, str], ...]  # (contains, value, rationale)

    def hazard_from(self, value: str | None) -> str:
        if value:
            for when, mapped, _rationale in self.hazard_rules:
                if value == when:
                    return mapped
        return self.hazard_default

    def severity_from(self, value: str | None) -> str:
        if value:
            lowered = value.lower()
            for needle, mapped, _rationale in self.severity_rules:
                if needle.lower() in lowered:
                    return mapped
        return self.severity_default

    def provenance(self, counts_by_kind: dict[str, int] | None = None) -> Provenance:
        return Provenance(
            source_id=self.source_id,
            source_name=self.source_name,
            source_url=self.source_url,
            license=self.license,
            bias_label=self.bias_label,
            bias_profile=dict(self.bias_profile),
            counts_by_kind=dict(counts_by_kind or {}),
        )


def _load_bias_profile(name: str, source: dict[str, Any]) -> dict[str, str]:
    """Validate ``[source.bias_profile]`` against :data:`BIAS_AXES`.

    Hard rule #3 says reporting bias is named, not hidden. A source that skips
    an axis, or answers it with "n/a", has hidden it, so this fails the load
    rather than letting an under-documented source into the registry.
    """
    raw = source.get("bias_profile")
    if not isinstance(raw, dict):
        raise ValueError(
            f"crosswalk {name!r}: [source.bias_profile] is required and must answer every axis "
            f"in {list(BIAS_AXES)} (see docs/REAL-DATA.md, 'The bias profile every source must "
            f"answer')"
        )

    missing = [axis for axis in BIAS_AXES if axis not in raw]
    if missing:
        raise ValueError(
            f"crosswalk {name!r}: [source.bias_profile] missing required axis/axes {missing}. "
            f"Every axis must be answered in this source's own terms; if one genuinely does not "
            f"apply, say so and say why."
        )

    unknown = sorted(set(raw) - set(BIAS_AXES))
    if unknown:
        raise ValueError(
            f"crosswalk {name!r}: [source.bias_profile] has unrecognized axis/axes {unknown}; "
            f"the closed axis list is {list(BIAS_AXES)}"
        )

    problems: list[str] = []
    for axis in BIAS_AXES:
        answer = raw[axis]
        if not isinstance(answer, str):
            problems.append(f"{axis}: must be a string, got {type(answer).__name__}")
            continue
        stripped = answer.strip()
        if stripped.lower().rstrip(".") in _PLACEHOLDER_BIAS_ANSWERS:
            problems.append(
                f"{axis}: {stripped!r} asserts nothing; explain the axis or why it does not apply"
            )
        elif len(stripped) < _MIN_BIAS_ANSWER_CHARS:
            problems.append(
                f"{axis}: {stripped!r} is {len(stripped)} chars, under the "
                f"{_MIN_BIAS_ANSWER_CHARS}-char floor for a substantive answer"
            )
    if problems:
        raise ValueError(f"crosswalk {name!r}: [source.bias_profile] " + "; ".join(problems))

    return {axis: str(raw[axis]).strip() for axis in BIAS_AXES}


def load_crosswalk(name: str) -> Crosswalk:
    """Load and validate ``crosswalks/<name>.toml``.

    Every mapped ``hazard_type``/``severity`` target (including each
    ``default``) is checked against the intake schema's closed enum for that
    field; a manifest that targets a value the schema does not accept raises
    ``ValueError`` immediately rather than failing later as a rejected report.

    ``[source.bias_profile]`` is validated the same way: every axis in
    :data:`BIAS_AXES` must carry a substantive answer, so a new source cannot
    reach the registry with its skew undocumented.
    """
    path = CROSSWALK_DIR / f"{name}.toml"
    if not path.is_file():
        raise FileNotFoundError(f"no crosswalk manifest at {path}")
    with path.open("rb") as fh:
        data = tomllib.load(fh)

    try:
        source = data["source"]
    except KeyError as exc:
        raise ValueError(f"crosswalk {name!r}: missing required [source] table") from exc
    for required in ("id", "name", "url", "license", "bias_label"):
        if required not in source:
            raise ValueError(f"crosswalk {name!r}: [source] missing required key {required!r}")
    bias_profile = _load_bias_profile(name, source)

    hazard = data.get("hazard_type", {})
    severity = data.get("severity", {})

    hazard_default = hazard.get("default", "other")
    hazard_rules = tuple(
        (r["when"], r["value"], r.get("rationale", "")) for r in hazard.get("rules", [])
    )
    severity_default = severity.get("default", "near_miss")
    severity_rules = tuple(
        (r["contains"], r["value"], r.get("rationale", "")) for r in severity.get("rules", [])
    )

    valid_hazard = _intake_enum("hazard_type")
    bad_hazard = sorted(
        {v for _, v, _ in hazard_rules if v not in valid_hazard}
        | ({hazard_default} if hazard_default not in valid_hazard else set())
    )
    if bad_hazard:
        raise ValueError(
            f"crosswalk {name!r}: hazard_type value(s) not in intake schema enum "
            f"{sorted(valid_hazard)}: {bad_hazard}"
        )

    valid_severity = _intake_enum("severity")
    bad_severity = sorted(
        {v for _, v, _ in severity_rules if v not in valid_severity}
        | ({severity_default} if severity_default not in valid_severity else set())
    )
    if bad_severity:
        raise ValueError(
            f"crosswalk {name!r}: severity value(s) not in intake schema enum "
            f"{sorted(valid_severity)}: {bad_severity}"
        )

    return Crosswalk(
        source_id=source["id"],
        source_name=source["name"],
        source_url=source["url"],
        license=source["license"],
        bias_label=source["bias_label"],
        bias_profile=bias_profile,
        hazard_default=hazard_default,
        hazard_rules=hazard_rules,
        severity_default=severity_default,
        severity_rules=severity_rules,
    )
