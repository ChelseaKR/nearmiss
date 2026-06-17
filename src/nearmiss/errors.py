"""Typed errors for nearmiss.

Errors are narrow and named so failures are debuggable and so a malformed or
malicious input is rejected at a clear boundary rather than silently corrupting
the dataset (hard rule: dependability / data integrity).
"""

from __future__ import annotations


class NearmissError(Exception):
    """Base class for all nearmiss errors."""


class ValidationError(NearmissError):
    """A report failed schema validation at intake."""

    def __init__(self, message: str, problems: list[str] | None = None) -> None:
        super().__init__(message)
        self.problems: list[str] = problems or []


class ConfigError(NearmissError):
    """A configuration file was missing, unreadable, or invalid."""


class PrivacyError(NearmissError):
    """A publish-time invariant that protects contributor privacy was violated.

    Raised rather than emitting an artifact, because publishing a precise raw
    report is never an acceptable degraded mode (hard rule #4).
    """
