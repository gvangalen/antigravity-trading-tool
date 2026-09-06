#!/usr/bin/env python3
"""Persist a small, secret-free deployment outcome record atomically."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path


CANONICAL_DEPLOY_STEPS = frozenset(
    {
        "remote_preflight",
        "git_sync",
        "runtime_dependencies",
        "migration_plan",
        "migrations",
        "schema_health",
        "frontend_export",
        "memory_headroom",
        "pm2_core",
        "pm2_finn_interactive",
        "backend_stabilization",
        "pm2_auxiliary",
        "deep_health",
        "frontend_smoke",
        "external_smoke",
        "release_marker",
        "release_complete",
    }
)
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--step-id", required=True, choices=sorted(CANONICAL_DEPLOY_STEPS))
    parser.add_argument("--outcome", required=True, choices=("running", "success", "failure"))
    parser.add_argument("--exit-code", required=True, type=int)
    return parser.parse_args()


def _load_existing(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_atomically(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        dir=path.parent,
        text=True,
    )
    try:
        os.fchmod(descriptor, 0o640)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_name, path)
        os.chmod(path, 0o640)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def main() -> int:
    args = _parse_args()
    if not SHA_PATTERN.fullmatch(args.release_sha):
        raise SystemExit("release SHA must be a full lowercase commit SHA")
    if not 0 <= args.exit_code <= 255:
        raise SystemExit("exit code must be between 0 and 255")
    if args.outcome in {"running", "success"} and args.exit_code != 0:
        raise SystemExit("running and success require exit code 0")
    if args.outcome == "failure" and args.exit_code == 0:
        raise SystemExit("failure requires a nonzero exit code")

    path = Path(args.status_file)
    record = {
        "release_sha": args.release_sha,
        "step_id": args.step_id,
        "outcome": args.outcome,
        "exit_code": args.exit_code,
        "timestamp_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    existing = _load_existing(path)
    payload: dict[str, object] = {"format_version": 1, "current": record}
    if args.outcome == "failure":
        payload["last_failure"] = record
    elif isinstance(existing.get("last_failure"), dict):
        payload["last_failure"] = existing["last_failure"]

    _write_atomically(path, payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
