"""Prepare isolated accounts for the authorized active-user load test.

Run from backend/trading-tool-backend with PYTHONPATH=. and the target DB/JWT
environment loaded. No action writes to production without --allow-production.
Tokens are never printed and are written only to a private file outside Git.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import stat
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text

from backend.infrastructure.database import db_host, db_name, db_port, sync_engine


REPO_ROOT = Path(__file__).resolve().parents[4]
CAMPAIGN_RE = re.compile(r"[a-z0-9][a-z0-9-]{2,31}\Z")
FIXTURE_KIND = "read_only_load_v1"


def fixture_email(campaign: str, index: int) -> str:
    return f"capacity+{campaign}-{index:04d}@load.invalid"


def fixture_emails(campaign: str, count: int) -> list[str]:
    return [fixture_email(campaign, index) for index in range(1, count + 1)]


def validate_fixture(row: dict, campaign: str, index: int) -> None:
    marker = (row.get("ai_preferences") or {}).get("capacity_fixture") or {}
    if (
        row.get("email") != fixture_email(campaign, index)
        or row.get("role") != "user"
        or row.get("first_name") != "Capacity"
        or row.get("last_name") != "Fixture"
        or marker != {"campaign": campaign, "index": index, "kind": FIXTURE_KIND}
    ):
        raise RuntimeError(f"Fixture email collision or changed account at index {index}; refusing to continue")


def load_rows(connection, campaign: str, count: int, *, lock: bool = False) -> dict[str, dict]:
    suffix = " FOR UPDATE" if lock else ""
    query = text(
        "SELECT id, email, role, is_active, first_name, last_name, ai_preferences "
        "FROM users WHERE email = ANY(:emails)" + suffix
    )
    result = connection.execute(query, {"emails": fixture_emails(campaign, count)})
    return {row["email"]: dict(row) for row in result.mappings()}


def checked_rows(connection, campaign: str, count: int, *, lock: bool = False) -> dict[str, dict]:
    rows = load_rows(connection, campaign, count, lock=lock)
    for index in range(1, count + 1):
        email = fixture_email(campaign, index)
        if email in rows:
            validate_fixture(rows[email], campaign, index)
    return rows


def create_fixtures(campaign: str, count: int) -> dict:
    # This random password is discarded. The users cannot log in with a known
    # credential and are only accessible via the short-lived test tokens.
    from backend.utils.auth_utils import hash_password

    password_hash = hash_password(secrets.token_urlsafe(48))
    with sync_engine.begin() as connection:
        existing = checked_rows(connection, campaign, count, lock=True)
        if any(not row["is_active"] for row in existing.values()):
            raise RuntimeError("Campaign includes deactivated fixtures; use a new campaign")
        if not existing and connection.execute(text("SELECT count(*) FROM users")).scalar_one() == 0:
            raise RuntimeError("Refusing to create the first user in an empty database")
        inserted = 0
        for index in range(1, count + 1):
            email = fixture_email(campaign, index)
            if email in existing:
                continue
            preferences = {
                "locale": "nl",
                "selected_asset": "BTC",
                "capacity_fixture": {"campaign": campaign, "index": index, "kind": FIXTURE_KIND},
            }
            result = connection.execute(text("""
                INSERT INTO users (
                    email, password_hash, role, is_active, first_name, last_name,
                    subscription_status, created_at, ai_plan, ai_requests_limit_day,
                    ai_requests_used_day, ai_preferences
                ) VALUES (
                    :email, :password_hash, 'user', TRUE, 'Capacity', 'Fixture',
                    'active', NOW(), 'basis', 0, 0, CAST(:preferences AS jsonb)
                ) ON CONFLICT (email) DO NOTHING RETURNING id
            """), {
                "email": email,
                "password_hash": password_hash,
                "preferences": json.dumps(preferences),
            }).scalar_one_or_none()
            if result is None:
                raise RuntimeError(f"Concurrent account collision at index {index}; transaction rolled back")
            inserted += 1
    return {"campaign": campaign, "count": count, "created": inserted, "reused": count - inserted}


def deactivate_fixtures(campaign: str, count: int) -> dict:
    with sync_engine.begin() as connection:
        rows = checked_rows(connection, campaign, count, lock=True)
        if len(rows) != count:
            raise RuntimeError("Campaign is incomplete; refusing partial deactivation")
        active_ids = [row["id"] for row in rows.values() if row["is_active"]]
        if active_ids:
            connection.execute(
                text("UPDATE users SET is_active = FALSE, subscription_status = 'inactive' WHERE id = ANY(:ids)"),
                {"ids": active_ids},
            )
    return {"campaign": campaign, "count": count, "deactivated": len(active_ids),
            "note": "Previously issued stateless tokens remain valid until their short expiry"}


def private_output_path(raw_path: Path) -> Path:
    if not raw_path.is_absolute():
        raise ValueError("Token output must be an absolute path")
    path = raw_path.resolve()
    if path == REPO_ROOT or REPO_ROOT in path.parents:
        raise ValueError("Token output must be outside the repository")
    parent = path.parent
    if not parent.is_dir() or stat.S_IMODE(parent.stat().st_mode) & 0o077:
        raise ValueError("Token output directory must exist and be accessible only to its owner (mode 0700)")
    if path.exists() or raw_path.is_symlink():
        raise ValueError("Token output already exists; choose a new path")
    return path


def write_private_json(path: Path, payload: list[dict]) -> None:
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, prefix=".capacity-fixtures-",
                                         suffix=".tmp", delete=False, encoding="utf-8") as handle:
            temporary = Path(handle.name)
            os.fchmod(handle.fileno(), 0o600)
            json.dump(payload, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)  # Atomic publication; fails if the destination exists.
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def issue_tokens(campaign: str, count: int, output: Path, ttl_minutes: int) -> dict:
    from backend.utils.auth_utils import create_token

    path = private_output_path(output)
    with sync_engine.connect() as connection:
        rows = checked_rows(connection, campaign, count)
        if len(rows) != count or any(not row["is_active"] for row in rows.values()):
            raise RuntimeError("All requested fixture accounts must exist and be active")
        ordered = [rows[fixture_email(campaign, index)] for index in range(1, count + 1)]
    expiry = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    payload = [
        {"user_id": row["id"], "email": row["email"], "access_token": create_token(
            {"sub": str(row["id"]), "role": "user", "capacity_fixture": {
                "kind": FIXTURE_KIND, "campaign": campaign,
            }}, timedelta(minutes=ttl_minutes), "access"
        )}
        for row in ordered
    ]
    write_private_json(path, payload)
    return {"campaign": campaign, "count": count, "token_file": str(path),
            "expires_at": expiry.isoformat(), "file_mode": "0600"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("plan", "create", "issue", "deactivate"))
    parser.add_argument("--campaign", required=True, help="Unique slug for this load-test run")
    parser.add_argument("--count", type=int, default=1000)
    parser.add_argument("--expected-db-host", required=True)
    parser.add_argument("--expected-db-name", required=True)
    parser.add_argument("--expected-db-port", required=True)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--apply", action="store_true", help="Required for create, issue and deactivate")
    parser.add_argument("--output", type=Path, help="Private JSON token file outside Git (issue only)")
    parser.add_argument("--ttl-minutes", type=int, default=20)
    args = parser.parse_args()

    if not CAMPAIGN_RE.fullmatch(args.campaign):
        parser.error("Campaign must be a 3-32 character lowercase slug")
    if not 1 <= args.count <= 1000:
        parser.error("Count must be between 1 and 1000")
    if not 10 <= args.ttl_minutes <= 60:
        parser.error("Token lifetime must be between 10 and 60 minutes")
    if (args.expected_db_host != db_host or args.expected_db_name != db_name
            or args.expected_db_port != db_port):
        parser.error("Configured database target does not match the expected host, port and name")
    environment = os.getenv("APP_ENV", "development").lower()
    if (environment == "production" or db_host not in {"127.0.0.1", "localhost", "::1"}) and not args.allow_production:
        parser.error("Production fixture operations require --allow-production")
    if args.action != "plan" and not args.apply:
        parser.error("This action requires --apply")
    if args.action == "issue" and args.output is None:
        parser.error("Issuing tokens requires --output")
    if args.action != "issue" and args.output is not None:
        parser.error("--output is only valid for issue")

    if args.action == "plan":
        with sync_engine.connect() as connection:
            rows = checked_rows(connection, args.campaign, args.count)
        result = {"campaign": args.campaign, "count": args.count,
                  "existing": len(rows), "missing": args.count - len(rows),
                  "inactive": sum(not row["is_active"] for row in rows.values())}
    elif args.action == "create":
        result = create_fixtures(args.campaign, args.count)
    elif args.action == "issue":
        result = issue_tokens(args.campaign, args.count, args.output, args.ttl_minutes)
    else:
        result = deactivate_fixtures(args.campaign, args.count)
    print(json.dumps({"action": args.action, "database_host": db_host,
                      "database_port": db_port, "database_name": db_name, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
