#!/usr/bin/env python3
"""Print only fixed booleans for the protected QA/deploy SSH binding."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


def _keys(lines: str) -> set[tuple[str, str]]:
    keys = set()
    for line in lines.splitlines():
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        for index, value in enumerate(parts[:-1]):
            if value.startswith(("ssh-", "ecdsa-sha2-", "sk-ssh-")):
                keys.add((value, parts[index + 1]))
                break
    return keys


def diagnose(qa_host: str, deploy_host: str, known_hosts: str) -> dict[str, str]:
    result = {
        "qa_host_equals_deploy_host": str(bool(qa_host and qa_host == deploy_host)).lower(),
        "qa_pin_contains_selected_host": "false",
        "qa_pin_matches_deploy_host": "unavailable",
    }
    if not qa_host or not deploy_host or not known_hosts:
        return result
    path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as file:
            file.write(known_hosts)
            path = Path(file.name)
        path.chmod(0o600)
        pinned = subprocess.run(
            ["ssh-keygen", "-F", qa_host, "-f", str(path)],
            capture_output=True, text=True, check=False, timeout=10,
        )
        pinned_keys = _keys(pinned.stdout) if pinned.returncode == 0 else set()
        result["qa_pin_contains_selected_host"] = str(bool(pinned_keys)).lower()
        if not pinned_keys:
            return result
        scanned = subprocess.run(
            ["ssh-keyscan", "-T", "5", deploy_host],
            capture_output=True, text=True, check=False, timeout=10,
        )
        scanned_keys = _keys(scanned.stdout)
        if scanned_keys:
            result["qa_pin_matches_deploy_host"] = str(bool(pinned_keys & scanned_keys)).lower()
    except (OSError, subprocess.TimeoutExpired):
        pass
    finally:
        if path is not None:
            path.unlink(missing_ok=True)
    return result


if __name__ == "__main__":
    for key, value in diagnose(
        os.environ.get("QA_SELECTED_HOST", ""),
        os.environ.get("DEPLOY_SELECTED_HOST", ""),
        os.environ.get("QA_KNOWN_HOSTS", ""),
    ).items():
        print(f"{key}={value}")
