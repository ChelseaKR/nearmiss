#!/usr/bin/env python3
"""Build the exact checkout site and verify retrievable bytes and privacy probes."""

from __future__ import annotations

import argparse
import json
import secrets
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = str(ROOT / "src")
ROOT_STRING = str(ROOT)
if SOURCE not in sys.path:
    sys.path.insert(0, SOURCE)
if ROOT_STRING not in sys.path:
    sys.path.insert(1, ROOT_STRING)

from nearmiss.live_site_verifier import (  # noqa: E402
    LiveSiteVerificationError,
    ProductionHttpsFetcher,
    verify_live_site,
)
from tools.build_site import build_site  # noqa: E402


def _checkout_sha() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--attempts", type=int, default=6)
    parser.add_argument("--retry-seconds", type=float, default=10.0)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    parser.add_argument("--deadline-seconds", type=float, default=480.0)
    args = parser.parse_args()
    if not 1 <= args.attempts <= 30:
        parser.error("--attempts must be between 1 and 30")
    if not 0 <= args.retry_seconds <= 60:
        parser.error("--retry-seconds must be between 0 and 60")
    if not 30 <= args.deadline_seconds <= 540:
        parser.error("--deadline-seconds must be between 30 and 540")
    if _checkout_sha() != args.expected_sha:
        parser.error("--expected-sha must equal the checked-out Git commit")

    deadline = time.monotonic() + args.deadline_seconds
    with tempfile.TemporaryDirectory(prefix="nearmiss-live-expected-") as directory:
        expected_root = Path(directory) / "site"
        build_site(expected_root, args.expected_sha)
        fetcher = ProductionHttpsFetcher(
            timeout_seconds=args.timeout_seconds,
            deadline_seconds=args.deadline_seconds,
        )
        last_error: LiveSiteVerificationError | None = None
        for attempt in range(1, args.attempts + 1):
            try:
                summary = verify_live_site(
                    expected_root,
                    expected_sha=args.expected_sha,
                    cache_token=secrets.token_hex(16),
                    fetcher=fetcher,
                )
            except LiveSiteVerificationError as exc:
                last_error = exc
                if attempt == args.attempts:
                    break
                print(
                    f"live verification attempt {attempt}/{args.attempts} failed: {exc}",
                    file=sys.stderr,
                )
                if time.monotonic() + args.retry_seconds >= deadline:
                    break
                time.sleep(args.retry_seconds)
            else:
                print(json.dumps(asdict(summary), sort_keys=True, separators=(",", ":")))
                return 0
    assert last_error is not None
    print(
        f"live verification failed after {args.attempts} attempt(s): {last_error}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
