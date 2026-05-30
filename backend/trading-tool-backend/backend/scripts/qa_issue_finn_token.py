#!/usr/bin/env python3
"""Issue a QA-only FINN bearer token for replay and manual validation.

This script does not mutate production data. It simply verifies that a target
user exists and mints a normal access token using the configured JWT secret.

Typical use, from backend/trading-tool-backend:

  PYTHONPATH=. python3 backend/scripts/qa_issue_finn_token.py --email henk@example.com

It prints a JSON payload containing:
  - user metadata
  - access token
  - expires_at
  - a ready-to-copy Authorization header
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import User
from backend.utils.auth_utils import ACCESS_TOKEN_EXPIRE_MINUTES, create_access_token


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Issue a QA bearer token for a real FINN user.")
    owner = parser.add_mutually_exclusive_group(required=True)
    owner.add_argument("--user-id", type=int, help="Target user id")
    owner.add_argument("--email", help="Target user email")
    parser.add_argument(
        "--minutes",
        type=int,
        default=ACCESS_TOKEN_EXPIRE_MINUTES,
        help="Token lifetime in minutes. Defaults to backend access-token TTL.",
    )
    return parser.parse_args()


async def _find_user(*, user_id: Optional[int], email: Optional[str]) -> Optional[User]:
    async with async_session_factory() as session:
        query = select(User)
        if user_id is not None:
            query = query.where(User.id == user_id)
        else:
            query = query.where(User.email == email)
        result = await session.execute(query.limit(1))
        return result.scalars().first()


async def _run() -> int:
    args = _parse_args()
    user = await _find_user(user_id=args.user_id, email=args.email)
    if not user:
        print(json.dumps({
            "ok": False,
            "error": "user_not_found",
            "user_id": args.user_id,
            "email": args.email,
        }, indent=2))
        return 1

    token = create_access_token({"sub": str(user.id), "role": user.role})
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=args.minutes)
    payload: Dict[str, Any] = {
        "ok": True,
        "user": {
            "id": user.id,
            "email": user.email,
            "role": user.role,
            "first_name": user.first_name,
        },
        "token_type": "Bearer",
        "access_token": token,
        "authorization_header": f"Bearer {token}",
        "expires_at": expires_at,
        "note": "QA-only helper. Token reflects the current backend JWT policy and does not mutate user state.",
    }
    print(json.dumps(payload, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
