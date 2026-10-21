"""Seed or remove two marked capacity users' owner-isolation canary rows.

Use the existing capacity provisioner to create and issue tokens first. This
script never creates users, calls a model, or writes trades. Public GET checks
are performed separately by ops/load/owner_canary.py.
"""

from __future__ import annotations

import argparse
import json

from sqlalchemy import text

from backend.infrastructure.database import db_host, db_name, db_port, sync_engine
from backend.scripts.provision_capacity_fixtures import CAMPAIGN_RE, checked_rows, fixture_email


SYMBOLS = ("XRP", "ADA")


def assert_no_run_dependents(connection, run_id: str) -> None:
    """Refuse a cascading delete if any table acquired a reference to the run."""
    constraints = connection.execute(text("""
        SELECT child_ns.nspname AS schema_name, child.relname AS table_name,
               array_agg(att.attname ORDER BY keys.ordinality) AS columns
        FROM pg_constraint fk
        JOIN pg_class parent ON parent.oid = fk.confrelid
        JOIN pg_namespace parent_ns ON parent_ns.oid = parent.relnamespace
        JOIN pg_class child ON child.oid = fk.conrelid
        JOIN pg_namespace child_ns ON child_ns.oid = child.relnamespace
        JOIN LATERAL unnest(fk.conkey) WITH ORDINALITY AS keys(attnum, ordinality) ON true
        JOIN pg_attribute att ON att.attrelid = child.oid AND att.attnum = keys.attnum
        WHERE fk.contype = 'f' AND parent.relname = 'finn_v2_runs'
          AND parent_ns.nspname = current_schema()
        GROUP BY child_ns.nspname, child.relname, fk.oid
    """)).mappings().all()
    if not constraints:
        raise RuntimeError("Cannot verify FINN run dependencies; refusing cleanup")
    quote = connection.dialect.identifier_preparer.quote
    for constraint in constraints:
        columns = constraint["columns"]
        if len(columns) != 1:
            raise RuntimeError("Unexpected composite FINN run dependency; refusing cleanup")
        table = f'{quote(constraint["schema_name"])}.{quote(constraint["table_name"])}'
        column = quote(columns[0])
        count = connection.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE {column}=:run_id"),
            {"run_id": run_id},
        ).scalar_one()
        if count:
            raise RuntimeError("FINN run has dependent rows; refusing cleanup")


def canary_values(campaign: str, index: int) -> dict:
    return {
        "email": fixture_email(campaign, index),
        "symbol": SYMBOLS[index - 1],
        "conversation_id": f"capacity-owner-{campaign}-{index}",
        "run_id": f"capacity-owner-run-{campaign}-{index}",
        "message": f"Capacity owner canary {campaign} account {index}",
    }


def seed(campaign: str) -> dict:
    with sync_engine.begin() as connection:
        rows = checked_rows(connection, campaign, 2, lock=True)
        if len(rows) != 2 or any(not row["is_active"] for row in rows.values()):
            raise RuntimeError("Both marked capacity accounts must exist and be active")
        user_ids = [rows[fixture_email(campaign, index)]["id"] for index in (1, 2)]
        existing = connection.execute(text("""
            SELECT
              (SELECT COUNT(*) FROM watchlists WHERE user_id = ANY(:ids)) AS watchlists,
              (SELECT COUNT(*) FROM finn_v2_conversations WHERE user_id = ANY(:ids)) AS conversations,
              (SELECT COUNT(*) FROM finn_v2_runs WHERE user_id = ANY(:ids)) AS runs
        """), {"ids": user_ids}).mappings().one()
        if any(existing[key] for key in ("watchlists", "conversations", "runs")):
            raise RuntimeError("Owner canary accounts already contain content; refusing to seed")
        for index, user_id in enumerate(user_ids, 1):
            values = {**canary_values(campaign, index), "user_id": user_id}
            connection.execute(text("""
                INSERT INTO watchlists (user_id, symbol, created_at)
                VALUES (:user_id, :symbol, NOW())
            """), values)
            connection.execute(text("""
                INSERT INTO finn_v2_conversations
                    (id, user_id, title, status, created_at, updated_at, context_json)
                VALUES (:conversation_id, :user_id, :message, 'active', NOW(), NOW(),
                        CAST(:context_json AS jsonb))
            """), {**values, "context_json": json.dumps({"capacity_owner_canary": campaign})})
            connection.execute(text("""
                INSERT INTO finn_v2_runs
                    (id, conversation_id, user_id, request_id, trace_id,
                     idempotency_key, transport, visibility, feature_mode, status,
                     interaction_mode, message, created_at, updated_at, completed_at)
                VALUES (:run_id, :conversation_id, :user_id, :run_id, :run_id,
                        :run_id, 'chat', 'visible', 'capacity_owner_canary',
                        'completed', 'READ', :message, NOW(), NOW(), NOW())
            """), values)
    return {"campaign": campaign, "seeded_users": 2, "symbols": list(SYMBOLS)}


def cleanup(campaign: str) -> dict:
    with sync_engine.begin() as connection:
        rows = checked_rows(connection, campaign, 2, lock=True)
        if len(rows) != 2:
            raise RuntimeError("Both marked capacity accounts must exist for exact cleanup")
        removed = 0
        for index in (1, 2):
            user_id = rows[fixture_email(campaign, index)]["id"]
            values = {**canary_values(campaign, index), "user_id": user_id,
                      "context_json": json.dumps({"capacity_owner_canary": campaign})}
            run = connection.execute(text("""
                SELECT id, user_id, conversation_id, message, status, feature_mode,
                       visibility, interaction_mode, transport, request_id,
                       trace_id, idempotency_key FROM finn_v2_runs
                WHERE id=:run_id FOR UPDATE
            """), values).mappings().one_or_none()
            conversation = connection.execute(text("""
                SELECT id, user_id, title, context_json FROM finn_v2_conversations
                WHERE id=:conversation_id FOR UPDATE
            """), values).mappings().one_or_none()
            conversation_run_count = connection.execute(text("""
                SELECT COUNT(*) FROM finn_v2_runs WHERE conversation_id=:conversation_id
            """), values).scalar_one()
            watchlist = connection.execute(text("""
                SELECT id FROM watchlists WHERE user_id=:user_id AND symbol=:symbol FOR UPDATE
            """), values).mappings().one_or_none()
            if run is not None and (run["user_id"] != user_id
                                    or run["conversation_id"] != values["conversation_id"]
                                    or run["message"] != values["message"]
                                    or run["status"] != "completed"
                                    or run["feature_mode"] != "capacity_owner_canary"
                                    or run["visibility"] != "visible"
                                    or run["interaction_mode"] != "READ"
                                    or run["transport"] != "chat"
                                    or any(run[field] != values["run_id"] for field in
                                           ("request_id", "trace_id", "idempotency_key"))):
                raise RuntimeError("Canary run changed; refusing cleanup")
            if conversation is not None and (conversation["user_id"] != user_id
                                             or conversation["title"] != values["message"]
                                             or conversation["context_json"] != {"capacity_owner_canary": campaign}):
                raise RuntimeError("Canary conversation changed; refusing cleanup")
            if conversation_run_count != int(run is not None):
                raise RuntimeError("Canary conversation contains unexpected runs; refusing cleanup")
            if run is not None:
                assert_no_run_dependents(connection, values["run_id"])
                connection.execute(text("DELETE FROM finn_v2_runs WHERE id=:run_id AND user_id=:user_id"), values)
                removed += 1
            if conversation is not None:
                connection.execute(text("""
                    DELETE FROM finn_v2_conversations WHERE id=:conversation_id AND user_id=:user_id
                """), values)
                removed += 1
            if watchlist is not None:
                connection.execute(text("""
                    DELETE FROM watchlists WHERE id=:id AND user_id=:user_id AND symbol=:symbol
                """), {**values, "id": watchlist["id"]})
                removed += 1
    return {"campaign": campaign, "removed_rows": removed}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("seed", "cleanup"))
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--expected-db-host", required=True)
    parser.add_argument("--expected-db-port", required=True)
    parser.add_argument("--expected-db-name", required=True)
    parser.add_argument("--allow-production", action="store_true")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if not CAMPAIGN_RE.fullmatch(args.campaign):
        parser.error("Campaign must be a 3-32 character lowercase slug")
    if (args.expected_db_host, args.expected_db_port, args.expected_db_name) != (db_host, db_port, db_name):
        parser.error("Configured database target does not match expected host, port and name")
    if not args.allow_production:
        parser.error("Canary writes require explicit --allow-production on every database target")
    if not args.apply:
        parser.error("Canary writes require --apply")
    result = seed(args.campaign) if args.action == "seed" else cleanup(args.campaign)
    print(json.dumps({"action": args.action, "database_host": db_host,
                      "database_port": db_port, "database_name": db_name, **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
