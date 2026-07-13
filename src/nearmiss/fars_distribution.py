# SPDX-License-Identifier: Apache-2.0
"""Dependency-free validation for official NHTSA FARS distribution URLs."""

from __future__ import annotations

from urllib.parse import urlsplit

_DISTRIBUTION_PATH_PREFIX = "/nhtsa/downloads/FARS/"


def _distribution_release_year(path: str) -> int:
    if (
        not path.isascii()
        or "%" in path
        or "\\" in path
        or "//" in path
        or any(segment in {".", ".."} for segment in path.split("/"))
    ):
        raise ValueError("FARS distribution URL path must be canonical and unencoded")
    if not path.startswith(_DISTRIBUTION_PATH_PREFIX):
        raise ValueError("FARS distribution URL path must be under /nhtsa/downloads/FARS/")
    release_year = path.removeprefix(_DISTRIBUTION_PATH_PREFIX).partition("/")[0]
    if len(release_year) != 4 or not release_year.isascii() or not release_year.isdecimal():
        raise ValueError("FARS distribution URL must contain a four-digit release year")
    return int(release_year)


def validate_fars_distribution_url(value: str, *, expected_year: int | None = None) -> str:
    """Return a canonical NHTSA FARS distribution URL or fail closed."""
    if not isinstance(value, str):
        raise TypeError("FARS distribution URL must be a string")
    if not value or value.strip() != value or any(ord(character) < 33 for character in value):
        raise ValueError("FARS distribution URL must not contain whitespace or controls")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as exc:
        raise ValueError("FARS distribution URL is malformed") from exc
    if parts.scheme != "https":
        raise ValueError("FARS distribution URL must use HTTPS")
    if parts.hostname != "static.nhtsa.gov" or parts.netloc != "static.nhtsa.gov":
        raise ValueError("FARS distribution URL host must be exactly static.nhtsa.gov")
    if parts.username is not None or parts.password is not None or port is not None:
        raise ValueError("FARS distribution URL must not contain credentials or a port")
    if parts.query or parts.fragment:
        raise ValueError("FARS distribution URL must not contain a query or fragment")
    release_year = _distribution_release_year(parts.path)
    if expected_year is not None and release_year != expected_year:
        raise ValueError("FARS distribution URL release year must match expected_year")
    if not parts.path.casefold().endswith((".zip", ".csv")):
        raise ValueError("FARS distribution URL must identify a ZIP or CSV distribution")
    return value
