"""Intake: validate incoming reports and land them in the PRIVATE raw store.

Every report is validated against the published schema before it is written.
The raw store (``data/raw/``) is private and gitignored; nothing here is ever
published as-is (hard rule #4).
"""

from __future__ import annotations

import json
from pathlib import Path

from .config import Config
from .contributor import load_tombstones, tombstone_key
from .errors import ValidationError
from .loaders import load_reports
from .validation import validate_report


def run_intake(config: Config, source: Path | None = None) -> list[dict[str, object]]:
    """Validate reports from ``source`` (or the configured path) into the raw store.

    Returns the validated rows. Raises :class:`ValidationError` listing every
    rejected report rather than silently dropping or accepting bad data.

    Reports whose id has been tombstoned (deleted by a contributor or purged by
    retention) are skipped, so re-importing an upstream source never resurrects a
    deleted report (contributor data-rights).
    """
    src = source or config.reports_path
    rows = load_reports(src)
    tombstoned = load_tombstones(config)

    accepted: list[dict[str, object]] = []
    rejections: list[str] = []
    for row in rows:
        problems = validate_report(row)
        if problems:
            rid = row.get("id", "<no id>")
            rejections.append(f"{rid}: {problems[0]}")
            continue
        if tombstone_key(row.get("id")) in tombstoned:
            continue  # deleted/purged: never resurrect it
        accepted.append(row)

    if rejections:
        raise ValidationError(
            f"{len(rejections)} of {len(rows)} reports failed validation", rejections
        )

    config.raw_dir.mkdir(parents=True, exist_ok=True)
    raw_file = config.raw_dir / "reports.json"
    raw_file.write_text(
        json.dumps({"reports": accepted}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return accepted
