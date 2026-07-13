# SPDX-License-Identifier: Apache-2.0
"""Filesystem-boundary tests for private storage path containment."""

from __future__ import annotations

from pathlib import Path

import pytest

from nearmiss.private_paths import (
    PrivateRootPreflightError,
    RepositoryContainmentError,
    RepositoryRootPreflightError,
    require_private_root_outside_repository,
)

ROOT = Path(__file__).resolve().parents[1]


def test_equal_inside_and_outside_roots_are_classified_without_creation(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    inside = repository / "private" / "not-created"

    with pytest.raises(RepositoryContainmentError):
        require_private_root_outside_repository(repository, repository)
    with pytest.raises(RepositoryContainmentError):
        require_private_root_outside_repository(inside, repository)
    assert not inside.exists()

    outside = tmp_path / "outside" / "not-created"
    assert require_private_root_outside_repository(outside, repository) == outside.resolve()
    assert not outside.exists()


def test_existing_live_repository_and_outside_paths_are_classified_by_identity() -> None:
    with pytest.raises(RepositoryContainmentError):
        require_private_root_outside_repository(ROOT / "tests", ROOT)
    assert require_private_root_outside_repository(ROOT.parent, ROOT) == ROOT.parent.resolve()


def test_case_alias_of_existing_repository_ancestor_is_rejected_when_supported() -> None:
    canonical = Path("/Users")
    alias = Path("/users")
    try:
        aliases_same_directory = canonical.samefile(alias)
    except OSError:
        aliases_same_directory = False
    if not aliases_same_directory:
        pytest.skip("filesystem does not expose /Users through the /users case alias")

    with pytest.raises(RepositoryContainmentError):
        require_private_root_outside_repository(
            alias / "nearmiss-private-root-must-not-exist",
            canonical,
        )


def test_resolved_symlink_outside_is_allowed_and_symlink_inside_is_rejected(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    outward_link = repository / "private-link"
    outward_link.symlink_to(outside, target_is_directory=True)
    proposed = outward_link / "annual"
    assert (
        require_private_root_outside_repository(proposed, repository)
        == (outside / "annual").resolve()
    )

    inward_link = tmp_path / "repository-alias"
    inward_link.symlink_to(repository, target_is_directory=True)
    with pytest.raises(RepositoryContainmentError):
        require_private_root_outside_repository(inward_link / "annual", repository)


def test_malformed_root_and_repository_fail_separately(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()

    with pytest.raises(PrivateRootPreflightError, match="private storage root"):
        require_private_root_outside_repository("bad\0root", repository)
    with pytest.raises(RepositoryRootPreflightError, match="repository root"):
        require_private_root_outside_repository(tmp_path / "outside", "bad\0repository")
    with pytest.raises(PrivateRootPreflightError, match="private storage root"):
        require_private_root_outside_repository("", repository)
    with pytest.raises(RepositoryRootPreflightError, match="repository root"):
        require_private_root_outside_repository(tmp_path / "outside", "")


def test_files_and_missing_repositories_are_not_valid_roots(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    private_file = tmp_path / "private-file"
    private_file.write_text("not a directory")

    with pytest.raises(PrivateRootPreflightError):
        require_private_root_outside_repository(private_file, repository)
    with pytest.raises(RepositoryRootPreflightError):
        require_private_root_outside_repository(tmp_path / "outside", tmp_path / "missing")
    repository_file = tmp_path / "repository-file"
    repository_file.write_text("not a directory")
    with pytest.raises(RepositoryRootPreflightError):
        require_private_root_outside_repository(tmp_path / "outside", repository_file)
