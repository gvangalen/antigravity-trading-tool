"""QA-only helper for live preflight token guardrail tests.

This mutates one ai_pending_actions payload for a live_preflight_bot_decision
action so QA can force:
- stale preflight token
- not-approved preflight token
- approved/fresh preflight token

It is intentionally not exposed through the API. Mutations require both:
  --apply
  ALLOW_QA_DB_MUTATION=1

Examples, from backend/trading-tool-backend:
  PYTHONPATH=. python3 backend/scripts/qa_set_live_preflight_token_state.py \
    --email henk@example.com --token finn-maint-...-u30 --mode stale

  ALLOW_QA_DB_MUTATION=1 PYTHONPATH=. python3 backend/scripts/qa_set_live_preflight_token_state.py \
    --email henk@example.com --token finn-maint-...-u30 --mode not_approved --apply
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import text

from backend.infrastructure.database import async_session_factory


def _utc_naive_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QA-only helper to force live preflight token states.",
    )
    parser.add_argument("--token", required=True, help="ai_pending_actions id / live_preflight_token.")
    owner = parser.add_mutually_exclusive_group()
    owner.add_argument("--user-id", type=int)
    owner.add_argument("--email")
    parser.add_argument(
        "--mode",
        choices=("fresh", "stale", "not_approved"),
        required=True,
    )
    parser.add_argument("--minutes-old", type=int, default=20)
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


async def _fetch_action(session, token: str, user_id: Optional[int], email: Optional[str]) -> Optional[Dict[str, Any]]:
    conditions = ["a.id = :token"]
    params: Dict[str, Any] = {"token": token}
    if user_id is not None:
        conditions.append("a.user_id = :user_id")
        params["user_id"] = user_id
    if email:
        conditions.append("u.email = :email")
        params["email"] = email
    result = await session.execute(text(f"""
        SELECT
            a.id,
            a.user_id,
            u.email,
            a.type,
            a.status,
            a.payload,
            a.created_at,
            a.expires_at
        FROM ai_pending_actions a
        JOIN users u ON u.id = a.user_id
        WHERE {" AND ".join(conditions)}
        LIMIT 1
    """), params)
    row = result.mappings().first()
    return dict(row) if row else None


def _as_payload(value: Any) -> Dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value or {})


def _mutate_payload(payload: Dict[str, Any], mode: str, minutes_old: int) -> Dict[str, Any]:
    mutated = copy.deepcopy(payload)
    action = mutated.get("action") if isinstance(mutated.get("action"), dict) else {}
    result = mutated.get("result") if isinstance(mutated.get("result"), dict) else {}
    verified = result.get("verified") if isinstance(result.get("verified"), dict) else {}
    if action.get("type") != "live_preflight_bot_decision":
        raise RuntimeError("Token payload is not a live_preflight_bot_decision action.")

    now = datetime.now(timezone.utc)
    if mode == "stale":
        if minutes_old <= 15:
            raise RuntimeError("--minutes-old must be greater than 15 for stale mode.")
        mutated["updated_at"] = (now - timedelta(minutes=minutes_old)).isoformat()
        verified["live_preflight"] = True
        verified["fresh_decision_context"] = True
    elif mode == "not_approved":
        mutated["updated_at"] = now.isoformat()
        verified["live_preflight"] = False
        verified["fresh_decision_context"] = False
        result["freshness"] = {
            "fresh": False,
            "status": "stale",
            "reason": "QA-forced not-approved preflight token.",
        }
        result["stale_data_block"] = {
            "code": "LIVE_EXECUTION_STALE_DATA",
            "message": "QA-forced not-approved preflight token.",
        }
    else:
        mutated["updated_at"] = now.isoformat()
        verified["live_preflight"] = True
        verified["fresh_decision_context"] = True
        result["stale_data_block"] = None
        result["freshness"] = result.get("freshness") or {"fresh": True, "status": "fresh"}
        if isinstance(result["freshness"], dict):
            result["freshness"]["fresh"] = True
            result["freshness"]["status"] = "fresh"

    result["verified"] = verified
    mutated["result"] = result
    return mutated


async def _run() -> int:
    args = _parse_args()
    async with async_session_factory() as session:
        row = await _fetch_action(session, args.token, args.user_id, args.email)
        if not row:
            print("No matching ai_pending_actions row found.", file=sys.stderr)
            return 1
        before_payload = _as_payload(row.get("payload"))
        try:
            after_payload = _mutate_payload(before_payload, args.mode, args.minutes_old)
        except RuntimeError as exc:
            _print_json({"ok": False, "error": str(exc), "action": row})
            return 2

        mutation_allowed = args.apply and os.getenv("ALLOW_QA_DB_MUTATION") == "1"
        if not mutation_allowed:
            _print_json({
                "ok": True,
                "dry_run": True,
                "would_apply": args.apply,
                "mutation_env_set": os.getenv("ALLOW_QA_DB_MUTATION") == "1",
                "mode": args.mode,
                "token": args.token,
                "before": before_payload,
                "after": after_payload,
                "note": "No row was changed. Use --apply and ALLOW_QA_DB_MUTATION=1 to mutate.",
            })
            await session.rollback()
            return 0

        await session.execute(text("""
            UPDATE ai_pending_actions
            SET payload = CAST(:payload AS JSONB)
            WHERE id = :token
              AND user_id = :user_id
        """), {
            "payload": json.dumps(after_payload),
            "token": row["id"],
            "user_id": row["user_id"],
        })
        await session.commit()
        after_row = await _fetch_action(session, args.token, args.user_id, args.email)
        _print_json({
            "ok": True,
            "dry_run": False,
            "mode": args.mode,
            "token": args.token,
            "before": before_payload,
            "after": _as_payload(after_row.get("payload")) if after_row else None,
        })
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
