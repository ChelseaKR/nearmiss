"""Closed release-index tests for the canonical 2020–2024 public release set."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any, cast

import pytest
import tools.build_fars_public_index as index_builder
from jsonschema import Draft202012Validator, FormatChecker
from tools.build_fars_public_index import build_index

import nearmiss.fars_public_index as release_index_module
from nearmiss.fars_public_index import (
    FARS_PUBLIC_INDEX_FILENAME,
    build_fars_public_release_index,
    canonical_fars_public_release_index_bytes,
    load_fars_public_release_bytes,
    load_fars_public_release_index_bytes,
    validate_fars_public_release_index,
    verify_fars_public_release_directory,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published"
INDEX_PATH = PUBLISHED / FARS_PUBLIC_INDEX_FILENAME
YEARS = tuple(range(2020, 2025))
ARTIFACTS = {year: PUBLISHED / f"fars-{year}-state-mode.json" for year in YEARS}
ARTIFACT_2024 = PUBLISHED / "fars-2024-state-mode.json"
SCHEMA_PATH = ROOT / "schema" / "public-fars-state-context-index.schema.json"
EXPECTED_INDEX_SHA256 = "64d73ea4f25de4ef1321e6f8bed56215b9585fdc7ee74bc05bf47ec74bedaa48"
EXPECTED_ARTIFACTS = {
    2020: (27589, "db4c50d998d20bc2f341b1943c883f6d6d3c805db4bb7117564619119499290c"),
    2021: (27630, "de7406ca0980e9d092eb25a230fe17fb2500f07b3b36f781dc3e4b35b7983168"),
    2022: (27622, "39f8e39fd52cc17abf07377dc460bc9545e05b82525740d8718c57e0f6fc4af8"),
    2023: (27636, "a0ddddc47f7c9ca70b823083f9f13831844b23fc45113321a3408a894eb98ade"),
    2024: (27590, "29b5dc2673987cc7bedd0a83b2147e724e1fb2a2cb1458053af3d017ac8d6578"),
}


def _canonical(value: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _artifact(year: int = 2024) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(ARTIFACTS[year].read_bytes()))


def _index() -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(INDEX_PATH.read_bytes()))


def _copy_release_set(tmp_path: Path) -> Path:
    root = tmp_path / "published"
    root.mkdir(parents=True)
    (root / FARS_PUBLIC_INDEX_FILENAME).write_bytes(INDEX_PATH.read_bytes())
    for artifact in ARTIFACTS.values():
        (root / artifact.name).write_bytes(artifact.read_bytes())
    return root


def _schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "byte safety limit"),
        (b" " * (256 * 1024 + 1), "byte safety limit"),
        (b"\xff", "not UTF-8"),
        (b"{", "invalid JSON"),
        (b"[]", "must be an object"),
        (b'{"duplicate":1,"duplicate":2}\n', "duplicate key"),
        (b'{"value":NaN}\n', "non-finite"),
        (b'{"value":Infinity}\n', "non-finite"),
        (b'{"value":-Infinity}\n', "non-finite"),
    ],
)
def test_annual_loader_rejects_unsafe_json_envelopes(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_fars_public_release_bytes(payload, expected_year=2024)


@pytest.mark.parametrize("payload", ["{}", bytearray(b"{}")])
def test_annual_loader_requires_exact_bytes(payload: object) -> None:
    with pytest.raises(TypeError, match="payload must be bytes"):
        load_fars_public_release_bytes(payload, expected_year=2024)  # type: ignore[arg-type]


def test_annual_loader_translates_parser_recursion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def recurse(*_args: object, **_kwargs: object) -> object:
        raise RecursionError("simulated parser depth")

    monkeypatch.setattr("nearmiss.fars_public_index.json.loads", recurse)
    with pytest.raises(ValueError, match="invalid JSON"):
        load_fars_public_release_bytes(b"{}", expected_year=2024)


@pytest.mark.parametrize(
    "helper",
    [
        release_index_module.fars_public_artifact_title,
        release_index_module.fars_public_artifact_caveat,
        release_index_module.fars_public_crosswalk_version,
    ],
)
def test_public_year_helpers_reject_unregistered_years(
    helper: Callable[[int], str],
) -> None:
    with pytest.raises(ValueError, match="year is not supported"):
        helper(2019)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.__setitem__("source", []), "source must be an object"),
        (lambda value: value.__setitem__("geography", []), "geography must be an object"),
        (lambda value: value.__setitem__("metric", []), "metric must be an object"),
        (lambda value: value.__setitem__("accounting", []), "accounting must be an object"),
        (
            lambda value: value["metric"].__setitem__("modes", {}),
            "modes must be an array",
        ),
        (lambda value: value.__setitem__("states", {}), "states must be an array"),
        (lambda value: value["states"].__setitem__(0, []), "state must be an object"),
        (
            lambda value: value["states"][0].__setitem__("cells", {}),
            "state cells must be an array",
        ),
        (
            lambda value: value["states"][0]["cells"].__setitem__(0, []),
            "cell must be an object",
        ),
    ],
)
def test_annual_artifact_rejects_nested_container_type_confusion(
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    artifact = _artifact()
    mutation(artifact)
    with pytest.raises(ValueError, match=message):
        load_fars_public_release_bytes(_canonical(artifact), expected_year=2024)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("case_count", True),
        ("case_count", 29_999),
        ("case_count", 45_001),
        ("state_count", 52),
        ("published_cell_count", -1),
        ("crash_contribution_total", 270_001),
    ],
)
def test_annual_accounting_rejects_boolean_and_numeric_bounds(
    field: str,
    value: object,
) -> None:
    artifact = _artifact()
    artifact["accounting"][field] = value
    with pytest.raises(ValueError, match=rf"accounting\.{field}.*between"):
        load_fars_public_release_bytes(_canonical(artifact), expected_year=2024)


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda value: value["accounting"].__setitem__("state_count", 50),
            "accounting state count",
        ),
        (
            lambda value: value["accounting"].__setitem__("state_mode_cell_count", 305),
            "accounting cell count",
        ),
        (lambda value: value.__setitem__("states", value["states"][:-1]), "50 states and DC"),
        (
            lambda value: value["states"][0].__setitem__("state_abbreviation", "XX"),
            "crosswalk or ordering",
        ),
        (
            lambda value: value["states"][0].__setitem__("cells", value["states"][0]["cells"][:-1]),
            "every canonical mode",
        ),
        (
            lambda value: value["states"][0]["cells"][0].__setitem__("involved_mode", "pedestrian"),
            "canonically ordered",
        ),
        (
            lambda value: value["states"][0]["cells"][0].__setitem__("status", "private"),
            "publication status",
        ),
        (
            lambda value: value["accounting"].__setitem__(
                "published_cell_count",
                value["accounting"]["published_cell_count"] - 1,
            ),
            "does not reconcile",
        ),
    ],
)
def test_annual_artifact_rejects_structural_and_reconciliation_drift(
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    artifact = _artifact()
    mutation(artifact)
    with pytest.raises(ValueError, match=message):
        load_fars_public_release_bytes(_canonical(artifact), expected_year=2024)


@pytest.mark.parametrize(
    ("section", "message"),
    [
        ("source", "registered annual contract"),
        ("geography", "fixed-year contract"),
    ],
)
def test_annual_artifact_rejects_cross_year_metadata_splicing(
    section: str,
    message: str,
) -> None:
    artifact = _artifact(2024)
    artifact[section] = copy.deepcopy(_artifact(2021)[section])
    with pytest.raises(ValueError, match=message):
        load_fars_public_release_bytes(_canonical(artifact), expected_year=2024)


def test_annual_artifact_rejects_identity_and_metric_drift() -> None:
    artifact = _artifact()
    artifact["title"] = "2023 US fatal-crash burden by state and involved mode"
    with pytest.raises(ValueError, match="identity"):
        load_fars_public_release_bytes(_canonical(artifact), expected_year=2024)

    artifact = _artifact()
    artifact["metric"]["effective_k"] = 9
    with pytest.raises(ValueError, match="metric contract"):
        load_fars_public_release_bytes(_canonical(artifact), expected_year=2024)


def test_checked_index_is_exact_canonical_five_year_release() -> None:
    artifacts = {year: path.read_bytes() for year, path in ARTIFACTS.items()}
    expected = canonical_fars_public_release_index_bytes(build_fars_public_release_index(artifacts))
    actual = INDEX_PATH.read_bytes()

    assert actual == expected
    assert len(actual) == 5270
    assert hashlib.sha256(actual).hexdigest() == EXPECTED_INDEX_SHA256
    index = load_fars_public_release_index_bytes(actual)
    assert index["default_year"] == 2024
    releases = index["releases"]
    assert isinstance(releases, list)
    assert [release["dataset_year"] for release in releases] == list(YEARS)
    for release in releases:
        year = release["dataset_year"]
        assert (release["artifact_bytes"], release["artifact_sha256"]) == EXPECTED_ARTIFACTS[year]

    assert list(_schema_validator().iter_errors(index)) == []


def test_multiyear_index_is_sorted_and_newest_defaults() -> None:
    artifact_2021 = ARTIFACTS[2021].read_bytes()
    artifact_2024 = ARTIFACT_2024.read_bytes()
    index = build_fars_public_release_index({2024: artifact_2024, 2021: artifact_2021})
    releases = index["releases"]

    assert index["default_year"] == 2024
    assert isinstance(releases, list)
    assert [release["dataset_year"] for release in releases] == [2021, 2024]
    assert releases[0]["artifact_sha256"] == hashlib.sha256(artifact_2021).hexdigest()
    assert releases[0]["contract"]["semantic_regime_id"] == "fars_per_typ_2020_2021_v1"
    assert releases[1]["contract"]["semantic_regime_id"] == "fars_per_typ_2022_2024_v1"
    assert list(_schema_validator().iter_errors(index)) == []
    assert (
        load_fars_public_release_index_bytes(canonical_fars_public_release_index_bytes(index))
        == index
    )


@pytest.mark.parametrize(
    "mutation, match",
    [
        (
            lambda artifact: artifact.update({"source_lineage": {"raw_path": "/private/raw.zip"}}),
            "missing or unexpected fields",
        ),
        (
            lambda artifact: artifact["source"].update({"raw_sha256": "0" * 64}),
            "registered annual contract",
        ),
        (
            lambda artifact: artifact["states"][0]["cells"][0].update({"raw_ids": ["x"]}),
            "missing or unexpected fields",
        ),
        (
            lambda artifact: artifact["states"][0]["cells"][0].update(
                {"status": "suppressed_or_zero", "crash_count": 0}
            ),
            "withheld public FARS cell",
        ),
        (
            lambda artifact: artifact["accounting"].update({"positive_suppressed_cell_count": 307}),
            "between 0 and 306",
        ),
    ],
)
def test_annual_artifact_contract_rejects_drift_and_private_fields(
    mutation: object,
    match: str,
) -> None:
    artifact = json.loads(ARTIFACT_2024.read_bytes())
    assert callable(mutation)
    mutation(artifact)
    with pytest.raises(ValueError, match=match):
        load_fars_public_release_bytes(_canonical(artifact), expected_year=2024)


def test_annual_artifact_contract_rejects_unknown_year_and_noncanonical_bytes() -> None:
    with pytest.raises(ValueError, match="not supported"):
        load_fars_public_release_bytes(ARTIFACT_2024.read_bytes(), expected_year=2019)
    pretty = json.dumps(json.loads(ARTIFACT_2024.read_bytes()), indent=2).encode()
    with pytest.raises(ValueError, match="not canonical"):
        load_fars_public_release_bytes(pretty, expected_year=2024)


def test_index_rejects_unknown_duplicate_unordered_and_stale_default() -> None:
    index = build_fars_public_release_index(
        {2021: ARTIFACTS[2021].read_bytes(), 2024: ARTIFACT_2024.read_bytes()}
    )
    releases = index["releases"]
    assert isinstance(releases, list)

    changed = copy.deepcopy(index)
    changed["default_year"] = 2023
    with pytest.raises(ValueError, match="newest published"):
        validate_fars_public_release_index(changed)

    changed = copy.deepcopy(index)
    changed["releases"] = list(reversed(releases))
    with pytest.raises(ValueError, match="unique and ordered"):
        validate_fars_public_release_index(changed)

    changed = copy.deepcopy(index)
    changed_releases = changed["releases"]
    assert isinstance(changed_releases, list)
    changed_releases.append(copy.deepcopy(changed_releases[-1]))
    with pytest.raises(ValueError, match="unique and ordered"):
        validate_fars_public_release_index(changed)

    changed = copy.deepcopy(index)
    changed_releases = changed["releases"]
    assert isinstance(changed_releases, list)
    changed_releases[0]["contract"]["semantic_regime_id"] = "unreviewed"
    with pytest.raises(ValueError, match="contract provenance"):
        validate_fars_public_release_index(changed)

    with pytest.raises(ValueError, match="not supported"):
        build_fars_public_release_index({2019: ARTIFACT_2024.read_bytes()})


def test_release_directory_verifies_index_artifacts_and_no_orphans(tmp_path: Path) -> None:
    root = _copy_release_set(tmp_path)
    index = verify_fars_public_release_directory(root)
    assert index["default_year"] == 2024

    artifact = root / ARTIFACT_2024.name
    artifact.write_bytes(artifact.read_bytes() + b" ")
    with pytest.raises(ValueError, match="does not match its index pin"):
        verify_fars_public_release_directory(root)

    root = _copy_release_set(tmp_path / "second")
    (root / "fars-2019-state-mode.json").write_bytes(ARTIFACT_2024.read_bytes())
    with pytest.raises(ValueError, match="FARS namespace"):
        verify_fars_public_release_directory(root)

    root = _copy_release_set(tmp_path / "third")
    nested = root / "old"
    nested.mkdir()
    (nested / "fars-2023-state-mode.json").write_bytes(ARTIFACTS[2023].read_bytes())
    with pytest.raises(ValueError, match="FARS namespace"):
        verify_fars_public_release_directory(root)

    root = _copy_release_set(tmp_path / "fourth")
    (root / "fars-2023-debug.json").write_text(
        '{"raw_case_ids":["private-case-id"]}\n',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="FARS namespace"):
        verify_fars_public_release_directory(root)


def test_release_directory_rejects_symlinked_index_or_artifact(tmp_path: Path) -> None:
    root = _copy_release_set(tmp_path)
    real_index = tmp_path / "real-index.json"
    real_index.write_bytes((root / FARS_PUBLIC_INDEX_FILENAME).read_bytes())
    (root / FARS_PUBLIC_INDEX_FILENAME).unlink()
    (root / FARS_PUBLIC_INDEX_FILENAME).symlink_to(real_index)
    with pytest.raises(ValueError, match="must not be a symlink"):
        verify_fars_public_release_directory(root)

    root = _copy_release_set(tmp_path / "second")
    real_artifact = tmp_path / "real-artifact.json"
    real_artifact.write_bytes((root / ARTIFACT_2024.name).read_bytes())
    (root / ARTIFACT_2024.name).unlink()
    (root / ARTIFACT_2024.name).symlink_to(real_artifact)
    with pytest.raises(ValueError, match="must not be a symlink"):
        verify_fars_public_release_directory(root)


def test_operator_index_builder_requires_explicit_canonical_names(tmp_path: Path) -> None:
    artifacts = []
    for source in ARTIFACTS.values():
        artifact = tmp_path / source.name
        artifact.write_bytes(source.read_bytes())
        artifacts.append(artifact)
    assert build_index(list(reversed(artifacts))) == INDEX_PATH.read_bytes()

    wrong = tmp_path / "latest.json"
    wrong.write_bytes(ARTIFACT_2024.read_bytes())
    with pytest.raises(ValueError, match="filename is not canonical"):
        build_index([wrong])
    with pytest.raises(ValueError, match="at least one"):
        build_index([])


@pytest.mark.parametrize(
    ("releases", "exception", "message"),
    [
        ([], TypeError, "must be a mapping"),
        ({}, ValueError, "one to five"),
        (
            {year: ARTIFACT_2024.read_bytes() for year in range(2020, 2026)},
            ValueError,
            "one to five",
        ),
        ({True: ARTIFACT_2024.read_bytes()}, TypeError, "years must be integers"),
        ({"2024": ARTIFACT_2024.read_bytes()}, TypeError, "years must be integers"),
        ({2024: "not-bytes"}, TypeError, "payloads must be bytes"),
    ],
)
def test_release_index_builder_rejects_invalid_inventory_types(
    releases: object,
    exception: type[Exception],
    message: str,
) -> None:
    with pytest.raises(exception, match=message):
        build_fars_public_release_index(releases)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda value: value.__setitem__("schema_version", "2.0.0"), "identity"),
        (
            lambda value: value["contract"].__setitem__("effective_k", 11),
            "index contract",
        ),
        (lambda value: value.__setitem__("releases", []), "one to five"),
        (
            lambda value: value["releases"][0].__setitem__(
                "artifact_path", "../fars-2020-state-mode.json"
            ),
            "path is not canonical",
        ),
        (
            lambda value: value["releases"][0]["source"].__setitem__("raw_sha256", "0" * 64),
            "source pin",
        ),
        (
            lambda value: value["releases"][0]["geography"].__setitem__(
                "state_crosswalk_sha256", "0" * 64
            ),
            "geography pin",
        ),
        (
            lambda value: value["releases"][-1].__setitem__(
                "contract", copy.deepcopy(value["releases"][0]["contract"])
            ),
            "contract provenance",
        ),
    ],
)
def test_release_index_rejects_identity_and_metadata_drift(
    mutation: Callable[[dict[str, Any]], None],
    message: str,
) -> None:
    index = _index()
    mutation(index)
    with pytest.raises(ValueError, match=message):
        validate_fars_public_release_index(index)


@pytest.mark.parametrize(
    ("digest", "message"),
    [
        ("", "nonempty string"),
        ("A" * 64, "lowercase SHA-256"),
        ("0" * 63, "lowercase SHA-256"),
    ],
)
def test_release_index_rejects_invalid_artifact_digest(
    digest: str,
    message: str,
) -> None:
    index = _index()
    index["releases"][0]["artifact_sha256"] = digest
    with pytest.raises(ValueError, match=message):
        validate_fars_public_release_index(index)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"", "byte safety limit"),
        (b" " * (64 * 1024 + 1), "byte safety limit"),
        (b"\xff", "not UTF-8"),
        (b"{", "invalid JSON"),
        (b"[]", "must be an object"),
        (b'{"duplicate":1,"duplicate":2}\n', "duplicate key"),
        (b'{"value":NaN}\n', "non-finite"),
    ],
)
def test_index_loader_rejects_unsafe_json_envelopes(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        load_fars_public_release_index_bytes(payload)


@pytest.mark.parametrize(
    "payload",
    [
        json.dumps(_index(), indent=2, sort_keys=True).encode(),
        INDEX_PATH.read_bytes().rstrip(b"\n"),
        INDEX_PATH.read_bytes() + b" ",
    ],
)
def test_index_loader_rejects_noncanonical_valid_json(payload: bytes) -> None:
    with pytest.raises(ValueError, match="not canonical"):
        load_fars_public_release_index_bytes(payload)


def test_index_loader_requires_exact_bytes() -> None:
    with pytest.raises(TypeError, match="payload must be bytes"):
        load_fars_public_release_index_bytes(bytearray(INDEX_PATH.read_bytes()))  # type: ignore[arg-type]


def test_release_directory_rejects_missing_file_and_nonregular_index(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing"
    with pytest.raises(ValueError, match="real directory"):
        verify_fars_public_release_directory(missing)

    root = tmp_path / "published"
    root.mkdir()
    with pytest.raises(ValueError, match="index is unavailable"):
        verify_fars_public_release_directory(root)

    (root / FARS_PUBLIC_INDEX_FILENAME).mkdir()
    with pytest.raises(ValueError, match="bounded regular file"):
        verify_fars_public_release_directory(root)


@pytest.mark.parametrize("payload", [b"", b" " * (64 * 1024 + 1)])
def test_release_directory_rejects_unbounded_index(
    tmp_path: Path,
    payload: bytes,
) -> None:
    root = tmp_path / "published"
    root.mkdir()
    (root / FARS_PUBLIC_INDEX_FILENAME).write_bytes(payload)
    with pytest.raises(ValueError, match="bounded regular file"):
        verify_fars_public_release_directory(root)


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="symlinks unavailable")
def test_release_directory_rejects_symlinked_root(tmp_path: Path) -> None:
    real = _copy_release_set(tmp_path)
    link = tmp_path / "published-link"
    link.symlink_to(real, target_is_directory=True)
    with pytest.raises(ValueError, match="real directory"):
        verify_fars_public_release_directory(link)


def test_bounded_file_rejects_a_size_change_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = tmp_path / "bounded.json"
    target.write_bytes(b"reviewed")
    original = Path.read_bytes

    def shortened(path: Path) -> bytes:
        payload = original(path)
        return payload[:-1] if path == target else payload

    monkeypatch.setattr(Path, "read_bytes", shortened)
    with pytest.raises(ValueError, match="changed while it was read"):
        release_index_module._bounded_regular_file(
            target,
            maximum=1024,
            label="test artifact",
        )


def test_release_directory_final_inventory_catches_canonical_named_directory(
    tmp_path: Path,
) -> None:
    root = _copy_release_set(tmp_path)
    (root / "fars-2019-state-mode.json").mkdir()
    with pytest.raises(ValueError, match="artifacts and release index do not match"):
        verify_fars_public_release_directory(root)


def test_operator_builder_rejects_duplicate_unsupported_and_unsafe_inputs(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / ARTIFACT_2024.name
    artifact.write_bytes(ARTIFACT_2024.read_bytes())
    with pytest.raises(ValueError, match="more than once"):
        build_index([artifact, artifact])

    unsupported = tmp_path / "fars-2019-state-mode.json"
    unsupported.write_bytes(ARTIFACT_2024.read_bytes())
    with pytest.raises(ValueError, match="year is not supported"):
        build_index([unsupported])

    missing = tmp_path / "fars-2023-state-mode.json"
    with pytest.raises(ValueError, match="unavailable"):
        build_index([missing])

    empty = tmp_path / "fars-2022-state-mode.json"
    empty.write_bytes(b"")
    with pytest.raises(ValueError, match="byte safety limit"):
        build_index([empty])

    oversized = tmp_path / "fars-2021-state-mode.json"
    oversized.write_bytes(b" " * (256 * 1024 + 1))
    with pytest.raises(ValueError, match="byte safety limit"):
        build_index([oversized])


@pytest.mark.skipif(not hasattr(Path, "symlink_to"), reason="symlinks unavailable")
def test_operator_builder_rejects_symlinked_artifact(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_bytes(ARTIFACT_2024.read_bytes())
    artifact = tmp_path / ARTIFACT_2024.name
    artifact.symlink_to(target)
    with pytest.raises(ValueError, match="must not be a symlink"):
        build_index([artifact])


def test_operator_builder_rejects_artifact_changed_during_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    artifact = tmp_path / ARTIFACT_2024.name
    artifact.write_bytes(ARTIFACT_2024.read_bytes())
    original = Path.read_bytes

    def shortened(path: Path) -> bytes:
        payload = original(path)
        return payload[:-1] if path == artifact else payload

    monkeypatch.setattr(Path, "read_bytes", shortened)
    with pytest.raises(ValueError, match="changed while it was read"):
        build_index([artifact])


def test_operator_cli_validation_failure_does_not_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid = tmp_path / "latest.json"
    invalid.write_text("{}", encoding="utf-8")
    output = tmp_path / FARS_PUBLIC_INDEX_FILENAME
    output.write_bytes(b"prior-reviewed-index\n")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "build_fars_public_index.py",
            "--artifact",
            str(invalid),
            "--out",
            str(output),
        ],
    )
    with pytest.raises(ValueError, match="filename is not canonical"):
        index_builder.main()
    assert output.read_bytes() == b"prior-reviewed-index\n"
