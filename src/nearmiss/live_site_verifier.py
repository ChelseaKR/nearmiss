# SPDX-License-Identifier: Apache-2.0
"""Exact, bounded verification of the deployed static public site."""

from __future__ import annotations

import hashlib
import http.client
import ipaddress
import json
import re
import socket
import ssl
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, NoReturn, Protocol, cast
from urllib.parse import urlsplit

from .fars_public_index import FARS_PUBLIC_INDEX_FILENAME, load_fars_public_release_index_bytes

PRODUCTION_SITE_URL = "https://nearmiss.chelseakr.com"
PRIVATE_PATH_PROBES = (
    ".git/HEAD",
    "config/davis.toml",
    "src/nearmiss/private_paths.py",
    "tests/fixtures/fars/accident.csv",
    "schema/private-fars-context.schema.json",
    "data/raw/private.json",
    "data/published/fars-2019-state-mode.json",
    "data/published/fars-2023-debug.json",
    "data/published/fars-2024-state-mode.run.json",
)
HOST_CONTROL_PATHS = frozenset({".nojekyll"})

_SHA1_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
_PUBLIC_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$", re.ASCII)
_MAX_MANIFEST_BYTES = 128 * 1024
_MAX_PUBLIC_FILE_BYTES = 16 * 1024 * 1024
_MAX_ERROR_RESPONSE_BYTES = 64 * 1024
_MAX_PUBLIC_FILES = 256
_MAX_PUBLIC_TOTAL_BYTES = 64 * 1024 * 1024
_CACHE_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$", re.ASCII)
_CONTENT_TYPES_BY_SUFFIX: Mapping[str, frozenset[str]] = {
    ".css": frozenset({"text/css"}),
    ".geojson": frozenset({"application/geo+json", "application/json"}),
    ".html": frozenset({"text/html"}),
    ".js": frozenset({"application/javascript", "text/javascript"}),
    ".json": frozenset({"application/json"}),
    ".png": frozenset({"image/png"}),
    ".svg": frozenset({"image/svg+xml"}),
    ".woff2": frozenset({"font/woff2"}),
}


class LiveSiteVerificationError(ValueError):
    """The live site did not exactly match its reviewed source deployment."""


@dataclass(frozen=True, slots=True)
class FetchResult:
    status: int
    body: bytes
    content_type: str | None = None


class Fetcher(Protocol):
    def fetch(self, target: str, *, maximum_bytes: int) -> FetchResult:
        """Fetch one same-origin absolute-path target without following redirects."""


@dataclass(frozen=True, slots=True)
class LiveSiteSummary:
    source_sha: str
    file_count: int
    total_bytes: int
    default_year: int
    default_source_revision: str
    private_probe_count: int


def _reject_constant(_value: str) -> NoReturn:
    raise LiveSiteVerificationError("JSON contains a non-finite number")


def _strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key, value in pairs:
        if key in output:
            raise LiveSiteVerificationError(f"JSON contains duplicate key {key!r}")
        output[key] = value
    return output


def _strict_json_object(payload: bytes, *, label: str, maximum_bytes: int) -> dict[str, Any]:
    if not isinstance(payload, bytes):
        raise TypeError(f"{label} payload must be bytes")
    if not 1 <= len(payload) <= maximum_bytes:
        raise LiveSiteVerificationError(f"{label} exceeds its byte safety limit")
    try:
        text = payload.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise LiveSiteVerificationError(f"{label} is not UTF-8") from exc
    try:
        value = json.loads(
            text,
            object_pairs_hook=_strict_object,
            parse_constant=_reject_constant,
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise LiveSiteVerificationError(f"{label} is invalid JSON") from exc
    if not isinstance(value, dict):
        raise LiveSiteVerificationError(f"{label} must be a JSON object")
    return cast(dict[str, Any], value)


def _manifest_path(value: object) -> str:
    if not isinstance(value, str):
        raise LiveSiteVerificationError("site manifest path must be a string")
    if (
        not value
        or len(value) > 256
        or not value.isascii()
        or _PUBLIC_PATH_RE.fullmatch(value) is None
        or value.startswith("/")
        or value.endswith("/")
        or "//" in value
        or "%" in value
        or "\\" in value
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise LiveSiteVerificationError("site manifest path is not canonical and relative")
    if value == "site-manifest.json":
        raise LiveSiteVerificationError("site manifest must not inventory its own envelope")
    return value


def _manifest(payload: bytes, *, expected_sha: str, label: str) -> dict[str, str]:
    value = _strict_json_object(payload, label=label, maximum_bytes=_MAX_MANIFEST_BYTES)
    if set(value) != {"schema_version", "source_sha", "files"}:
        raise LiveSiteVerificationError(f"{label} has missing or unexpected fields")
    if value["schema_version"] != 1 or value["source_sha"] != expected_sha:
        raise LiveSiteVerificationError(f"{label} does not bind the expected source commit")
    files = value["files"]
    if not isinstance(files, dict) or not 1 <= len(files) <= _MAX_PUBLIC_FILES:
        raise LiveSiteVerificationError(f"{label} has an invalid file inventory")
    validated: dict[str, str] = {}
    for raw_path, raw_digest in files.items():
        path = _manifest_path(raw_path)
        if not isinstance(raw_digest, str) or _SHA256_RE.fullmatch(raw_digest) is None:
            raise LiveSiteVerificationError(f"{label} contains an invalid SHA-256 digest")
        validated[path] = raw_digest
    return validated


def _bounded_file(path: Path, *, maximum_bytes: int, label: str) -> bytes:
    if path.is_symlink():
        raise LiveSiteVerificationError(f"{label} must not be a symlink")
    try:
        before = path.stat()
    except OSError as exc:
        raise LiveSiteVerificationError(f"{label} is unavailable") from exc
    if not path.is_file() or not 0 <= before.st_size <= maximum_bytes:
        raise LiveSiteVerificationError(f"{label} is not a bounded regular file")
    try:
        payload = path.read_bytes()
        after = path.stat()
    except OSError as exc:
        raise LiveSiteVerificationError(f"{label} could not be read") from exc
    if before.st_size != len(payload) or before.st_size != after.st_size:
        raise LiveSiteVerificationError(f"{label} changed while it was read")
    return payload


def _physical_inventory(root: Path) -> set[str]:
    physical: set[str] = set()
    for candidate in root.rglob("*"):
        if candidate.is_symlink():
            raise LiveSiteVerificationError("expected site contains a symlink")
        if candidate.is_file():
            physical.add(candidate.relative_to(root).as_posix())
    return physical


def _expected_inventory(
    expected_root: Path,
    *,
    expected_sha: str,
) -> tuple[bytes, dict[str, bytes], dict[str, str]]:
    if expected_root.is_symlink():
        raise LiveSiteVerificationError("expected site root must not be a symlink")
    try:
        root = expected_root.resolve(strict=True)
    except OSError as exc:
        raise LiveSiteVerificationError("expected site root is unavailable") from exc
    if not root.is_dir():
        raise LiveSiteVerificationError("expected site root must be a directory")

    manifest_bytes = _bounded_file(
        root / "site-manifest.json",
        maximum_bytes=_MAX_MANIFEST_BYTES,
        label="expected site manifest",
    )
    manifest = _manifest(
        manifest_bytes,
        expected_sha=expected_sha,
        label="expected site manifest",
    )
    physical = _physical_inventory(root)
    if physical != set(manifest) | {"site-manifest.json"}:
        raise LiveSiteVerificationError("expected site files do not match its manifest")

    files: dict[str, bytes] = {}
    total = 0
    for path, digest in manifest.items():
        payload = _bounded_file(
            root / path,
            maximum_bytes=_MAX_PUBLIC_FILE_BYTES,
            label=f"expected public file {path}",
        )
        total += len(payload)
        if total > _MAX_PUBLIC_TOTAL_BYTES:
            raise LiveSiteVerificationError("expected site exceeds its total byte safety limit")
        if hashlib.sha256(payload).hexdigest() != digest:
            raise LiveSiteVerificationError(
                f"expected public file {path} does not match its manifest"
            )
        files[path] = payload
    return manifest_bytes, files, manifest


def _cache_target(path: str, *, cache_token: str, query: str | None = None) -> str:
    if not path.startswith("/") or "?" in path or "#" in path:
        raise LiveSiteVerificationError("live request path is not canonical")
    if _CACHE_TOKEN_RE.fullmatch(cache_token) is None:
        raise LiveSiteVerificationError("live request cache token is invalid")
    suffix = f"{query}&" if query else ""
    return f"{path}?{suffix}verify={cache_token}"


def _required(
    fetcher: Fetcher,
    target: str,
    *,
    maximum_bytes: int,
    label: str,
) -> bytes:
    return _required_result(
        fetcher,
        target,
        maximum_bytes=maximum_bytes,
        label=label,
    ).body


def _expected_content_types(path: str) -> frozenset[str] | None:
    """Return the safe media types for a browser-significant public path."""
    if path == "/" or path.endswith("/"):
        return _CONTENT_TYPES_BY_SUFFIX[".html"]
    name = path.rsplit("/", 1)[-1].lower()
    for suffix, content_types in _CONTENT_TYPES_BY_SUFFIX.items():
        if name.endswith(suffix):
            return content_types
    return None


def _validate_content_type(
    path: str,
    content_type: str | None,
    *,
    label: str,
) -> None:
    """Reject MIME metadata that would break or unsafely reinterpret reviewed bytes."""
    expected = _expected_content_types(path)
    if expected is None:
        return
    media_type = "" if content_type is None else content_type.split(";", 1)[0].strip().lower()
    if media_type not in expected:
        allowed = ", ".join(sorted(expected))
        actual = "missing" if content_type is None else repr(content_type)
        raise LiveSiteVerificationError(
            f"{label} returned invalid Content-Type {actual}; expected {allowed}"
        )


def _required_result(
    fetcher: Fetcher,
    target: str,
    *,
    maximum_bytes: int,
    label: str,
) -> FetchResult:
    result = fetcher.fetch(target, maximum_bytes=maximum_bytes)
    if result.status != 200:
        raise LiveSiteVerificationError(f"{label} returned HTTP {result.status}")
    _validate_content_type(urlsplit(target).path, result.content_type, label=label)
    return result


def _deployment(payload: bytes, *, expected_sha: str) -> None:
    value = _strict_json_object(payload, label="live deployment record", maximum_bytes=4096)
    expected = {
        "schema_version": 1,
        "source_sha": expected_sha,
        "source_url": f"https://github.com/ChelseaKR/nearmiss/commit/{expected_sha}",
    }
    if value != expected:
        raise LiveSiteVerificationError("live deployment record does not bind the expected commit")


def _release_summary(index_payload: bytes, expected_files: Mapping[str, bytes]) -> tuple[int, str]:
    index = load_fars_public_release_index_bytes(index_payload)
    default_year = cast(int, index["default_year"])
    releases = cast(list[dict[str, Any]], index["releases"])
    default_revision = ""
    for release in releases:
        artifact_path = cast(str, release["artifact_path"])
        site_path = f"data/published/{artifact_path}"
        if site_path not in expected_files:
            raise LiveSiteVerificationError("release index names an undeployed annual artifact")
        payload = expected_files[site_path]
        if (
            len(payload) != release["artifact_bytes"]
            or hashlib.sha256(payload).hexdigest() != release["artifact_sha256"]
        ):
            raise LiveSiteVerificationError(
                "release index annual artifact pin does not match the site"
            )
        if release["dataset_year"] == default_year:
            source = cast(dict[str, Any], release["source"])
            default_revision = cast(str, source["source_revision_id"])
    if not default_revision:
        raise LiveSiteVerificationError("release index default year has no source revision")
    return default_year, default_revision


def _verify_share_shells(
    fetcher: Fetcher,
    *,
    cache_token: str,
    expected_html: bytes,
    first_year: int,
    default_year: int,
) -> None:
    for query in (f"year={first_year}&lang=es", f"year={default_year}&lang=en"):
        shell = _required(
            fetcher,
            _cache_target(
                "/web/us-coverage.html",
                cache_token=cache_token,
                query=query,
            ),
            maximum_bytes=_MAX_PUBLIC_FILE_BYTES,
            label="live localized share shell",
        )
        if shell != expected_html:
            raise LiveSiteVerificationError("live localized share shell changed the reviewed HTML")


def _verify_canonical_national_route(
    fetcher: Fetcher,
    *,
    cache_token: str,
    expected_html: bytes,
) -> None:
    canonical = _required(
        fetcher,
        _cache_target("/fars/national/", cache_token=cache_token),
        maximum_bytes=_MAX_PUBLIC_FILE_BYTES,
        label="live canonical national route",
    )
    if canonical != expected_html:
        raise LiveSiteVerificationError("live canonical national route changed the reviewed HTML")


def _verify_private_paths(
    fetcher: Fetcher,
    *,
    cache_token: str,
    not_found: FetchResult,
) -> None:
    for path in PRIVATE_PATH_PROBES:
        result = fetcher.fetch(
            _cache_target(f"/{path}", cache_token=cache_token),
            maximum_bytes=_MAX_ERROR_RESPONSE_BYTES,
        )
        if result != not_found:
            raise LiveSiteVerificationError(
                f"private or non-allowlisted path {path} did not match the reviewed 404 response"
            )


def _not_found_baseline(fetcher: Fetcher, *, cache_token: str) -> FetchResult:
    result = fetcher.fetch(
        _cache_target(
            f"/.well-known/nearmiss-guaranteed-missing-{cache_token}",
            cache_token=cache_token,
        ),
        maximum_bytes=_MAX_ERROR_RESPONSE_BYTES,
    )
    if result.status != 404:
        raise LiveSiteVerificationError(
            f"guaranteed-missing baseline returned HTTP {result.status} instead of 404"
        )
    _validate_content_type("/404.html", result.content_type, label="live 404 response")
    return result


def verify_live_site(
    expected_root: Path,
    *,
    expected_sha: str,
    cache_token: str,
    fetcher: Fetcher,
) -> LiveSiteSummary:
    """Verify retrievable site bytes and negative privacy paths against one exact build."""
    if not isinstance(expected_sha, str) or _SHA1_RE.fullmatch(expected_sha) is None:
        raise LiveSiteVerificationError(
            "expected source SHA must be 40 lowercase hexadecimal digits"
        )
    manifest_bytes, expected_files, manifest = _expected_inventory(
        expected_root,
        expected_sha=expected_sha,
    )

    live_manifest = _required(
        fetcher,
        _cache_target("/site-manifest.json", cache_token=cache_token),
        maximum_bytes=_MAX_MANIFEST_BYTES,
        label="live site manifest",
    )
    _manifest(live_manifest, expected_sha=expected_sha, label="live site manifest")
    if live_manifest != manifest_bytes:
        raise LiveSiteVerificationError(
            "live site manifest does not match the exact reviewed build"
        )

    not_found = _not_found_baseline(fetcher, cache_token=cache_token)
    if not_found.body != expected_files["404.html"]:
        raise LiveSiteVerificationError(
            "live 404 response does not match the manifest-bound reviewed document"
        )
    total = 0
    for path, expected_payload in expected_files.items():
        if path in HOST_CONTROL_PATHS:
            result = fetcher.fetch(
                _cache_target(f"/{path}", cache_token=cache_token),
                maximum_bytes=_MAX_ERROR_RESPONSE_BYTES,
            )
            if result != not_found:
                raise LiveSiteVerificationError(
                    f"host-control path {path} did not match the reviewed 404 response"
                )
            continue
        live_payload = _required(
            fetcher,
            _cache_target(f"/{path}", cache_token=cache_token),
            maximum_bytes=_MAX_PUBLIC_FILE_BYTES,
            label=f"live public file {path}",
        )
        total += len(live_payload)
        if total > _MAX_PUBLIC_TOTAL_BYTES:
            raise LiveSiteVerificationError("live site exceeds its total byte safety limit")
        if (
            live_payload != expected_payload
            or hashlib.sha256(live_payload).hexdigest() != manifest[path]
        ):
            raise LiveSiteVerificationError(
                f"live public file {path} does not match the reviewed build"
            )

    apex = _required(
        fetcher,
        _cache_target("/", cache_token=cache_token),
        maximum_bytes=_MAX_PUBLIC_FILE_BYTES,
        label="live apex",
    )
    if apex != expected_files["index.html"]:
        raise LiveSiteVerificationError("live apex does not match the reviewed index document")
    _verify_canonical_national_route(
        fetcher,
        cache_token=cache_token,
        expected_html=expected_files["fars/national/index.html"],
    )
    _deployment(expected_files["deployment.json"], expected_sha=expected_sha)
    _deployment(
        _required(
            fetcher,
            _cache_target("/deployment.json", cache_token=cache_token),
            maximum_bytes=4096,
            label="live deployment record",
        ),
        expected_sha=expected_sha,
    )

    index_path = f"data/published/{FARS_PUBLIC_INDEX_FILENAME}"
    default_year, default_revision = _release_summary(expected_files[index_path], expected_files)
    years = cast(
        list[dict[str, Any]],
        load_fars_public_release_index_bytes(expected_files[index_path])["releases"],
    )
    first_year = cast(int, years[0]["dataset_year"])
    _verify_share_shells(
        fetcher,
        cache_token=cache_token,
        expected_html=expected_files["web/us-coverage.html"],
        first_year=first_year,
        default_year=default_year,
    )
    _verify_private_paths(fetcher, cache_token=cache_token, not_found=not_found)

    return LiveSiteSummary(
        source_sha=expected_sha,
        file_count=len(expected_files),
        total_bytes=total,
        default_year=default_year,
        default_source_revision=default_revision,
        private_probe_count=len(PRIVATE_PATH_PROBES),
    )


class ProductionHttpsFetcher:
    """Bounded, no-redirect HTTPS transport fixed to the production origin."""

    def __init__(
        self,
        *,
        timeout_seconds: float = 10.0,
        deadline_seconds: float = 480.0,
    ) -> None:
        if not 1.0 <= timeout_seconds <= 30.0:
            raise ValueError("timeout must be between 1 and 30 seconds")
        if not 30.0 <= deadline_seconds <= 540.0:
            raise ValueError("deadline must be between 30 and 540 seconds")
        parts = urlsplit(PRODUCTION_SITE_URL)
        if parts.scheme != "https" or parts.hostname is None or parts.netloc != parts.hostname:
            raise RuntimeError("production site URL is not a canonical HTTPS origin")
        self._host = parts.hostname
        self._timeout = timeout_seconds
        self._deadline = time.monotonic() + deadline_seconds

    def _validate_public_dns(self) -> None:
        try:
            addresses = socket.getaddrinfo(self._host, 443, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise LiveSiteVerificationError("production site DNS lookup failed") from exc
        if not addresses:
            raise LiveSiteVerificationError("production site DNS returned no addresses")
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if not ip.is_global:
                raise LiveSiteVerificationError(
                    "production site DNS resolved to a non-public address"
                )

    def fetch(self, target: str, *, maximum_bytes: int) -> FetchResult:
        if (
            not isinstance(target, str)
            or not target.startswith("/")
            or target.startswith("//")
            or "#" in target
            or any(ord(character) < 32 for character in target)
        ):
            raise LiveSiteVerificationError("live request target is invalid")
        if not 0 <= maximum_bytes <= _MAX_PUBLIC_FILE_BYTES:
            raise LiveSiteVerificationError("live response byte limit is invalid")
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise LiveSiteVerificationError("live verification exceeded its total deadline")
        self._validate_public_dns()
        connection = http.client.HTTPSConnection(
            self._host,
            timeout=min(self._timeout, remaining),
            context=ssl.create_default_context(),
        )
        try:
            connection.request(
                "GET",
                target,
                headers={
                    "Accept-Encoding": "identity",
                    "Cache-Control": "no-cache, no-store, max-age=0",
                    "User-Agent": "nearmiss-live-integrity/1",
                },
            )
            response = connection.getresponse()
            encoding = response.getheader("Content-Encoding")
            if encoding not in {None, "identity"}:
                raise LiveSiteVerificationError("production response used an unexpected encoding")
            raw_length = response.getheader("Content-Length")
            if raw_length is not None:
                try:
                    content_length = int(raw_length)
                except ValueError as exc:
                    raise LiveSiteVerificationError(
                        "production response has an invalid length"
                    ) from exc
                if content_length < 0 or content_length > maximum_bytes:
                    raise LiveSiteVerificationError(
                        "production response exceeds its byte safety limit"
                    )
            body = response.read(maximum_bytes + 1)
            if len(body) > maximum_bytes:
                raise LiveSiteVerificationError("production response exceeds its byte safety limit")
            return FetchResult(
                status=response.status,
                body=body,
                content_type=response.getheader("Content-Type"),
            )
        except (OSError, http.client.HTTPException) as exc:
            raise LiveSiteVerificationError("production HTTPS request failed") from exc
        finally:
            connection.close()
