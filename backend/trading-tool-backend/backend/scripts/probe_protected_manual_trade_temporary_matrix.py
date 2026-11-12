"""One protected temporary-owner manual-trade matrix under the host QA lock.

This module is invoked only by the independent QA workflow. Build may validate
it locally, but never runs it against the production QA binding or manifest.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
from typing import Any

from sqlalchemy import text

from backend.infrastructure.database import async_session_factory
from backend.scripts.probe_protected_manual_trade_fixture_prepare import (
    _journal, _markets, _source_preflight, run as prepare_fixture,
)
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.services.setup_service import SetupService
from backend.utils.auth_utils import FINN_TEMP_QA_KIND, create_token, hash_password
from backend.scripts.finn_v2_matrix_transport import TERMINAL_STATUSES

PARENT_MARKER = "finn_production_qa_v1"
CHILD_SETUP_MARKER = "finn_manual_trade_qa_child_choice_v1"
PARENT_TABLES = ("users", "setups", "strategies", "bot_configs", "daily_scores",
                 "user_indicator_configs", "user_market_benchmark_weights",
                 "finn_manual_trade_plans", "bot_orders")
DENIED_CHILD_TABLES = {"exchange_keys", "bot_orders", "bot_configs", "strategies"}
LOOSE_CHILD_TABLES = {"market_data_indicators", "macro_data",
                      "technical_indicators", "market_indicator_rules",
                      "macro_indicator_rules", "technical_indicator_rules",
                      "system_logs"}


def _db(awaitable):
    """Use the runner's persistent event loop for its asyncpg connection pool."""
    from backend.scripts.run_finn_production_qa import _shared_database_loop
    return _shared_database_loop().run_until_complete(awaitable)


def _email(namespace: str) -> str:
    return f"finn-qa-{namespace}@example.invalid"


def _path_state(path: Path, namespace: str, release_sha: str, parent: int) -> dict[str, Any]:
    if path.exists():
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise RuntimeError("temporary_qa_journal_invalid")
        state = json.loads(path.read_text())
        if (state.get("kind") != FINN_TEMP_QA_KIND or state.get("namespace") != namespace
                or state.get("release_sha") != release_sha or state.get("parent") != parent):
            raise RuntimeError("temporary_qa_journal_binding_changed")
        return state
    state = {"kind": FINN_TEMP_QA_KIND, "namespace": namespace,
             "release_sha": release_sha, "parent": parent, "phase": "started"}
    _journal(path, state)
    return state


async def _parent_state(session, parent: int) -> str:
    owner = (await session.execute(text("""
        SELECT role,is_active,ai_preferences FROM users WHERE id=:parent FOR UPDATE
    """), {"parent": parent})).mappings().one_or_none()
    if (owner is None or owner["role"] != "user" or owner["is_active"] is not True
            or not isinstance(owner["ai_preferences"], dict)
            or owner["ai_preferences"].get("qa_fixture") != PARENT_MARKER):
        raise RuntimeError("temporary_qa_parent_invalid")
    states: dict[str, Any] = {}
    for table in PARENT_TABLES:
        condition = "id=:parent" if table == "users" else "user_id=:parent"
        rows = (await session.execute(text(
            f"SELECT to_jsonb(t) AS state FROM {table} AS t WHERE {condition} "
            "ORDER BY to_jsonb(t)::text"
        ), {"parent": parent})).scalars().all()
        states[table] = rows
    return hashlib.sha256(json.dumps(states, sort_keys=True, default=str,
                                     separators=(",", ":")).encode()).hexdigest()


async def _create_child(parent: int, namespace: str, lease_secret: str) -> tuple[int, str]:
    async with async_session_factory() as session:
        parent_hash = await _parent_state(session, parent)
        existing = (await session.execute(text("SELECT id FROM users WHERE email=:email"),
                                          {"email": _email(namespace)})).scalar_one_or_none()
        if existing is not None:
            raise RuntimeError("temporary_qa_child_collision")
        parent_plan = (await session.execute(text("""
            SELECT ai_plan,ai_requests_limit_day,ai_monthly_budget
            FROM users WHERE id=:parent
        """), {"parent": parent})).mappings().one()
        preferences = {"qa_fixture": FINN_TEMP_QA_KIND,
                       "finn_temp_qa": {"namespace": namespace, "parent": parent,
                                        "lease": lease_secret, "status": "preparing",
                                        "expires_at": (datetime.now(timezone.utc)
                                                       + timedelta(minutes=75)).isoformat()}}
        password = secrets.token_urlsafe(48)
        child = (await session.execute(text("""
            INSERT INTO users (email,password_hash,role,is_active,first_name,
                subscription_status,ai_plan,ai_requests_limit_day,ai_monthly_budget,
                ai_preferences,created_at)
            VALUES (:email,:password_hash,'user',FALSE,'FINN QA temporary',
                'active',:ai_plan,:requests,:budget,CAST(:preferences AS jsonb),CURRENT_TIMESTAMP)
            RETURNING id
        """), {"email": _email(namespace), "password_hash": hash_password(password),
               "ai_plan": parent_plan["ai_plan"],
               "requests": parent_plan["ai_requests_limit_day"],
               "budget": parent_plan["ai_monthly_budget"],
               "preferences": json.dumps(preferences)})).scalar_one()
        await session.commit()
    return int(child), parent_hash


async def _find_child(parent: int, namespace: str) -> int | None:
    async with async_session_factory() as session:
        row = (await session.execute(text("""
            SELECT id,role,ai_preferences FROM users WHERE email=:email
        """), {"email": _email(namespace)})).mappings().one_or_none()
        if row is None:
            return None
        prefs = row["ai_preferences"]
        lease = prefs.get("finn_temp_qa") if isinstance(prefs, dict) else None
        if (row["role"] != "user" or not isinstance(prefs, dict)
                or prefs.get("qa_fixture") != FINN_TEMP_QA_KIND
                or not isinstance(lease, dict) or lease.get("namespace") != namespace
                or lease.get("parent") != parent):
            raise RuntimeError("temporary_qa_child_binding_changed")
        return int(row["id"])


async def _seed_btc_choices(child: int) -> None:
    async with async_session_factory() as session:
        markets = await _markets(session)
        for choice in ("A", "B"):
            payload = {"name": f"FINN QA BTC/EUR choice {choice}", "symbol": "BTC",
                       "market_id": markets["BTC"], "timeframe": "1d",
                       "setup_type": "trade", "min_benchmark_score": 0,
                       "max_benchmark_score": 100, "description": CHILD_SETUP_MARKER,
                       "explanation": CHILD_SETUP_MARKER}
            SetupService(session).validate_setup_payload(dict(payload))
            created = await SetupRepository(session).create_setup(
                payload, child, [CHILD_SETUP_MARKER])
            if type(created) is not int or created <= 0:
                raise RuntimeError("temporary_qa_btc_choice_create_failed")
        await session.commit()


async def _extend_lease(child: int, namespace: str, lease_secret: str) -> None:
    async with async_session_factory() as session:
        updated = await session.execute(text("""
            UPDATE users SET is_active=TRUE,
                ai_preferences=jsonb_set(jsonb_set(ai_preferences,
                '{finn_temp_qa,expires_at}',to_jsonb(CAST(:expires_at AS text))),
                '{finn_temp_qa,status}',to_jsonb(CAST('active' AS text)))
            WHERE id=:child AND ai_preferences->>'qa_fixture'=:kind
              AND ai_preferences->'finn_temp_qa'->>'namespace'=:namespace
              AND ai_preferences->'finn_temp_qa'->>'lease'=:lease
              AND ai_preferences->'finn_temp_qa'->>'status'='preparing'
        """), {"child": child, "kind": FINN_TEMP_QA_KIND, "namespace": namespace,
               "lease": lease_secret,
               "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=45)).isoformat()})
        if updated.rowcount != 1:
            raise RuntimeError("temporary_qa_lease_changed")
        await session.commit()


async def _revoke_child(child: int, namespace: str) -> None:
    async with async_session_factory() as session:
        updated = await session.execute(text("""
            UPDATE users SET is_active=FALSE,
                ai_preferences=jsonb_set(ai_preferences,
                    '{finn_temp_qa,status}',to_jsonb(CAST('revoked' AS text)))
            WHERE id=:child AND ai_preferences->>'qa_fixture'=:kind
              AND ai_preferences->'finn_temp_qa'->>'namespace'=:namespace
        """), {"child": child, "kind": FINN_TEMP_QA_KIND,
               "namespace": namespace})
        if updated.rowcount != 1:
            raise RuntimeError("temporary_qa_revoke_cas_failed")
        await session.commit()


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


async def _delete_child(child: int, namespace: str) -> None:
    """Delete only a revoked, exact-marked child when its FK graph is safe."""
    async with async_session_factory() as session:
        row = (await session.execute(text("""
            SELECT role,is_active,ai_preferences FROM users WHERE id=:child FOR UPDATE
        """), {"child": child})).mappings().one_or_none()
        if row is None:
            return
        prefs = row["ai_preferences"]
        lease = prefs.get("finn_temp_qa") if isinstance(prefs, dict) else None
        if (row["role"] != "user" or row["is_active"] is not False
                or not isinstance(prefs, dict)
                or prefs.get("qa_fixture") != FINN_TEMP_QA_KIND
                or not isinstance(lease, dict) or lease.get("namespace") != namespace
                or lease.get("status") != "revoked"):
            raise RuntimeError("temporary_qa_delete_binding_changed")
        unsafe = (await session.execute(text("""
            SELECT
              (SELECT count(*) FROM exchange_keys WHERE user_id=:child) AS keys,
              (SELECT count(*) FROM bot_orders WHERE user_id=:child) AS orders,
              (SELECT count(*) FROM bot_configs WHERE user_id=:child) AS bots,
              (SELECT count(*) FROM strategies WHERE user_id=:child) AS strategies,
              (SELECT count(*) FROM finn_manual_trade_plans
                 WHERE user_id=:child AND plan_json->>'executable' IS DISTINCT FROM 'false') AS executable_plans
        """), {"child": child})).mappings().one()
        if any(int(value) for value in unsafe.values()):
            raise RuntimeError("temporary_qa_unexpected_child_rows")
        fk_rows = (await session.execute(text("""
            SELECT n.nspname AS schema_name,t.relname AS table_name,
                   a.attname AS column_name,c.confdeltype::text AS delete_action,
                   array_length(c.conkey,1) AS key_columns
            FROM pg_constraint c
            JOIN pg_class t ON t.oid=c.conrelid
            JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_attribute a ON a.attrelid=t.oid AND a.attnum=c.conkey[1]
            WHERE c.contype='f' AND c.confrelid='users'::regclass
        """))).mappings().all()
        if not fk_rows:
            raise RuntimeError("temporary_qa_user_fk_graph_unavailable")
        if any(row["key_columns"] != 1 for row in fk_rows):
            raise RuntimeError("temporary_qa_composite_user_fk_unverified")
        fk_map = {(row["schema_name"], row["table_name"], row["column_name"]):
                  row["delete_action"] for row in fk_rows}
        owner_columns = (await session.execute(text("""
            SELECT n.nspname AS schema_name,t.relname AS table_name,
                   a.attname AS column_name
            FROM pg_class t
            JOIN pg_namespace n ON n.oid=t.relnamespace
            JOIN pg_attribute a ON a.attrelid=t.oid
            JOIN pg_type y ON y.oid=a.atttypid
            WHERE n.nspname='public' AND t.relkind IN ('r','p')
              AND a.attname='user_id' AND NOT a.attisdropped
              AND y.typname IN ('int4','int8')
        """))).mappings().all()
        if not owner_columns:
            raise RuntimeError("temporary_qa_owner_columns_unavailable")
        direct_columns = {(row["schema_name"], row["table_name"],
                           row["column_name"]) for row in owner_columns}
        if not set(fk_map).issubset(direct_columns):
            raise RuntimeError("temporary_qa_other_user_fk_unverified")
        loose = []
        for column_row in owner_columns:
            identity = (column_row["schema_name"], column_row["table_name"],
                        column_row["column_name"])
            table = f"{_quoted(identity[0])}.{_quoted(identity[1])}"
            column = _quoted(identity[2])
            count = (await session.execute(text(
                f"SELECT count(*) FROM {table} WHERE {column}=:child"
            ), {"child": child})).scalar_one()
            if not int(count):
                continue
            if identity[1] in DENIED_CHILD_TABLES:
                raise RuntimeError("temporary_qa_unexpected_child_rows")
            action = fk_map.get(identity)
            if action is None:
                if identity[1] not in LOOSE_CHILD_TABLES:
                    raise RuntimeError("temporary_qa_unowned_child_column")
                loose.append((table, column))
            elif identity[1] == "ai_usage_logs":
                await session.execute(text(f"DELETE FROM {table} WHERE {column}=:child"),
                                      {"child": child})
            elif action != "c":
                raise RuntimeError("temporary_qa_non_cascade_child_fk")
        for fk in fk_rows:
            if fk["schema_name"] != "public":
                raise RuntimeError("temporary_qa_external_user_fk_unverified")
        removed = await session.execute(text("""
            DELETE FROM users WHERE id=:child AND is_active=FALSE
              AND ai_preferences->>'qa_fixture'=:kind
              AND ai_preferences->'finn_temp_qa'->>'namespace'=:namespace
              AND ai_preferences->'finn_temp_qa'->>'status'='revoked'
        """), {"child": child, "kind": FINN_TEMP_QA_KIND,
               "namespace": namespace})
        if removed.rowcount != 1:
            raise RuntimeError("temporary_qa_delete_cas_failed")
        for table, column in loose:
            await session.execute(text(f"DELETE FROM {table} WHERE {column}=:child"),
                                  {"child": child})
        for column_row in owner_columns:
            table = f"{_quoted(column_row['schema_name'])}.{_quoted(column_row['table_name'])}"
            column = _quoted(column_row["column_name"])
            remains = (await session.execute(text(
                f"SELECT count(*) FROM {table} WHERE {column}=:child"
            ), {"child": child})).scalar_one()
            if int(remains):
                raise RuntimeError("temporary_qa_child_rows_remain")
        await session.commit()


async def _parent_unchanged(parent: int, expected_hash: str) -> bool:
    async with async_session_factory() as session:
        current = await _parent_state(session, parent)
        await session.rollback()
    return current == expected_hash


async def _child_quiescent(child: int) -> bool:
    async with async_session_factory() as session:
        rows = (await session.execute(text("""
            SELECT status FROM finn_v2_runs WHERE user_id=:child
        """), {"child": child})).scalars().all()
        await session.rollback()
    return all(status in TERMINAL_STATUSES for status in rows)


def _assert_manual_trade_manifest(cases: list[dict[str, Any]]) -> None:
    if not 1 <= len(cases) <= 16:
        raise RuntimeError("temporary_qa_manifest_count_invalid")
    for case in cases:
        operation = case.get("expected_operation_id")
        if operation not in (None, "create_manual_trade_plan"):
            raise RuntimeError("temporary_qa_manifest_operation_invalid")
        if case.get("fixture_action", "read_only") not in (
                "read_only", "proposal", "confirmation", "safe_execution"):
            raise RuntimeError("temporary_qa_manifest_action_invalid")


def run(args, report: dict[str, Any]) -> dict[str, Any]:
    """Provision, prepare, test, revoke and remove one marked child account."""
    from backend.scripts import run_finn_production_qa as qa

    namespace = args.fixture_namespace or ""
    if (not re.fullmatch(r"qa-[0-9]+-[0-9]+-[0-9a-f]{8}-[0-9a-f]{8}", namespace)
            or os.getenv("FINN_QA_ALLOW_MANUAL_TRADE_PREPARE") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") != "1"
            or args.manifest_id == "none"):
        raise RuntimeError("temporary_qa_not_authorized")
    parent_raw = os.getenv("FINN_QA_USER_ID", "")
    if not parent_raw.isdecimal() or int(parent_raw) <= 0:
        raise RuntimeError("temporary_qa_parent_binding_invalid")
    parent = int(parent_raw)
    report_path = Path(args.report_path)
    journal_path = report_path.with_suffix(".temp-journal.json")
    state = _path_state(journal_path, namespace, args.release_sha, parent)
    child = None
    parent_hash = None
    child_report = report_path.with_suffix(".child-report.json")
    try:
        if state["phase"] != "started":
            child = _db(_find_child(parent, namespace))
            raise RuntimeError("temporary_qa_prior_attempt_interrupted")
        # Validate the QA-owned manifest and genuine sources before any write.
        if args.manifest_bundle_path:
            crypto_script = Path(args.manifest_crypto_script or
                                 Path(args.checkout) / "ops/qa/finn_qa_manifest_bundle.py")
            qa.stage_manifest_bundle(
                crypto_script=crypto_script,
                private_key_path=Path(args.manifest_private_key_path),
                bundle_path=Path(args.manifest_bundle_path),
                manifest_root=Path(args.manifest_root),
                manifest_id=args.manifest_id,
            )
        cases = list(qa.load_manifest(
            manifest_root=Path(args.manifest_root), manifest_id=args.manifest_id,
            fixture_namespace=namespace))
        _assert_manual_trade_manifest(cases)
        report["manifest_sha256"] = qa.sha256_file(qa.manifest_path(
            manifest_root=Path(args.manifest_root), manifest_id=args.manifest_id))
        report["planned_count"] = len(cases)
        _db(_source_preflight())
        lease_secret = secrets.token_urlsafe(32)
        child, parent_hash = _db(_create_child(parent, namespace, lease_secret))
        state["phase"] = "child_created"
        _journal(journal_path, state)
        _db(_seed_btc_choices(child))
        state["phase"] = "choices_seeded"
        _journal(journal_path, state)
        original_env = {key: os.environ.get(key) for key in (
            "FINN_QA_USER_ID", "FINN_QA_TEMP_CHILD_RUN", "FINN_QA_FIXTURE_NAMESPACE")}
        os.environ["FINN_QA_USER_ID"] = str(child)
        os.environ["FINN_QA_TEMP_CHILD_RUN"] = "1"
        os.environ["FINN_QA_FIXTURE_NAMESPACE"] = namespace
        try:
            _db(prepare_fixture(
                journal_path=report_path.with_suffix(".prepare-journal.json"),
                release_sha=args.release_sha, fixture_namespace=namespace))
        finally:
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
        state["phase"] = "prepared"
        _journal(journal_path, state)
        _db(_extend_lease(child, namespace, lease_secret))
        child_env = os.environ.copy()
        child_env["FINN_QA_USER_ID"] = str(child)
        child_env["FINN_QA_TEMP_CHILD_RUN"] = "1"
        command = [sys.executable, str(Path(__file__).with_name("run_finn_production_qa.py")),
                   "--release-sha", args.release_sha, "--profile", "targeted_regression",
                   "--manifest-id", args.manifest_id, "--run-label", args.run_label,
                   "--base-url", args.base_url, "--checkout", args.checkout,
                   "--release-marker", args.release_marker,
                   "--manifest-root", args.manifest_root,
                   "--manifest-private-key-path", args.manifest_private_key_path,
                   "--report-path", str(child_report),
                   "--workflow-run-id", args.workflow_run_id,
                   "--fixture-namespace", namespace,
                   "--matrix-deadline-seconds", "2100",
                   "--case-timeout-seconds", "60"]
        if args.runner_revision:
            command.extend(["--runner-revision", args.runner_revision])
        state["phase"] = "matrix_running"
        _journal(journal_path, state)
        try:
            os.fstat(9)  # Host-wide protected QA flock, inherited by the child.
        except OSError as error:
            raise RuntimeError("temporary_qa_host_lock_missing") from error
        process = subprocess.Popen(command, env=child_env, stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True, pass_fds=(9,))
        try:
            matrix_exit = process.wait(timeout=2400)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise RuntimeError("temporary_qa_matrix_timeout")
        if child_report.exists():
            matrix = json.loads(child_report.read_text())
            for key in ("auth_preflight", "cases", "planned_count", "attempted_count",
                        "completed_count", "failed_count", "not_run_count", "incomplete",
                        "failure_summary", "safety", "manifest_sha256", "base_manifest_hash"):
                if key in matrix:
                    report[key] = matrix[key]
            report["matrix_outcome"] = matrix.get("outcome")
            report["matrix_qa_status"] = matrix.get("qa_status")
        else:
            report["matrix_outcome"] = "missing_report"
        if matrix_exit != 0:
            raise RuntimeError("temporary_qa_matrix_failed")
        state["phase"] = "matrix_complete"
        _journal(journal_path, state)
    finally:
        if child is None:
            child = _db(_find_child(parent, namespace))
        if child is not None:
            cleanup_ready = (
                state["phase"] == "matrix_complete"
                and report.get("matrix_outcome") == "passed"
                and _db(_child_quiescent(child))
            )
            if cleanup_ready:
                # Prove the same fresh bearer works immediately before revocation.
                fresh_token = create_token({"sub": str(child), "role": "user",
                                            "finn_temp_qa": {"kind": FINN_TEMP_QA_KIND,
                                                             "namespace": namespace,
                                                             "lease": lease_secret}},
                                           timedelta(minutes=2), "access")
                status_before, *_ = qa.request_json(
                    url=f"{args.base_url.rstrip('/')}/api/auth/me", token=fresh_token,
                    timeout_seconds=10.0)
                report["temporary_qa_pre_revocation_http_200"] = status_before == 200
                if status_before != 200:
                    cleanup_ready = False
            _db(_revoke_child(child, namespace))
            report["temporary_qa_token_revoked"] = True
            if cleanup_ready:
                status, *_ = qa.request_json(
                    url=f"{args.base_url.rstrip('/')}/api/auth/me", token=fresh_token,
                    timeout_seconds=10.0)
                report["temporary_qa_revocation_http_401"] = status == 401
                if status != 401:
                    raise RuntimeError("temporary_qa_revocation_not_enforced")
                if not _db(_child_quiescent(child)):
                    cleanup_ready = False
                if cleanup_ready:
                    _db(_delete_child(child, namespace))
                    report["temporary_qa_child_deleted"] = True
            if not report.get("temporary_qa_child_deleted"):
                report["temporary_qa_child_quarantined"] = True
        if parent_hash is not None:
            report["temporary_qa_parent_unchanged"] = _db(
                _parent_unchanged(parent, parent_hash))
            if not report["temporary_qa_parent_unchanged"]:
                raise RuntimeError("temporary_qa_parent_changed")
        state["phase"] = ("finished" if report.get("temporary_qa_child_deleted")
                          else "quarantined")
        _journal(journal_path, state)
    if report.get("matrix_outcome") != "passed":
        raise RuntimeError("temporary_qa_matrix_failed")
    if not all(report.get(key) is True for key in (
            "temporary_qa_token_revoked", "temporary_qa_revocation_http_401",
            "temporary_qa_pre_revocation_http_200",
            "temporary_qa_child_deleted", "temporary_qa_parent_unchanged")):
        raise RuntimeError("temporary_qa_cleanup_unverified")
    return {"matrix_passed": True, "cleanup_verified": True}


def cleanup_quarantined(run_label: str) -> dict[str, bool]:
    """QA-only recovery after independent diagnosis, under the same host lock."""
    match = re.fullmatch(r"cleanup-(qa-[0-9]+-[0-9]+-[0-9a-f]{8}-[0-9a-f]{8})",
                         run_label)
    parent_raw = os.getenv("FINN_QA_USER_ID", "")
    if (match is None or not parent_raw.isdecimal() or int(parent_raw) <= 0
            or os.getenv("FINN_QA_ALLOW_FIXTURE_ACTIONS") != "1"
            or os.getenv("FINN_QA_ALLOW_FIXTURE_EXECUTION") == "1"):
        raise RuntimeError("temporary_qa_cleanup_not_authorized")
    try:
        os.fstat(9)
    except OSError as error:
        raise RuntimeError("temporary_qa_host_lock_missing") from error
    parent = int(parent_raw)
    namespace = match.group(1)

    async def parent_hash() -> str:
        async with async_session_factory() as session:
            value = await _parent_state(session, parent)
            await session.rollback()
            return value

    before = _db(parent_hash())
    child = _db(_find_child(parent, namespace))
    if child is None:
        raise RuntimeError("temporary_qa_child_missing")
    _db(_revoke_child(child, namespace))
    if not _db(_child_quiescent(child)):
        raise RuntimeError("temporary_qa_child_not_quiescent")
    _db(_delete_child(child, namespace))
    if not _db(_parent_unchanged(parent, before)):
        raise RuntimeError("temporary_qa_parent_changed")
    return {"child_deleted": True, "parent_unchanged": True}
