"""QA-only helper for live execution freshness guardrail tests.

This script mutates exactly one bot_decision timestamp so QA can force:
- fresh decision context
- stale decision context (> 60 minutes)
- unknown timestamp context

It is intentionally not exposed through the API. Mutations require both:
  --apply
  ALLOW_QA_DB_MUTATION=1

Examples, from backend/trading-tool-backend:
  PYTHONPATH=. python backend/scripts/qa_set_bot_decision_freshness.py \
    --email henk@example.com --decision-id 38677 --mode stale

  ALLOW_QA_DB_MUTATION=1 PYTHONPATH=. python backend/scripts/qa_set_bot_decision_freshness.py \
    --email henk@example.com --decision-id 38677 --mode stale --minutes-old 90 --apply

  ALLOW_QA_DB_MUTATION=1 PYTHONPATH=. python backend/scripts/qa_set_bot_decision_freshness.py \
    --email henk@example.com --decision-id 38677 --mode fresh --apply
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, Optional

from sqlalchemy import text

from backend.infrastructure.database import async_session_factory


TIMESTAMP_COLUMNS = ("decision_ts", "updated_at", "created_at")


def _utc_naive_now() -> datetime:
    """Return UTC as naive datetime for PostgreSQL TIMESTAMP columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=_json_default))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="QA-only helper to force bot_decisions freshness states.",
    )
    parser.add_argument("--decision-id", type=int, required=True)
    owner = parser.add_mutually_exclusive_group()
    owner.add_argument("--user-id", type=int)
    owner.add_argument("--email")
    parser.add_argument(
        "--mode",
        choices=("fresh", "stale", "unknown"),
        required=True,
        help="fresh sets timestamps to now, stale sets them to now - minutes-old, unknown clears nullable timestamp columns.",
    )
    parser.add_argument(
        "--minutes-old",
        type=int,
        default=90,
        help="Age used for --mode stale. Default: 90.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually mutate the row. Without this flag the script is dry-run only.",
    )
    return parser.parse_args()


async def _fetch_decision(session, decision_id: int, user_id: Optional[int], email: Optional[str]) -> Optional[Dict[str, Any]]:
    conditions = ["d.id = :decision_id"]
    params: Dict[str, Any] = {"decision_id": decision_id}
    if user_id is not None:
        conditions.append("d.user_id = :user_id")
        params["user_id"] = user_id
    if email:
        conditions.append("u.email = :email")
        params["email"] = email

    query = text(f"""
        SELECT
            d.id,
            d.user_id,
            u.email,
            d.bot_id,
            d.strategy_id,
            d.setup_id,
            d.symbol,
            d.decision_date,
            d.decision_ts,
            d.created_at,
            d.updated_at,
            d.status,
            d.action
        FROM bot_decisions d
        JOIN users u ON u.id = d.user_id
        WHERE {" AND ".join(conditions)}
        LIMIT 1
    """)
    result = await session.execute(query, params)
    row = result.fetchone()
    return dict(row._mapping) if row else None


async def _nullable_timestamp_columns(session, columns: Iterable[str]) -> Dict[str, bool]:
    query = text("""
        SELECT column_name, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'bot_decisions'
          AND column_name = ANY(:columns)
    """)
    result = await session.execute(query, {"columns": list(columns)})
    return {
        str(row._mapping["column_name"]): str(row._mapping["is_nullable"]).upper() == "YES"
        for row in result.fetchall()
    }


def _set_clause_for_mode(mode: str, nullable: Dict[str, bool]) -> tuple[str, Dict[str, Any]]:
    now = _utc_naive_now()
    if mode == "fresh":
        return (
            "decision_ts = :target_ts, updated_at = :target_ts",
            {"target_ts": now},
        )
    if mode == "stale":
        # minutes-old is applied by the caller.
        return (
            "decision_ts = :target_ts, updated_at = :target_ts",
            {},
        )

    nullable_columns = [name for name in TIMESTAMP_COLUMNS if nullable.get(name)]
    if set(nullable_columns) != set(TIMESTAMP_COLUMNS):
        missing = sorted(set(TIMESTAMP_COLUMNS) - set(nullable_columns))
        raise RuntimeError(
            "Unknown timestamp mode requires decision_ts, updated_at and created_at "
            f"to be nullable. Non-nullable or missing columns: {', '.join(missing)}"
        )
    return (
        "decision_ts = NULL, updated_at = NULL, created_at = NULL",
        {},
    )


async def _run() -> int:
    args = _parse_args()
    if args.mode == "stale" and args.minutes_old <= 60:
        print("--minutes-old must be greater than 60 for stale mode.", file=sys.stderr)
        return 2

    async with async_session_factory() as session:
        before = await _fetch_decision(session, args.decision_id, args.user_id, args.email)
        if not before:
            print("No matching bot_decision found for the supplied decision/user filter.", file=sys.stderr)
            return 1

        nullable = await _nullable_timestamp_columns(session, TIMESTAMP_COLUMNS)
        try:
            set_clause, params = _set_clause_for_mode(args.mode, nullable)
        except RuntimeError as exc:
            _print_json({
                "ok": False,
                "mode": args.mode,
                "decision": before,
                "column_nullability": nullable,
                "error": str(exc),
            })
            return 2

        if args.mode == "stale":
            params["target_ts"] = _utc_naive_now() - timedelta(minutes=args.minutes_old)

        mutation_allowed = args.apply and os.getenv("ALLOW_QA_DB_MUTATION") == "1"
        if not mutation_allowed:
            _print_json({
                "ok": True,
                "dry_run": True,
                "would_apply": args.apply,
                "mutation_env_set": os.getenv("ALLOW_QA_DB_MUTATION") == "1",
                "mode": args.mode,
                "minutes_old": args.minutes_old if args.mode == "stale" else None,
                "decision_before": before,
                "column_nullability": nullable,
                "note": "No row was changed. Use --apply and ALLOW_QA_DB_MUTATION=1 to mutate.",
            })
            await session.rollback()
            return 0

        update_query = text(f"""
            UPDATE bot_decisions
            SET {set_clause}
            WHERE id = :decision_id
              AND user_id = :user_id
        """)
        await session.execute(update_query, {
            **params,
            "decision_id": before["id"],
            "user_id": before["user_id"],
        })
        await session.commit()

        after = await _fetch_decision(session, args.decision_id, args.user_id, args.email)
        _print_json({
            "ok": True,
            "dry_run": False,
            "mode": args.mode,
            "minutes_old": args.minutes_old if args.mode == "stale" else None,
            "decision_before": before,
            "decision_after": after,
        })
        return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_run()))
