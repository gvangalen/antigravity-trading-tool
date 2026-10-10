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


FIXTURES = (
    ("FINN_BUILD_SMOKE_USER_ID", "finn-protected-build@tradamind.example", "finn_production_build_v1", "Protected Build"),
    ("FINN_QA_USER_ID", "finn-protected-qa@tradamind.example", "finn_production_qa_v1", "Protected QA"),
)


def provision(secret_path: Path) -> str:
    if secret_path.is_symlink() or not secret_path.is_file():
        raise RuntimeError("production_secret_file_invalid")
    if not stat.S_ISREG(secret_path.stat().st_mode):
        raise RuntimeError("production_secret_file_invalid")
    existing_text = secret_path.read_text()
    existing_bindings: dict[str, int] = {}
    for variable, _, _, _ in FIXTURES:
        matches = re.findall(rf"^\s*(?:export\s+)?{variable}\s*=([^\n]*)", existing_text, re.MULTILINE)
        if len(matches) > 1:
            raise RuntimeError("fixture_binding_ambiguous")
        if matches:
            raw = matches[0].strip().strip('"\'')
            if not raw.isdecimal() or int(raw) <= 0:
                raise RuntimeError("fixture_binding_invalid")
            existing_bindings[variable] = int(raw)

    # Imports happen only after the protected workflow has sourced trading.env.
    from sqlalchemy import func, select

    from backend.infrastructure.database import SessionLocal
    from backend.infrastructure.models import ExchangeKey, User
    from backend.schemas.auth_schema import RegisterRequest
    from backend.utils.auth_utils import hash_password

    for _, email, _, display_name in FIXTURES:
        RegisterRequest(first_name="FINN", last_name=display_name, email=email, password="not-a-login")

    resolved: dict[str, int] = {}
    with SessionLocal() as session:
        for variable, email, marker, display_name in FIXTURES:
            if variable in existing_bindings:
                owner = session.get(User, existing_bindings[variable])
                if owner is None or owner.email != email:
                    raise RuntimeError("fixture_binding_owner_mismatch")
            else:
                owner = session.execute(select(User).where(User.email == email)).scalar_one_or_none()
                if owner is None:
                    owner = User(
                        email=email,
                        password_hash=hash_password(secrets.token_urlsafe(48)),
                        role="user",
                        is_active=True,
                        first_name="FINN",
                        last_name=display_name,
                        ai_preferences={"locale": "nl", "qa_fixture": marker},
                        ai_requests_limit_day=150,
                    )
                    session.add(owner)
                    session.flush()
            if (
                owner.role != "user"
                or not owner.is_active
                or (owner.ai_preferences or {}).get("qa_fixture") != marker
            ):
                raise RuntimeError("designated_fixture_not_safe")
            exchange_key_count = session.scalar(
                select(func.count()).select_from(ExchangeKey).where(ExchangeKey.user_id == owner.id)
            )
            if exchange_key_count:
                raise RuntimeError("fixture_has_exchange_keys")
            resolved[variable] = owner.id
        if len(set(resolved.values())) != len(FIXTURES):
            raise RuntimeError("fixture_owner_collision")
        session.commit()

    # The DB commit deliberately precedes the secret write. If the write fails,
    # a retry can reuse only this exact, marked account.
    additions = "".join(f"{variable}={resolved[variable]}\n" for variable, _, _, _ in FIXTURES if variable not in existing_bindings)
    next_text = existing_text.rstrip("\n") + "\n" + additions
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
    return "protected_fixtures_provisioned"


if __name__ == "__main__":
    try:
        print(provision(Path.home() / ".secrets" / "trading.env"))
    except Exception as exc:
        # Do not print exception strings: DB drivers can include query values.
        print("qa_fixture_provision_failed:" + type(exc).__name__)
        raise SystemExit(1)
