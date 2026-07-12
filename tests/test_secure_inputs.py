from __future__ import annotations

import os
import stat
import tempfile
from pathlib import Path

import pytest

import nearmiss.secure_inputs as secure_inputs
from nearmiss.secure_inputs import SecureInputError, read_owned_regular


def test_reads_exact_owned_regular_bytes(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.write_bytes(b"exact bytes")
    source.chmod(0o644)

    assert read_owned_regular(source, maximum_bytes=64) == b"exact bytes"


@pytest.mark.skipif(not Path("/private/tmp").is_dir(), reason="macOS /private/tmp is unavailable")
def test_reads_owned_file_through_macos_private_tmp() -> None:
    descriptor, raw_path = tempfile.mkstemp(dir="/private/tmp")
    source = Path(raw_path)
    try:
        os.write(descriptor, b"private tmp bytes")
        os.close(descriptor)
        descriptor = -1
        assert read_owned_regular(source, maximum_bytes=64) == b"private tmp bytes"
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        source.unlink(missing_ok=True)


@pytest.mark.parametrize("mode", [0o666, 0o646, 0o664])
def test_rejects_group_or_world_writable_input(tmp_path: Path, mode: int) -> None:
    source = tmp_path / "input"
    source.write_bytes(b"bytes")
    source.chmod(mode)

    with pytest.raises(SecureInputError, match="permissions"):
        read_owned_regular(source, maximum_bytes=64)


def test_rejects_symlinks_and_hardlinks(tmp_path: Path) -> None:
    source = tmp_path / "input"
    source.write_bytes(b"bytes")
    symlink = tmp_path / "symlink"
    symlink.symlink_to(source)
    hardlink = tmp_path / "hardlink"
    os.link(source, hardlink)

    with pytest.raises(SecureInputError, match="safely readable"):
        read_owned_regular(symlink, maximum_bytes=64)
    with pytest.raises(SecureInputError, match="link count"):
        read_owned_regular(source, maximum_bytes=64)


def test_rejects_intermediate_symlink_directory(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    source = real / "input"
    source.write_bytes(b"bytes")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)

    with pytest.raises(SecureInputError, match="safely readable"):
        read_owned_regular(alias / "input", maximum_bytes=64)


def test_rejects_nonsticky_writable_ancestor(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe"
    unsafe.mkdir(mode=0o700)
    source = unsafe / "input"
    source.write_bytes(b"bytes")
    unsafe.chmod(0o777)

    with pytest.raises(SecureInputError, match="ancestor permissions"):
        read_owned_regular(source, maximum_bytes=64)


def test_fifo_is_rejected_without_blocking(tmp_path: Path) -> None:
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)

    with pytest.raises(SecureInputError, match="regular file"):
        read_owned_regular(fifo, maximum_bytes=64)


@pytest.mark.parametrize("payload", [b"", b"too many bytes"])
def test_rejects_empty_or_oversized_input(tmp_path: Path, payload: bytes) -> None:
    source = tmp_path / "input"
    source.write_bytes(payload)

    with pytest.raises(SecureInputError, match="size"):
        read_owned_regular(source, maximum_bytes=4)


def test_rejects_in_place_mutation_during_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input"
    source.write_bytes(b"before")
    real_fstat = os.fstat
    regular_calls = 0

    def mutating_fstat(descriptor: int) -> os.stat_result:
        nonlocal regular_calls
        metadata = real_fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            return metadata
        regular_calls += 1
        if regular_calls == 2:
            source.write_bytes(b"after!")
            os.utime(source, ns=(metadata.st_atime_ns, metadata.st_mtime_ns))
            return real_fstat(descriptor)
        return metadata

    monkeypatch.setattr(os, "fstat", mutating_fstat)
    with pytest.raises(SecureInputError, match="changed"):
        read_owned_regular(source, maximum_bytes=64)


def test_post_open_oserror_is_redacted(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "input"
    source.write_bytes(b"bytes")
    real_fstat = os.fstat

    def failing_regular_fstat(descriptor: int) -> os.stat_result:
        metadata = real_fstat(descriptor)
        if stat.S_ISREG(metadata.st_mode):
            raise OSError("sensitive kernel detail")
        return metadata

    monkeypatch.setattr(os, "fstat", failing_regular_fstat)
    with pytest.raises(SecureInputError, match="safely readable") as caught:
        read_owned_regular(source, maximum_bytes=64)
    assert "sensitive" not in str(caught.value)


@pytest.mark.parametrize(
    "missing_capability",
    [
        "O_NOFOLLOW",
        "O_DIRECTORY",
        "O_CLOEXEC",
        "O_NONBLOCK",
        "open",
        "close",
        "fdopen",
        "geteuid",
        "fstat",
    ],
)
def test_unsupported_platform_capability_fails_before_traversal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    missing_capability: str,
) -> None:
    source = tmp_path / "input"
    source.write_bytes(b"bytes")
    traversed = False

    def forbidden_traversal(_path: str | Path) -> tuple[int, str]:
        nonlocal traversed
        traversed = True
        raise AssertionError("capability preflight must precede traversal")

    monkeypatch.delattr(os, missing_capability)
    monkeypatch.setattr(secure_inputs, "_open_parent", forbidden_traversal)
    with pytest.raises(SecureInputError, match="verification is unavailable"):
        read_owned_regular(source, maximum_bytes=64)
    assert traversed is False


@pytest.mark.parametrize("zero_flag", ["O_NOFOLLOW", "O_DIRECTORY", "O_CLOEXEC", "O_NONBLOCK"])
def test_zero_security_flag_fails_before_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, zero_flag: str
) -> None:
    source = tmp_path / "input"
    source.write_bytes(b"bytes")
    monkeypatch.setattr(os, zero_flag, 0)
    monkeypatch.setattr(
        secure_inputs,
        "_open_parent",
        lambda _path: pytest.fail("capability preflight must precede traversal"),
    )

    with pytest.raises(SecureInputError, match="verification is unavailable"):
        read_owned_regular(source, maximum_bytes=64)


def test_missing_openat_support_fails_before_traversal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "input"
    source.write_bytes(b"bytes")
    monkeypatch.setattr(os, "supports_dir_fd", set())

    with pytest.raises(SecureInputError, match="verification is unavailable"):
        read_owned_regular(source, maximum_bytes=64)


@pytest.mark.parametrize("maximum", [0, -1])
def test_requires_a_positive_byte_limit(tmp_path: Path, maximum: int) -> None:
    with pytest.raises(ValueError, match="positive"):
        read_owned_regular(tmp_path / "missing", maximum_bytes=maximum)
