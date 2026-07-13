# SPDX-License-Identifier: Apache-2.0
"""Filesystem-identity containment checks for private storage roots."""

from __future__ import annotations

import os
import stat
from pathlib import Path


class PrivateRootPreflightError(ValueError):
    """The proposed private storage root could not be resolved safely."""


class RepositoryRootPreflightError(ValueError):
    """The repository root could not be resolved to an existing directory."""


class RepositoryContainmentError(ValueError):
    """The resolved private storage root is the repository or one of its children."""


def _resolve_root(value: str | Path) -> Path:
    try:
        if isinstance(value, str) and not value:
            raise ValueError
        return Path(value).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, TypeError, ValueError):
        raise PrivateRootPreflightError("private storage root preflight failed") from None


def _resolve_repository(value: str | Path) -> tuple[Path, os.stat_result]:
    try:
        if isinstance(value, str) and not value:
            raise ValueError
        repository = Path(value).expanduser().resolve(strict=True)
        metadata = repository.stat()
        if not stat.S_ISDIR(metadata.st_mode):
            raise ValueError
    except (OSError, RuntimeError, TypeError, ValueError):
        raise RepositoryRootPreflightError("repository root preflight failed") from None
    return repository, metadata


def require_private_root_outside_repository(
    root: str | Path,
    repository_root: str | Path,
) -> Path:
    """Resolve a private root and reject repository containment by identity.

    ``Path.relative_to`` is retained as a fast lexical check, but it is not the
    security boundary: case-insensitive filesystems can expose one directory
    through differently-cased absolute paths.  Walking the resolved root's
    existing ancestors and comparing device/inode identity closes that alias.
    The walk deliberately starts from the *resolved* root, so a symlink located
    inside the repository that resolves to genuine outside storage remains a
    supported private-root configuration.
    """

    private_root = _resolve_root(root)
    repository, repository_metadata = _resolve_repository(repository_root)

    try:
        private_root.relative_to(repository)
    except ValueError:
        pass
    else:
        raise RepositoryContainmentError("private storage root must remain outside the repository")

    found_existing_ancestor = False
    for ancestor in (private_root, *private_root.parents):
        try:
            metadata = ancestor.stat()
        except (FileNotFoundError, NotADirectoryError):
            continue
        except (OSError, ValueError):
            raise PrivateRootPreflightError("private storage root preflight failed") from None
        if not stat.S_ISDIR(metadata.st_mode):
            raise PrivateRootPreflightError("private storage root preflight failed")
        found_existing_ancestor = True
        if os.path.samestat(metadata, repository_metadata):
            raise RepositoryContainmentError(
                "private storage root must remain outside the repository"
            )

    if not found_existing_ancestor:
        raise PrivateRootPreflightError("private storage root preflight failed")
    return private_root


__all__ = [
    "PrivateRootPreflightError",
    "RepositoryContainmentError",
    "RepositoryRootPreflightError",
    "require_private_root_outside_repository",
]
