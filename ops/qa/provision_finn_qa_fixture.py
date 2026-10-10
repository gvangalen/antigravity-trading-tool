#!/usr/bin/env python3
"""Provision the one protected FINN QA owner on the production host.

This is an Operations command, never an application endpoint. It emits status
only; the owner ID and generated password never leave the host.
"""

from __future__ import annotations

import os
import re
import secrets
import stat
import tempfile
from pathlib import Path


FIXTURE_EMAIL = "finn-protected-qa@tradamind.invalid"
FIXTURE_MARKER = "finn_production_qa_v1"
ASSIGNMENT = re.compile(r"^\s*(?:export\s+)?FINN_QA_USER_ID\s*=", re.MULTILINE)


def provision(secret_path: Path) -> str:
    if secret_path.is_symlink() or not secret_path.is_file():
        raise RuntimeError("production_secret_file_invalid")
    if not stat.S_ISREG(secret_path.stat().st_mode):
        raise RuntimeError("production_secret_file_invalid")
    existing_text = secret_path.read_text()
    if ASSIGNMENT.search(existing_text):
        raise RuntimeError("qa_binding_already_present")

    build_owner = os.environ.get("FINN_BUILD_SMOKE_USER_ID", "")
    if not build_owner.isdecimal() or int(build_owner) <= 0:
        raise RuntimeError("build_fixture_binding_invalid")

    # Imports happen only after the protected workflow has sourced trading.env.
    from sqlalchemy import func, select

    from backend.infrastructure.database import SessionLocal
    from backend.infrastructure.models import ExchangeKey, User
    from backend.utils.auth_utils import hash_password

    with SessionLocal() as session:
        owner = session.execute(select(User).where(User.email == FIXTURE_EMAIL)).scalar_one_or_none()
        if owner is None:
            owner = User(
                email=FIXTURE_EMAIL,
                password_hash=hash_password(secrets.token_urlsafe(48)),
                role="user",
                is_active=True,
                first_name="FINN",
                last_name="Protected QA",
                ai_preferences={"locale": "nl", "qa_fixture": FIXTURE_MARKER},
                ai_requests_limit_day=150,
            )
            session.add(owner)
            session.commit()
            session.refresh(owner)
        elif (
            owner.role != "user"
            or not owner.is_active
            or (owner.ai_preferences or {}).get("qa_fixture") != FIXTURE_MARKER
        ):
            raise RuntimeError("designated_fixture_not_safe")

        if owner.id == int(build_owner):
            raise RuntimeError("fixture_owner_collision")
        exchange_key_count = session.scalar(
            select(func.count()).select_from(ExchangeKey).where(ExchangeKey.user_id == owner.id)
        )
        if exchange_key_count:
            raise RuntimeError("fixture_has_exchange_keys")
        owner_id = owner.id

    # The DB commit deliberately precedes the secret write. If the write fails,
    # a retry can reuse only this exact, marked account.
    next_text = existing_text.rstrip("\n") + f"\nFINN_QA_USER_ID={owner_id}\n"
    fd, temporary_name = tempfile.mkstemp(prefix=".trading.env.qa-", dir=secret_path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(next_text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, secret_path)
    finally:
        temporary.unlink(missing_ok=True)
    return "qa_fixture_provisioned"


if __name__ == "__main__":
    try:
        print(provision(Path.home() / ".secrets" / "trading.env"))
    except Exception as exc:
        # Do not print exception strings: DB drivers can include query values.
        print("qa_fixture_provision_failed:" + type(exc).__name__)
        raise SystemExit(1)
