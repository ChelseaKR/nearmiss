# SPDX-License-Identifier: Apache-2.0
"""Single source of truth for this package's SCHEMA-version constants (FIX-11 / REL-02).

This is deliberately separate from ``nearmiss.__version__`` (the *package's own*
version, already single-sourced from installed distribution metadata in
``nearmiss/__init__.py``). The constants here are the contract-version numbers
baked into the artifacts this package reads and writes:

* ``REPORT_SCHEMA_VERSION`` — the intake contract a single raw report is
  validated against (``schema/report.schema.json``), carried in every
  :class:`nearmiss.models.Report`.
* ``DATASET_SCHEMA_VERSION`` — the published, aggregated GeoJSON/metadata
  contract (``schema/dataset.schema.md``), carried in every artifact
  :mod:`nearmiss.publish` writes.

Each is versioned independently of the other and of the package release
(see "Versioning and deprecation policy" in ``schema/dataset.schema.md``
§7): a schema version changes only when that specific artifact's *shape*
changes. Bump a constant here — and only here — when the corresponding
schema's contract changes; every consumer imports it rather than
hand-copying the literal, so it is impossible for two call sites to drift
out of sync (the exact failure mode this module closes: before it existed,
``"1.0.0"`` was typed by hand in three separate places across
``models.py`` and ``publish.py``).
"""

from __future__ import annotations

REPORT_SCHEMA_VERSION = "1.0.0"
DATASET_SCHEMA_VERSION = "1.1.0"

# The per-city published DATA version (metadata.dataset_version), independent of
# both the package version and the schema versions above: it moves when the
# published dataset *content* changes for the same inputs (e.g. FIX-02's
# network-topology Gi* weights changed every getis_ord_z), not when the code or
# the contract shape changes.
DATASET_VERSION = "0.1.1"
