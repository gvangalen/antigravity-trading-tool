"""Read-only protected inspection of Paper-opening strategy column types."""

from __future__ import annotations

REQUIRED = {
    "targets": {("ARRAY", "_text")},
    "market_id": {("bigint", "int8")},
    "data": {("jsonb", "jsonb")},
    "setup_type": {("character varying", "varchar"), ("text", "text")},
    "entry": {("numeric", "numeric")},
    "stop_loss": {("numeric", "numeric")},
}
SAFE_TYPES = {item for allowed in REQUIRED.values() for item in allowed}
CONSTRAINT_KINDS = {"f": "FOREIGN_KEY", "c": "CHECK", "u": "UNIQUE", "p": "PRIMARY_KEY"}
SAFE_CONSTRAINT_NAMES = frozenset({
    "strategies_pkey", "strategies_user_id_fkey",
    "strategies_setup_id_fkey", "strategies_market_id_fkey",
})


def run() -> dict:
    from backend.utils.db import get_db_connection

    conn = get_db_connection()
    if conn is None:
        raise RuntimeError("trader_strategy_schema_database_unavailable")
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
            cur.execute(
                """SELECT column_name,data_type,udt_name,is_nullable
                   FROM information_schema.columns
                   WHERE table_schema='public' AND table_name='strategies'
                     AND column_name=ANY(%s::text[])""",
                (list(REQUIRED),),
            )
            rows = cur.fetchall()
            cur.execute(
                """SELECT c.conname,c.contype,a.attname
                   FROM pg_constraint c JOIN pg_attribute a
                     ON a.attrelid=c.conrelid AND a.attnum=ANY(c.conkey)
                   WHERE c.conrelid='public.strategies'::regclass
                     AND c.contype IN ('f','c','u','p')
                     AND a.attname=ANY(%s::text[])
                   ORDER BY c.conname,a.attname""",
                (list(REQUIRED),),
            )
            constraint_rows = cur.fetchall()
            cur.execute(
                """SELECT tgenabled FROM pg_trigger
                   WHERE tgrelid='public.strategies'::regclass AND NOT tgisinternal"""
            )
            trigger_rows = cur.fetchall()
        columns = {}
        for name, data_type, udt_name, nullable in rows:
            if name not in REQUIRED or name in columns:
                raise RuntimeError("trader_strategy_schema_unexpected_column")
            pair = (data_type, udt_name)
            columns[name] = {
                "data_type": data_type if pair in SAFE_TYPES else "OTHER",
                "udt_name": udt_name if pair in SAFE_TYPES else "OTHER",
                "nullable": nullable == "YES",
                "matches_expected": pair in REQUIRED[name],
            }
        constraints = {}
        other_count = 0
        for name, kind, column in constraint_rows:
            if (column not in REQUIRED or kind not in CONSTRAINT_KINDS
                    or name not in SAFE_CONSTRAINT_NAMES):
                other_count += 1
                continue
            item = constraints.setdefault(name, {"kind": CONSTRAINT_KINDS[kind], "columns": []})
            if item["kind"] != CONSTRAINT_KINDS[kind]:
                raise RuntimeError("trader_strategy_schema_constraint_conflict")
            if column not in item["columns"]:
                item["columns"].append(column)
        missing = sorted(set(REQUIRED) - set(columns))
        matches = not missing and all(item["matches_expected"] for item in columns.values())
        return {
            "result": "PASS" if matches else "FAIL",
            "type_contract_matches": matches,
            "missing_columns": missing,
            "columns": {name: columns[name] for name in sorted(columns)},
            "constraints": {name: constraints[name] for name in sorted(constraints)},
            "other_constraint_rows": min(other_count, 40),
            "other_constraint_rows_capped": other_count > 40,
            "user_trigger_count": min(len(trigger_rows), 40),
            "user_trigger_count_capped": len(trigger_rows) > 40,
            "enabled_user_trigger_count": min(sum(row[0] != "D" for row in trigger_rows), 40),
        }
    finally:
        conn.close()
