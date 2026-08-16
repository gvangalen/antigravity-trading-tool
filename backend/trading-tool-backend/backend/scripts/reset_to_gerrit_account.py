#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv

from backend.utils.db import get_db_connection


ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV = ROOT / "backend" / ".env"
DEFAULT_BACKUP_DIR = ROOT / "tmp" / "db_backups"
ALLOWED_USER_ROLES = {"user", "admin"}


def load_environment() -> None:
    load_dotenv(BACKEND_ENV, override=False)


def env_value(name: str, fallback: str | None = None) -> str | None:
    return os.getenv(name) or fallback


def connect_kwargs() -> dict[str, str]:
    return {
        "host": env_value("DB_HOST", "127.0.0.1"),
        "port": env_value("DB_PORT", "5432"),
        "dbname": env_value("DB_NAME", "market_dashboard"),
        "user": env_value("DB_USER") or env_value("PGUSER") or "postgres",
        "password": env_value("DB_PASS") or env_value("DB_PASSWORD") or env_value("PGPASSWORD") or "",
    }


def make_dsn(kwargs: dict[str, str]) -> str:
    dsn = f"postgresql://{kwargs['user']}@{kwargs['host']}:{kwargs['port']}/{kwargs['dbname']}"
    return dsn


@dataclass(frozen=True)
class TableAction:
    label: str
    count_sql: str
    delete_sql: str
    mode: str


def sql_user(table: str) -> TableAction:
    return TableAction(
        label=table,
        count_sql=f"SELECT COUNT(*) FROM {table} WHERE user_id = ANY(%(all_target_user_ids)s)",
        delete_sql=f"DELETE FROM {table} WHERE user_id = ANY(%(all_target_user_ids)s)",
        mode="delete_all_target_users",
    )


def sql_non_gerrit_user(table: str) -> TableAction:
    return TableAction(
        label=table,
        count_sql=f"SELECT COUNT(*) FROM {table} WHERE user_id = ANY(%(other_user_ids)s)",
        delete_sql=f"DELETE FROM {table} WHERE user_id = ANY(%(other_user_ids)s)",
        mode="delete_other_users_only",
    )


def sql_non_gerrit_users_table() -> TableAction:
    return TableAction(
        label="users",
        count_sql="SELECT COUNT(*) FROM users WHERE id = ANY(%(other_user_ids)s)",
        delete_sql="DELETE FROM users WHERE id = ANY(%(other_user_ids)s)",
        mode="delete_other_users_only",
    )


ACTIONS: list[TableAction] = [
    sql_user("auth_refresh_sessions"),
    sql_user("auth_password_reset_tokens"),
    sql_user("mobile_push_tokens"),
    sql_user("push_subscriptions"),
    TableAction(
        label="chat_messages",
        count_sql="""
            SELECT COUNT(*)
            FROM chat_messages m
            JOIN chat_sessions s ON s.id = m.session_id
            WHERE s.user_id = ANY(%(all_target_user_ids)s)
        """,
        delete_sql="""
            DELETE FROM chat_messages
            WHERE session_id IN (
                SELECT id FROM chat_sessions WHERE user_id = ANY(%(all_target_user_ids)s)
            )
        """,
        mode="delete_all_target_users",
    ),
    sql_user("chat_sessions"),
    sql_user("conversation_state"),
    sql_user("ai_pending_actions"),
    sql_user("ai_intelligence_events"),
    sql_user("ai_reflections"),
    sql_user("finn_product_events"),
    sql_user("regime_memory"),
    sql_user("trading_advice"),
    sql_user("watchlists"),
    sql_user("onboarding_steps"),
    sql_user("user_indicator_configs"),
    sql_user("market_indicator_rules"),
    sql_user("macro_indicator_rules"),
    sql_user("technical_indicator_rules"),
    sql_user("market_data_indicators"),
    sql_user("macro_data"),
    sql_user("technical_indicators"),
    sql_user("daily_setup_scores"),
    sql_user("active_strategy_snapshot"),
    sql_user("indicator_curves"),
    sql_user("bot_trade_plans"),
    sql_user("bot_executions"),
    sql_user("bot_ledger"),
    sql_user("bot_orders"),
    sql_user("bot_decisions"),
    sql_user("bot_portfolio_snapshots"),
    sql_user("bot_portfolios"),
    sql_user("bot_configs"),
    sql_user("portfolio_balance_snapshots"),
    sql_user("report_snapshots"),
    sql_user("daily_reports"),
    sql_user("weekly_reports"),
    sql_user("monthly_reports"),
    sql_user("quarterly_reports"),
    sql_user("daily_scores"),
    sql_user("ai_category_insights"),
    sql_user("ai_usage_logs"),
    sql_user("system_logs"),
    sql_user("strategies"),
    sql_user("setups"),
    sql_non_gerrit_user("exchange_keys"),
    sql_non_gerrit_users_table(),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reset the live test database to one clean Gerrit account while preserving Gerrit's exchange keys."
    )
    parser.add_argument("--gerrit-user-id", type=int, required=True)
    parser.add_argument("--gerrit-email", required=True)
    parser.add_argument("--execute", action="store_true", help="Run the live reset. Default is dry-run.")
    parser.add_argument("--backup-dir", default=str(DEFAULT_BACKUP_DIR))
    parser.add_argument("--yes", action="store_true", help="Skip interactive confirmation for --execute.")
    parser.add_argument(
        "--allow-missing-gerrit-exchange",
        action="store_true",
        help="Allow live reset even when Gerrit has no exchange_keys row to preserve.",
    )
    parser.add_argument(
        "--drop-gerrit-exchange",
        action="store_true",
        help="Delete Gerrit's exchange_keys rows too, leaving only the account/login.",
    )
    return parser.parse_args()


def _rows_as_dicts(cur) -> list[dict[str, Any]]:
    columns = [desc[0] for desc in (cur.description or [])]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def fetch_one(cur, sql: str, params: dict | None = None):
    cur.execute(sql, params or {})
    rows = _rows_as_dicts(cur)
    return rows[0] if rows else None


def fetch_all(cur, sql: str, params: dict | None = None):
    cur.execute(sql, params or {})
    return _rows_as_dicts(cur)


def identify_gerrit(cur, user_id: int, email: str) -> dict:
    rows = fetch_all(
        cur,
        """
        SELECT id, email, first_name, last_name, role, is_active, subscription_status
        FROM users
        WHERE id = %(user_id)s
           OR lower(email) = lower(%(email)s)
        ORDER BY id
        """,
        {"user_id": user_id, "email": email},
    )
    if len(rows) != 1:
        raise RuntimeError(
            f"Gerrit identity check failed: expected exactly 1 row for user_id={user_id} or email={email}, found {len(rows)}."
        )
    row = rows[0]
    if row["id"] != user_id or row["email"].lower() != email.lower():
        raise RuntimeError(
            f"Gerrit identity mismatch: row resolved to id={row['id']} email={row['email']} instead of id={user_id} email={email}."
        )
    return row


def find_users(cur, gerrit_user_id: int) -> list[dict]:
    users = fetch_all(
        cur,
        """
        SELECT id, email, first_name, last_name, role, is_active, subscription_status
        FROM users
        ORDER BY id
        """
    )
    unknown_roles = [u for u in users if str(u["role"]) not in ALLOWED_USER_ROLES]
    if unknown_roles:
        roles = ", ".join(f"{u['id']}:{u['email']}:{u['role']}" for u in unknown_roles)
        raise RuntimeError(f"Unknown system or service accounts detected via unexpected roles: {roles}")
    return [u for u in users if u["id"] != gerrit_user_id]


def count_exchange_keys(cur, gerrit_user_id: int) -> tuple[int, int]:
    preserved = fetch_one(
        cur,
        "SELECT COUNT(*) AS count FROM exchange_keys WHERE user_id = %(gerrit_user_id)s",
        {"gerrit_user_id": gerrit_user_id},
    )["count"]
    removed = fetch_one(
        cur,
        "SELECT COUNT(*) AS count FROM exchange_keys WHERE user_id <> %(gerrit_user_id)s",
        {"gerrit_user_id": gerrit_user_id},
    )["count"]
    return preserved, removed


def count_gerrit_exchange_keys(cur, gerrit_user_id: int) -> int:
    return fetch_one(
        cur,
        "SELECT COUNT(*) AS count FROM exchange_keys WHERE user_id = %(gerrit_user_id)s",
        {"gerrit_user_id": gerrit_user_id},
    )["count"]


def collect_action_counts(cur, params: dict) -> list[tuple[str, int, str]]:
    rows: list[tuple[str, int, str]] = []
    for action in ACTIONS:
        count = fetch_one(cur, action.count_sql, params)["count"]
        rows.append((action.label, int(count), action.mode))
    return rows


def format_count_table(rows: list[tuple[str, int, str]]) -> str:
    width = max(len(label) for label, _, _ in rows)
    lines = []
    for label, count, mode in rows:
        lines.append(f"{label.ljust(width)}  {str(count).rjust(8)}  {mode}")
    return "\n".join(lines)


def backup_database(kwargs: dict[str, str], backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"market_dashboard_pre_gerrit_reset_{timestamp}.dump"
    if not shutil.which("pg_dump"):
        raise RuntimeError("pg_dump not found in PATH.")
    env = os.environ.copy()
    if kwargs["password"]:
        env["PGPASSWORD"] = kwargs["password"]
    subprocess.run(
        [
            "pg_dump",
            "-h",
            kwargs["host"],
            "-p",
            kwargs["port"],
            "-U",
            kwargs["user"],
            "-d",
            kwargs["dbname"],
            "-Fc",
            "-f",
            str(backup_path),
        ],
        check=True,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    if not backup_path.exists() or backup_path.stat().st_size == 0:
        raise RuntimeError("Backup failed: no backup file was created.")
    return backup_path


def confirm_execute() -> None:
    answer = input("Type RESET to execute the live Gerrit-only database reset: ").strip()
    if answer != "RESET":
        raise RuntimeError("Execution cancelled. Expected exact confirmation string RESET.")


def run_reset(cur, params: dict) -> None:
    for action in ACTIONS:
        cur.execute(action.delete_sql, params)
    cur.execute(
        """
        UPDATE users
        SET
            ai_preferences = DEFAULT,
            ai_plan = DEFAULT,
            ai_requests_limit_day = DEFAULT,
            ai_requests_used_day = DEFAULT,
            ai_usage_current = DEFAULT,
            ai_monthly_budget = DEFAULT,
            last_usage_reset = NULL,
            ai_tokens_used_month = DEFAULT
        WHERE id = %(gerrit_user_id)s
        """,
        params,
    )


def validate_post_reset(
    cur,
    gerrit_user_id: int,
    allow_missing_gerrit_exchange: bool,
    drop_gerrit_exchange: bool,
) -> list[str]:
    failures: list[str] = []

    users_remaining = fetch_all(
        cur,
        "SELECT id, email FROM users ORDER BY id",
    )
    if len(users_remaining) != 1 or users_remaining[0]["id"] != gerrit_user_id:
        failures.append(f"Expected only Gerrit user to remain, found: {users_remaining}")

    gerrit_exchange = fetch_one(
        cur,
        "SELECT COUNT(*) AS count FROM exchange_keys WHERE user_id = %(gerrit_user_id)s",
        {"gerrit_user_id": gerrit_user_id},
    )["count"]
    if drop_gerrit_exchange:
        if gerrit_exchange != 0:
            failures.append(f"Expected 0 Gerrit exchange_keys rows, found {gerrit_exchange}.")
    elif gerrit_exchange < 1 and not allow_missing_gerrit_exchange:
        failures.append("Expected at least one Gerrit exchange_keys row to remain.")

    zero_tables = [
        "watchlists",
        "setups",
        "strategies",
        "chat_sessions",
        "conversation_state",
        "bot_configs",
        "bot_decisions",
        "bot_trade_plans",
        "bot_orders",
        "bot_executions",
        "bot_ledger",
        "bot_portfolios",
        "bot_portfolio_snapshots",
        "portfolio_balance_snapshots",
        "daily_reports",
        "weekly_reports",
        "monthly_reports",
        "quarterly_reports",
        "report_snapshots",
    ]
    for table in zero_tables:
        count = fetch_one(
            cur,
            f"SELECT COUNT(*) AS count FROM {table} WHERE user_id = %(gerrit_user_id)s",
            {"gerrit_user_id": gerrit_user_id},
        )["count"]
        if count != 0:
            failures.append(f"Expected 0 Gerrit rows in {table}, found {count}.")

    chat_message_count = fetch_one(
        cur,
        """
        SELECT COUNT(*)
        FROM chat_messages m
        JOIN chat_sessions s ON s.id = m.session_id
        WHERE s.user_id = %(gerrit_user_id)s
        """,
        {"gerrit_user_id": gerrit_user_id},
    )["count"]
    if chat_message_count != 0:
        failures.append(f"Expected 0 Gerrit chat_messages rows, found {chat_message_count}.")

    other_exchange = fetch_one(
        cur,
        "SELECT COUNT(*) AS count FROM exchange_keys WHERE user_id <> %(gerrit_user_id)s",
        {"gerrit_user_id": gerrit_user_id},
    )["count"]
    if other_exchange != 0:
        failures.append(f"Expected 0 non-Gerrit exchange_keys rows, found {other_exchange}.")

    return failures


def main() -> int:
    load_environment()
    args = parse_args()
    db_kwargs = connect_kwargs()
    dsn = make_dsn(db_kwargs)
    print(f"Target database: {dsn}")
    conn = get_db_connection()
    if conn is None:
        print("\nReset aborted: database connection unavailable.", file=sys.stderr)
        return 1
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            gerrit = identify_gerrit(cur, args.gerrit_user_id, args.gerrit_email)
            other_users = find_users(cur, args.gerrit_user_id)
            other_user_ids = [u["id"] for u in other_users]
            all_target_user_ids = [args.gerrit_user_id] + other_user_ids
            params = {
                "gerrit_user_id": args.gerrit_user_id,
                "gerrit_email": args.gerrit_email,
                "other_user_ids": other_user_ids,
                "all_target_user_ids": all_target_user_ids,
            }

            preserved_exchange_count, removed_exchange_count = count_exchange_keys(cur, args.gerrit_user_id)
            gerrit_exchange_to_drop = count_gerrit_exchange_keys(cur, args.gerrit_user_id) if args.drop_gerrit_exchange else 0
            action_counts = collect_action_counts(cur, params)

            print("\nGerrit identity")
            print(
                f"  user_id={gerrit['id']} email={gerrit['email']} role={gerrit['role']} active={gerrit['is_active']}"
            )
            print(f"  subscription_status={gerrit['subscription_status']}")

            print("\nOther users to delete")
            for user in other_users:
                print(
                    f"  id={user['id']} email={user['email']} role={user['role']} active={user['is_active']}"
                )

            print("\nExchange key summary")
            print(f"  Gerrit exchange_keys preserved: {preserved_exchange_count}")
            print(f"  Non-Gerrit exchange_keys removed: {removed_exchange_count}")
            if args.drop_gerrit_exchange:
                print(f"  Gerrit exchange_keys removed too: {gerrit_exchange_to_drop}")

            print("\nDry-run deletion counts")
            print(format_count_table(action_counts))

            if not args.execute:
                conn.rollback()
                print("\nDry-run only. No changes were applied.")
                print("Run again with --execute after reviewing the counts and confirming the target Gerrit identity.")
                return 0

            backup_dir = Path(args.backup_dir)
            backup_path = backup_database(db_kwargs, backup_dir)
            print(f"\nBackup created: {backup_path}")

            if not args.yes:
                confirm_execute()

            if args.drop_gerrit_exchange:
                cur.execute(
                    "DELETE FROM exchange_keys WHERE user_id = %(gerrit_user_id)s",
                    params,
                )
            run_reset(cur, params)
            failures = validate_post_reset(
                cur,
                args.gerrit_user_id,
                args.allow_missing_gerrit_exchange,
                args.drop_gerrit_exchange,
            )
            if failures:
                raise RuntimeError("Post-reset validation failed:\n- " + "\n- ".join(failures))

            conn.commit()
            print("\nLive reset completed successfully.")
            print("Post-reset validation passed.")
            print(f"Gerrit exchange_keys preserved: {preserved_exchange_count}")
            print("All other users, bots, orders, plans, chats, reports, and user state were removed.")
            return 0
    except Exception as exc:
        conn.rollback()
        print(f"\nReset aborted: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
