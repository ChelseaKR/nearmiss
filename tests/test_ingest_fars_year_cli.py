"""Narrow operator contract for exact fixed-year FARS activation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

import pytest

from nearmiss import __main__ as cli
from nearmiss import fars_year_activation as activation
from nearmiss.ingestion import IngestionError

ROOT = Path(__file__).resolve().parents[1]
_RAW_LEXICAL = "downloads/../reviewed/FARS2024NationalCSV.zip"
_EVIDENCE_KEYS = {
    "source_id",
    "dataset_year",
    "contract_revision",
    "source_revision_id",
    "contract_sha256",
    "crash_mapping_version",
    "person_mapping_version",
    "release_status",
    "crash_records_read",
    "crash_records_accepted",
    "crash_records_rejected",
    "person_records_read",
    "person_records_accepted",
    "person_records_excluded",
    "cases_joined",
    "cases_excluded",
    "raw_sha256",
    "accident_sha256",
    "person_sha256",
    "normalized_sha256",
    "attempt_id",
}


@dataclass(frozen=True)
class _Evidence:
    values: dict[str, object]

    def as_dict(self) -> dict[str, object]:
        return dict(self.values)


def _evidence_values() -> dict[str, object]:
    return {
        "source_id": "fars-joined-2024",
        "dataset_year": 2024,
        "contract_revision": 1,
        "source_revision_id": "fars-2024-final-r1",
        "contract_sha256": "a" * 64,
        "crash_mapping_version": "fars-crash-v1",
        "person_mapping_version": "fars-person-v1",
        "release_status": "final",
        "crash_records_read": 36_297,
        "crash_records_accepted": 36_127,
        "crash_records_rejected": 170,
        "person_records_read": 88_326,
        "person_records_accepted": 87_982,
        "person_records_excluded": 344,
        "cases_joined": 36_127,
        "cases_excluded": 170,
        "raw_sha256": "b" * 64,
        "accident_sha256": "c" * 64,
        "person_sha256": "d" * 64,
        "normalized_sha256": "e" * 64,
        "attempt_id": "20260713T000000.000000Z-abc123",
    }


def _argv(root: str | Path, *, raw_archive: str = _RAW_LEXICAL) -> list[str]:
    return [
        "ingest-fars-year",
        raw_archive,
        "--root",
        str(root),
        "--year",
        "2024",
        "--contract-revision",
        "1",
    ]


def test_dispatch_preflights_root_and_emits_exact_sorted_aggregate_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Pin both inputs to boundary discovery at this checkout.  Discovery walks the
    # working directory and the imported module's tree, so a second checkout of the
    # same repository -- a git worktree, or an editable install exercised from
    # elsewhere -- contributes a second boundary, the guard below runs once per
    # boundary, and this test fails for a reason that has nothing to do with the
    # dispatch contract it exists to state.  The two-boundary shape is a real
    # contract and is covered on its own terms in
    # test_a_second_checkout_is_preflighted_as_its_own_boundary.
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(cli, "__file__", str(ROOT / "src" / "nearmiss" / "__main__.py"))

    requested_root = tmp_path / "operator-root"
    resolved_root = requested_root.resolve()
    events: list[str] = []
    received: dict[str, object] = {}
    values = _evidence_values()

    def guard(root: str | Path, repository_root: str | Path) -> Path:
        events.append("guard")
        assert root == str(requested_root)
        assert Path(repository_root) == ROOT
        return resolved_root

    def activate(**kwargs: object) -> _Evidence:
        events.append("activate")
        received.update(kwargs)
        return _Evidence(values)

    monkeypatch.setattr(cli, "require_private_root_outside_repository", guard)
    monkeypatch.setattr(activation, "activate_fars_year", activate)

    assert cli.main(_argv(requested_root)) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    assert (
        captured.out
        == json.dumps(
            values,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
        )
        + "\n"
    )
    assert events == ["guard", "activate"]
    assert set(values) == _EVIDENCE_KEYS == cli._FARS_YEAR_CLI_EVIDENCE_KEYS
    assert received == {
        "root": resolved_root,
        "repository_root": ROOT,
        "raw_archive_path": _RAW_LEXICAL,
        "year": 2024,
        "contract_revision": 1,
    }


def test_raw_archive_is_passed_lexically_without_expansion_or_resolution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lexical = "~/private-downloads/../reviewed.zip"
    observed: list[object] = []

    def activate(**kwargs: object) -> _Evidence:
        observed.append(kwargs["raw_archive_path"])
        return _Evidence(_evidence_values())

    monkeypatch.setattr(activation, "activate_fars_year", activate)

    assert cli.main(_argv(tmp_path / "private", raw_archive=lexical)) == 0
    assert observed == [lexical]
    assert capsys.readouterr().err == ""


def _make_checkout(root: Path) -> Path:
    """Write the identity markers that make ``root`` a nearmiss source checkout.

    Deliberately written out here rather than imported from the module under test:
    a fixture built from the code's own marker list would agree with any change to
    that list, including a change that stops recognising a real checkout.
    """

    (root / "src" / "nearmiss").mkdir(parents=True)
    (root / "web").mkdir()
    (root / "data" / "published").mkdir(parents=True)
    (root / "pyproject.toml").write_text("# checkout marker\n", encoding="utf-8")
    (root / "index.html").write_text("<!doctype html>\n", encoding="utf-8")
    module = root / "src" / "nearmiss" / "__main__.py"
    module.write_text("# checkout marker\n", encoding="utf-8")
    return module


def test_a_second_checkout_is_preflighted_as_its_own_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Every operator-visible tree is guarded, and the invocation tree is the root.

    An editable install exercised from a second working tree -- a git worktree, a
    developer running one checkout's tests against another checkout's install --
    makes the working directory and the imported module resolve to two different
    nearmiss checkouts.  Both are operator-visible, so a private root inside either
    must be refused; the ``repository_root`` handed to activation is the invocation
    tree, never the install prefix.
    """
    installed_checkout = tmp_path / "second-checkout"
    installed_module = _make_checkout(installed_checkout)
    requested_root = tmp_path / "operator-root"
    resolved_root = requested_root.resolve()
    guarded: list[Path] = []
    received: dict[str, object] = {}
    values = _evidence_values()

    def guard(root: str | Path, repository_root: str | Path) -> Path:
        assert root == str(requested_root)
        guarded.append(Path(repository_root))
        return resolved_root

    def activate(**kwargs: object) -> _Evidence:
        received.update(kwargs)
        return _Evidence(values)

    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(cli, "__file__", str(installed_module))
    monkeypatch.setattr(cli, "require_private_root_outside_repository", guard)
    monkeypatch.setattr(activation, "activate_fars_year", activate)

    assert cli.main(_argv(requested_root)) == 0

    assert guarded == [ROOT, installed_checkout.resolve()]
    assert received["repository_root"] == ROOT
    assert capsys.readouterr().err == ""


def test_boundaries_that_disagree_about_the_private_root_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Two boundaries resolving one root differently is a refusal, not a choice."""
    installed_checkout = tmp_path / "second-checkout"
    installed_module = _make_checkout(installed_checkout)
    resolutions = iter([tmp_path / "first", tmp_path / "second"])

    def guard(root: str | Path, repository_root: str | Path) -> Path:
        return next(resolutions)

    def forbidden_activation(**_kwargs: object) -> NoReturn:
        raise AssertionError("activation must not run when the boundaries disagree")

    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(cli, "__file__", str(installed_module))
    monkeypatch.setattr(cli, "require_private_root_outside_repository", guard)
    monkeypatch.setattr(activation, "activate_fars_year", forbidden_activation)

    assert cli.main(_argv(tmp_path / "operator-root")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "nearmiss: error: annual FARS activation failed\n"


def test_an_internal_fault_is_not_reported_as_an_annual_fars_data_fault(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A fault in this package must not be reported as a fact about FARS data.

    One broad ``except`` once rewrote every internal fault into "annual FARS
    activation failed", sending a reader to inspect the dataset for a bug in this
    file.  It also made the forbidden-activation sentinels below unable to fail:
    they report a regression by raising ``AssertionError``, and laundered into the
    data refusal that produced the same exit code and the same stderr as the refusal
    they exist to tell apart.  Redaction is unchanged -- the fault's own message is
    still never echoed.
    """

    def broken_activation(**_kwargs: object) -> NoReturn:
        raise AssertionError("internal invariant broken at /private/secret")

    monkeypatch.setattr(
        cli,
        "require_private_root_outside_repository",
        lambda root, repository_root: Path(root),
    )
    monkeypatch.setattr(activation, "activate_fars_year", broken_activation)

    assert cli.main(_argv(tmp_path / "operator-root")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "nearmiss: error: annual FARS activation hit an internal nearmiss fault "
        "(AssertionError); the FARS input is not implicated\n"
    )
    assert "secret" not in captured.err
    assert "annual FARS activation failed" not in captured.err


def test_an_internal_fault_with_a_hostile_type_name_prints_no_type_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The type name is printed only when it is a plain identifier.

    ``type()`` does not require ``__name__`` to be an identifier, so a class built
    at runtime can carry an arbitrary string -- including a private path.  The label
    is a diagnostic, not a channel: anything that is not a short identifier is
    dropped rather than printed.
    """
    hostile = type("/private/secret", (Exception,), {})

    def broken_activation(**_kwargs: object) -> NoReturn:
        raise hostile()

    monkeypatch.setattr(
        cli,
        "require_private_root_outside_repository",
        lambda root, repository_root: Path(root),
    )
    monkeypatch.setattr(activation, "activate_fars_year", broken_activation)

    assert cli.main(_argv(tmp_path / "operator-root")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == (
        "nearmiss: error: annual FARS activation hit an internal nearmiss fault "
        "(unnamed); the FARS input is not implicated\n"
    )
    assert "secret" not in captured.err


def test_wheel_layout_uses_invocation_checkout_not_install_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installed_module = (
        tmp_path
        / "pipx"
        / "venvs"
        / "nearmiss"
        / "lib"
        / "python3.12"
        / "site-packages"
        / "nearmiss"
        / "__main__.py"
    )
    installed_module.parent.mkdir(parents=True)
    installed_module.write_text("# installed wheel layout\n", encoding="utf-8")
    private_root = ROOT / ".fars-year-wheel-private-must-not-exist"
    assert not private_root.exists()

    def forbidden_activation(**_kwargs: object) -> NoReturn:
        raise AssertionError("activation must not run for a checkout-contained private root")

    monkeypatch.setattr(cli, "__file__", str(installed_module))
    monkeypatch.setattr(activation, "activate_fars_year", forbidden_activation)
    monkeypatch.chdir(ROOT / "web")

    assert cli.main(_argv(private_root, raw_archive="missing-and-must-not-be-read.zip")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "nearmiss: error: annual FARS activation failed\n"
    assert str(private_root) not in captured.err
    assert not private_root.exists()


def test_wheel_layout_without_operator_visible_boundary_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    installed_module = tmp_path / "site-packages" / "nearmiss" / "__main__.py"
    installed_module.parent.mkdir(parents=True)
    installed_module.write_text("# installed wheel layout\n", encoding="utf-8")
    working_directory = tmp_path / "unidentified-workspace"
    working_directory.mkdir()

    def forbidden_activation(**_kwargs: object) -> NoReturn:
        raise AssertionError("activation must not run without a public-tree boundary")

    monkeypatch.setattr(cli, "__file__", str(installed_module))
    monkeypatch.setattr(activation, "activate_fars_year", forbidden_activation)
    monkeypatch.chdir(working_directory)

    assert cli.main(_argv(tmp_path / "private")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "nearmiss: error: annual FARS activation failed\n"


@pytest.mark.parametrize(
    "argv",
    [
        [
            "ingest-fars-year",
            "--root",
            "private",
            "--year",
            "2024",
            "--contract-revision",
            "1",
        ],
        [
            "ingest-fars-year",
            "archive.zip",
            "--year",
            "2024",
            "--contract-revision",
            "1",
        ],
        [
            "ingest-fars-year",
            "archive.zip",
            "--root",
            "private",
            "--contract-revision",
            "1",
        ],
        [
            "ingest-fars-year",
            "archive.zip",
            "--root",
            "private",
            "--year",
            "2024",
        ],
    ],
)
def test_archive_root_year_and_revision_are_all_required(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(argv)
    assert raised.value.code == 2


@pytest.mark.parametrize("year", ["2019", "2025", "latest", "２０２４"])
def test_only_explicit_registered_ascii_years_are_accepted(year: str) -> None:
    argv = _argv("private")
    argv[argv.index("--year") + 1] = year

    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(argv)
    assert raised.value.code == 2


@pytest.mark.parametrize("revision", ["0", "-1", "1.0", "latest"])
def test_contract_revision_must_be_an_explicit_positive_integer(revision: str) -> None:
    argv = _argv("private")
    argv[argv.index("--contract-revision") + 1] = revision

    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(argv)
    assert raised.value.code == 2


@pytest.mark.parametrize(
    "forbidden",
    [
        ["--latest"],
        ["--release-status", "final"],
        ["--distribution-url", "https://example.test/fars.zip"],
        ["--max-raw-bytes", "1"],
        ["--max-normalized-bytes", "1"],
        ["--attempt-id", "operator-chosen"],
        ["--allow-record-regression"],
        ["--allow-mode-regression"],
        ["--allow-release-regression"],
    ],
)
def test_policy_source_size_and_attempt_overrides_are_not_cli_options(
    forbidden: list[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args([*_argv("private"), *forbidden])
    assert raised.value.code == 2


def test_parser_namespace_contains_no_hidden_policy_inputs() -> None:
    parsed = cli.build_parser().parse_args(_argv("private"))

    assert set(vars(parsed)) == {
        "command",
        "raw_archive",
        "root",
        "year",
        "contract_revision",
        "func",
    }


def test_command_help_names_only_the_closed_operator_surface(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as raised:
        cli.build_parser().parse_args(["ingest-fars-year", "--help"])
    assert raised.value.code == 0
    help_text = capsys.readouterr().out
    for token in ("RAW_ARCHIVE", "--root", "--year", "--contract-revision"):
        assert token in help_text
    for token in (
        "--latest",
        "--release-status",
        "--distribution-url",
        "--max-raw-bytes",
        "--max-normalized-bytes",
        "--attempt-id",
        "--allow-",
    ):
        assert token not in help_text


def test_repository_local_root_fails_before_activation_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_root = ROOT / ".fars-year-cli-private-must-not-exist"
    assert not private_root.exists()

    def forbidden_activation(**_kwargs: object) -> NoReturn:
        raise AssertionError("activation must not run after root rejection")

    monkeypatch.setattr(activation, "activate_fars_year", forbidden_activation)

    assert cli.main(_argv(private_root, raw_archive="missing-and-must-not-be-read.zip")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "nearmiss: error: annual FARS activation failed\n"
    assert str(private_root) not in captured.err
    assert not private_root.exists()


def test_malformed_root_has_the_same_constant_redacted_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def forbidden_activation(**_kwargs: object) -> NoReturn:
        raise AssertionError("activation must not run after malformed root rejection")

    monkeypatch.setattr(activation, "activate_fars_year", forbidden_activation)

    assert cli.main(_argv("private\0secret")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "nearmiss: error: annual FARS activation failed\n"
    assert "secret" not in captured.err


@pytest.mark.parametrize(
    "error",
    [
        ValueError("raw archive /private/secret.zip was rejected"),
        OSError("private root /private/secret failed"),
        IngestionError("ingestion refused /private/secret"),
    ],
)
def test_operator_faults_share_one_constant_redacted_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    error: Exception,
) -> None:
    """A rejected input reports one constant, whatever the underlying message said.

    An internal fault is redacted just as hard but reports a *different* constant,
    because it is not a fact about FARS data; see
    test_an_internal_fault_is_not_reported_as_an_annual_fars_data_fault.
    """

    def fail(**_kwargs: object) -> NoReturn:
        raise error

    monkeypatch.setattr(activation, "activate_fars_year", fail)

    assert cli.main(_argv(tmp_path / "private")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "nearmiss: error: annual FARS activation failed\n"
    assert "secret" not in captured.err


def test_evidence_projection_failure_is_redacted_before_any_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class BrokenEvidence:
        def as_dict(self) -> dict[str, object]:
            raise ValueError("aggregate projection leaked /private/secret")

    monkeypatch.setattr(
        activation,
        "activate_fars_year",
        lambda **_kwargs: BrokenEvidence(),
    )

    assert cli.main(_argv(tmp_path / "private")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == "nearmiss: error: annual FARS activation failed\n"


def test_evidence_projection_key_drift_fails_closed_before_stdout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    values = _evidence_values()
    values["private_path"] = "/private/secret"
    monkeypatch.setattr(
        activation,
        "activate_fars_year",
        lambda **_kwargs: _Evidence(values),
    )

    assert cli.main(_argv(tmp_path / "private")) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    # Redacted exactly as hard as before, but attributed honestly: an evidence
    # projection whose key set drifted is a contract fault in this package, and
    # reporting it as "annual FARS activation failed" pointed at the dataset.
    assert captured.err == (
        "nearmiss: error: annual FARS activation hit an internal nearmiss fault "
        "(RuntimeError); the FARS input is not implicated\n"
    )
    assert "secret" not in captured.err


def test_interrupts_are_not_converted_to_operator_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def interrupt(**_kwargs: object) -> NoReturn:
        raise KeyboardInterrupt

    monkeypatch.setattr(activation, "activate_fars_year", interrupt)

    with pytest.raises(KeyboardInterrupt):
        cli.main(_argv(tmp_path / "private"))
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""
