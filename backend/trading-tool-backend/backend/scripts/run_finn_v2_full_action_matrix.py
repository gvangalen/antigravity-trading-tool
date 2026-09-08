#!/usr/bin/env python3
"""Run every safe FINN V2 action contract through the local public runtime.

This is intentionally an integration harness, not a fixture-proposal test:
every proposal must originate from a persisted V2 run dispatched to the local
Celery worker.  Fixtures contain only synthetic users and domain objects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
import uuid

from sqlalchemy import text

from backend.domain.finn_v2_operation_registry import FinnV2OperationRegistry
from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, run_gate
from backend.utils.auth_utils import create_access_token


ACTION_SPECS = (
    ("select_asset", "Selecteer SOL als mijn actieve asset.", "Stel mijn actieve asset in.", "SOL."),
    ("watchlist_add", "Voeg ETH toe aan mijn watchlist.", "Voeg een asset toe aan mijn watchlist.", "ETH."),
    ("watchlist_remove", "Verwijder XRP uit mijn watchlist.", "Verwijder een asset uit mijn watchlist.", "XRP."),
    ("create_indicator_configuration", "Maak een technische RSI indicatorconfiguratie voor ADA.", "Maak een technische RSI indicatorconfiguratie.", "Voor ADA."),
    ("update_indicator_configuration", "Werk mijn technische RSI indicatorconfiguratie voor BTC bij en zet de periode naar 21.", "Pas mijn technische RSI indicatorconfiguratie aan.", "Voor BTC en zet de periode naar 21."),
    ("delete_indicator_configuration", "Verwijder mijn technische RSI indicatorconfiguratie voor SOL.", "Verwijder mijn technische RSI indicatorconfiguratie.", "Voor SOL."),
    ("create_setup", "Maak een swing setup voor SOL op 4 uur met de naam Matrix Nieuwe Setup.", "Maak een swing setup voor SOL.", "Op 4 uur met de naam Matrix Nieuwe Setup."),
    ("update_setup", "Werk Matrix Update Setup bij en zet het tijdframe naar 1 uur.", "Werk een setup bij.", "Werk Matrix Update Setup bij en zet het tijdframe naar 1 uur."),
    ("delete_setup", "Verwijder de setup Matrix Delete Setup.", "Verwijder een setup.", "Verwijder de setup Matrix Delete Setup."),
    ("create_strategy", "Maak een fixed strategie voor Matrix Strategy Parent met een basisinleg van 100 euro en de naam Matrix Nieuwe Strategie.", "Maak een strategie.", "Maak een fixed strategie voor Matrix Strategy Parent met een basisinleg van 100 euro en de naam Matrix Nieuwe Strategie."),
    ("update_strategy", "Werk Matrix Update Strategie bij en zet de basisinleg naar 120 euro.", "Werk een strategie bij.", "Werk Matrix Update Strategie bij en zet de basisinleg naar 120 euro."),
    ("delete_strategy", "Verwijder de strategie Matrix Delete Strategie.", "Verwijder een strategie.", "Verwijder de strategie Matrix Delete Strategie."),
    ("create_bot", "Maak een paper bot voor Matrix Bot Parent met de naam Matrix Nieuwe Bot.", "Maak een bot.", "Maak een paper bot voor Matrix Bot Parent met de naam Matrix Nieuwe Bot."),
    ("update_bot", "Werk Matrix Update Bot bij en zet de cadence naar weekly.", "Werk een bot bij.", "Werk Matrix Update Bot bij en zet de cadence naar weekly."),
    ("delete_bot", "Verwijder de bot Matrix Delete Bot.", "Verwijder een bot.", "Verwijder de bot Matrix Delete Bot."),
    ("deactivate_bot", "Deactiveer de bot Matrix Deactivate Bot.", "Deactiveer een bot.", "Deactiveer de bot Matrix Deactivate Bot."),
)


def _create_local_user() -> dict[str, Any]:
    """Create a non-login synthetic user without consuming HTTP auth limits."""
    with sync_engine.begin() as connection:
        user_id = connection.execute(text("""
            INSERT INTO users (email, password_hash, role, is_active, first_name, last_name,
                               subscription_status, created_at, ai_plan, ai_requests_limit_day,
                               ai_requests_used_day, ai_preferences)
            VALUES (:email, 'local-fixture-not-for-login', 'user', TRUE, 'FINN', 'Matrix',
                    'active', NOW(), 'basis', 500, 0, CAST(:preferences AS jsonb))
            RETURNING id
        """), {"email": f"finn.local.matrix.{uuid.uuid4().hex[:16]}@example.com",
                "preferences": json.dumps({"selected_asset": "BTC", "locale": "nl"})}).scalar_one()
    return {"id": int(user_id), "role": "user"}


def _insert_setup(
    connection,
    user_id: int,
    name: str,
    symbol: str = "BTC",
    *,
    setup_type: str = "trade",
) -> int:
    return int(connection.execute(text("""
        INSERT INTO setups (user_id, name, symbol, timeframe, setup_type, created_at)
        VALUES (:user_id, :name, :symbol, '4H', :setup_type, NOW()) RETURNING id
    """), {"user_id": user_id, "name": name, "symbol": symbol, "setup_type": setup_type}).scalar_one())


def _insert_strategy(connection, user_id: int, setup_id: int, name: str) -> int:
    return int(connection.execute(text("""
        INSERT INTO strategies (user_id, setup_id, name, setup_type, execution_mode,
                                base_amount, entry, targets, stop_loss, data, created_at)
        VALUES (:user_id, :setup_id, :name, 'trade', 'fixed', 100, 100,
                ARRAY['120']::TEXT[], 90,
                CAST(:data AS jsonb), NOW()) RETURNING id
    """), {"user_id": user_id, "setup_id": setup_id, "name": name,
            "data": json.dumps({
                "name": name, "execution_mode": "fixed", "base_amount": 100,
                "entry": 100, "targets": ["120"], "stop_loss": 90,
            })}).scalar_one())


def _insert_bot(connection, user_id: int, strategy_id: int, name: str) -> int:
    return int(connection.execute(text("""
        INSERT INTO bot_configs (user_id, name, strategy_id, mode, is_live, is_active,
                                 risk_profile, cadence, budget_total_eur,
                                 budget_daily_limit_eur, budget_min_order_eur,
                                 budget_max_order_eur, max_asset_exposure_pct,
                                 base_currency, symbol, created_at, updated_at)
        VALUES (:user_id, :name, :strategy_id, 'manual', FALSE, TRUE, 'balanced',
                'daily', 100, 50, 10, 50, 100, 'EUR', 'BTC', NOW(), NOW()) RETURNING id
    """), {"user_id": user_id, "strategy_id": strategy_id, "name": name}).scalar_one())


def _seed_fixtures(user_id: int) -> dict[str, int]:
    """Create independent local objects so mutation cases never share state."""
    with sync_engine.begin() as connection:
        connection.execute(text("""
            UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id
        """), {"user_id": user_id, "preferences": json.dumps({"selected_asset": "BTC"})})
        connection.execute(text("""
            INSERT INTO asset_catalog (symbol, display_name, asset_class, provider, content_hash, payload_json)
            VALUES ('BTC', 'Bitcoin', 'crypto', 'local_fixture', 'matrix-btc-v1', CAST(:payload AS jsonb))
            ON CONFLICT (symbol) DO NOTHING
        """), {"payload": json.dumps({"fixture": "local_action_matrix"})})
        connection.execute(text("""
            INSERT INTO watchlists (user_id, symbol, created_at) VALUES (:user_id, 'XRP', NOW())
            ON CONFLICT (user_id, symbol) DO NOTHING
        """), {"user_id": user_id})
        for symbol in ("BTC", "SOL"):
            connection.execute(text("""
                INSERT INTO user_indicator_configs
                    (user_id, indicator, category, symbol, asset_class, priority, enabled,
                     config_json, provenance, created_at, updated_at)
                VALUES (:user_id, 'rsi', 'technical', :symbol, 'crypto', 100, TRUE,
                        CAST(:config AS jsonb), 'local_action_matrix', NOW(), NOW())
            """), {"user_id": user_id, "symbol": symbol,
                    "config": json.dumps({"period": 14, "source": "close"})})
        fixtures = {
            "setup_update": _insert_setup(connection, user_id, "Matrix Update Setup"),
            "setup_delete": _insert_setup(connection, user_id, "Matrix Delete Setup"),
            # The existing create_strategy action contract requires only a
            # setup, execution mode and base amount. A DCA parent is the
            # supported minimal path; trade setups intentionally require
            # additional risk fields in StrategyService.
            "strategy_parent_setup": _insert_setup(connection, user_id, "Matrix Strategy Parent", setup_type="dca"),
            "strategy_update_setup": _insert_setup(connection, user_id, "Matrix Strategy Update Parent"),
            "strategy_delete_setup": _insert_setup(connection, user_id, "Matrix Strategy Delete Parent"),
            "bot_create_setup": _insert_setup(connection, user_id, "Matrix Bot Create Parent"),
            "bot_update_setup": _insert_setup(connection, user_id, "Matrix Bot Update Parent"),
            "bot_delete_setup": _insert_setup(connection, user_id, "Matrix Bot Delete Parent"),
            "bot_deactivate_setup": _insert_setup(connection, user_id, "Matrix Bot Deactivate Parent"),
        }
        fixtures["strategy_update"] = _insert_strategy(connection, user_id, fixtures["strategy_update_setup"], "Matrix Update Strategie")
        fixtures["strategy_delete"] = _insert_strategy(connection, user_id, fixtures["strategy_delete_setup"], "Matrix Delete Strategie")
        fixtures["bot_create_strategy"] = _insert_strategy(connection, user_id, fixtures["bot_create_setup"], "Matrix Bot Parent")
        bot_update_strategy = _insert_strategy(connection, user_id, fixtures["bot_update_setup"], "Matrix Update Bot Strategie")
        bot_delete_strategy = _insert_strategy(connection, user_id, fixtures["bot_delete_setup"], "Matrix Delete Bot Strategie")
        bot_deactivate_strategy = _insert_strategy(connection, user_id, fixtures["bot_deactivate_setup"], "Matrix Deactivate Bot Strategie")
        fixtures["bot_update"] = _insert_bot(connection, user_id, bot_update_strategy, "Matrix Update Bot")
        fixtures["bot_delete"] = _insert_bot(connection, user_id, bot_delete_strategy, "Matrix Delete Bot")
        fixtures["bot_deactivate"] = _insert_bot(connection, user_id, bot_deactivate_strategy, "Matrix Deactivate Bot")
    return fixtures


def _fixture_provenance(fields: dict[str, int]) -> list[dict[str, object]]:
    """Expose synthetic preconditions without supplying them to FINN input."""
    kinds = {
        "setup": "setup", "strategy": "strategy", "bot": "bot",
    }
    return [
        {
            "fixture_key": key,
            "fixture_type": next((kind for prefix, kind in kinds.items() if prefix in key), "other"),
            "fixture_id": value,
            "creation_source": "explicit_local_fixture_before_measured_turn",
        }
        for key, value in sorted(fields.items())
    ]


def _runtime_record(run_id: str) -> dict[str, Any]:
    with sync_engine.connect() as connection:
        contract = connection.execute(text("""
            SELECT contract_id, revision, state_json, terminal_projection_json
            FROM finn_v2_runtime_contracts WHERE run_id = :run_id
        """), {"run_id": run_id}).mappings().one_or_none()
        proposal = connection.execute(text("""
            SELECT id, status, operation_type, target_type, target_id, asset, payload_hash
            FROM finn_v2_proposals WHERE run_id = :run_id ORDER BY created_at DESC LIMIT 1
        """), {"run_id": run_id}).mappings().one_or_none()
    projection = dict((contract or {}).get("terminal_projection_json") or {})
    state = dict((contract or {}).get("state_json") or {})
    return {
        "runtime_contract_id": (contract or {}).get("contract_id"),
        "runtime_contract_revision": (contract or {}).get("revision"),
        "runtime_state": state,
        "terminal_projection": projection,
        "proposal": dict(proposal) if proposal else None,
    }


def _proposal_lifecycle(base_url: str, token: str, other_token: str, proposal: dict[str, Any]) -> dict[str, Any]:
    proposal_id = str(proposal["id"])
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    other_headers = {"Authorization": f"Bearer {other_token}", "Content-Type": "application/json"}
    _, cross_user_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}", method="GET",
        headers=other_headers, body=None, timeout=10,
    )
    published, publish_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/publish", method="POST",
        headers=headers, body={}, timeout=10,
    )
    confirmation_token = str(published.get("confirmation_token") or "")
    confirmation_payload = {
        "idempotency_key": f"local-confirm-{uuid.uuid4().hex}",
        "confirmation_token": confirmation_token,
        "expected_payload_hash": proposal["payload_hash"],
    }
    confirmed, confirmation_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/confirm", method="POST",
        headers=headers, body=confirmation_payload, timeout=10,
    )
    execution_payload = {
        "idempotency_key": f"local-execute-{uuid.uuid4().hex}",
        "expected_payload_hash": proposal["payload_hash"],
    }
    executed, execution_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/execute", method="POST",
        headers=headers, body=execution_payload, timeout=20,
    )
    replayed, replay_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/execute", method="POST",
        headers=headers, body=execution_payload, timeout=20,
    )
    return {
        "cross_user_rejected": cross_user_status in {403, 404},
        "publish_status": publish_status,
        "confirmation_status": confirmation_status,
        "confirmed": bool(confirmed.get("confirmed")),
        "execution_status": execution_status,
        "execution_result": executed.get("status"),
        "idempotency_replay_status": replay_status,
        "idempotency_result": replayed.get("status"),
    }


def _run_follow_up(base_url: str, token: str, spec: tuple[str, str, str, str], fields: dict[str, int]) -> dict[str, Any]:
    operation_id, _, incomplete, follow_up = spec
    first = run_gate(base_url=base_url, bearer_token=token, message=incomplete.format(**fields), timeout_seconds=75)
    second = run_gate(base_url=base_url, bearer_token=token, conversation_id=first["conversation_id"], message=follow_up.format(**fields), timeout_seconds=75)
    first_record = _runtime_record(first["run_id"])
    second_record = _runtime_record(second["run_id"])
    return {
        "initial_run_id": first["run_id"],
        "follow_up_run_id": second["run_id"],
        "initial_operation_id": first["final_operation_id"],
        "initial_missing_inputs": first_record["terminal_projection"].get("missing_inputs"),
        "follow_up_supplied_inputs": second_record["terminal_projection"].get("supplied_inputs"),
        "follow_up_missing_inputs": second_record["terminal_projection"].get("missing_inputs"),
        "follow_up_operation_id": second["final_operation_id"],
        "conversation_reused": first["conversation_id"] == second["conversation_id"],
        "proposal_after_follow_up": bool(second_record["proposal"]),
        "passed": (
            first["final_operation_id"] in {operation_id, "clarify_request"}
            and second["final_operation_id"] == operation_id
            and first["conversation_id"] == second["conversation_id"]
            and not second_record["terminal_projection"].get("missing_inputs")
            and bool(second_record["proposal"])
        ),
    }


def _run_contract(base_url: str, spec: tuple[str, str, str, str]) -> dict[str, Any]:
    operation_id, complete, _, _ = spec
    primary = _create_local_user()
    other = _create_local_user()
    follow_up_user = _create_local_user()
    user_id = int(primary["id"])
    fields = _seed_fixtures(user_id)
    token = create_access_token({"sub": str(user_id), "role": str(primary.get("role") or "user")})
    other_token = create_access_token({"sub": str(other["id"]), "role": str(other.get("role") or "user")})
    # The primary path deliberately executes once. The incomplete-flow path
    # must prove slot continuation, not attempt the same mutation after that
    # execution, so it receives a separate synthetic user and fresh objects.
    follow_up_fields = _seed_fixtures(int(follow_up_user["id"]))
    follow_up_token = create_access_token(
        {"sub": str(follow_up_user["id"]), "role": str(follow_up_user.get("role") or "user")}
    )
    contract = FinnV2OperationRegistry().require_supported(operation_id)
    message = complete.format(**fields)
    result: dict[str, Any] = {
        "operation_id": operation_id,
        "testcase": f"local_action_{operation_id}",
        "safe_input_description": message,
        "expected_contract_outcome": "proposal_confirmation_safe_execution_idempotent_replay",
        "required_inputs": list(contract.required_inputs),
        "action_polarity": contract.action_polarity.value,
        "status": "FAIL",
        "fixture_objects": _fixture_provenance(fields),
    }
    try:
        observed = run_gate(base_url=base_url, bearer_token=token, message=message, timeout_seconds=75)
        record = _runtime_record(observed["run_id"])
        projection = record["terminal_projection"]
        proposal = record["proposal"]
        result.update({
            "run_id": observed["run_id"],
            "selector_result": {"initial_operation_id": observed["initial_operation_id"], "final_operation_id": observed["final_operation_id"]},
            "supplied_inputs": projection.get("supplied_inputs"),
            "missing_inputs": projection.get("missing_inputs"),
            "resolved_entity": {
                "canonical_target": projection.get("canonical_target"),
                "target_source": projection.get("target_source"),
                "resolved_ids": {
                    key: value for key, value in dict(projection.get("supplied_inputs") or {}).items()
                    if key.endswith("_id")
                },
                "resolution_source": "owner_scoped_message_reference" if any(
                    key.endswith("_id") for key in dict(projection.get("supplied_inputs") or {})
                ) else None,
            },
            "runtime_contract_id": record["runtime_contract_id"],
            "runtime_contract_revision": record["runtime_contract_revision"],
            "dispatch_count": projection.get("dispatch_count"),
            "attempt_count": projection.get("attempt_count"),
            "proposal_id": proposal.get("id") if proposal else None,
            "proposal_status": proposal.get("status") if proposal else None,
            "terminal_status": observed["status"],
            "terminal_reason": projection.get("terminal_reason"),
            "polling_sse_parity": observed["polling_sse_contract_projection"],
            "elapsed_ms": observed["elapsed_ms"],
        })
        if proposal:
            lifecycle = _proposal_lifecycle(base_url, token, other_token, proposal)
            result.update(lifecycle)
        follow_up = _run_follow_up(base_url, follow_up_token, spec, follow_up_fields)
        result["incomplete_follow_up"] = follow_up
        required = set(contract.required_inputs)
        supplied = set(result.get("supplied_inputs") or {})
        lifecycle_ok = bool(proposal) and result.get("confirmed") and result.get("execution_result") == "succeeded" and result.get("idempotency_result") == "already_executed"
        result["status"] = "PASS" if all((
            observed["initial_operation_id"] == operation_id,
            observed["final_operation_id"] == operation_id,
            required.issubset(supplied),
            not result.get("missing_inputs"),
            bool(record["runtime_contract_id"]),
            result.get("dispatch_count") == 1,
            result.get("attempt_count") == 1,
            observed["polling_sse_contract_projection"],
            lifecycle_ok,
            # Only create_strategy requires a multi-turn slot-collection
            # proof in this action matrix. Other actions are fully proven by
            # their natural first turn plus proposal/confirmation/execution;
            # their follow-up is retained as diagnostic evidence and must not
            # turn an already-completed action into a false matrix failure.
            (operation_id != "create_strategy" or follow_up["passed"]),
        )) else "FAIL"
    except Exception as exc:  # Preserve all cases in the artifact instead of failing fast.
        result["error"] = f"{type(exc).__name__}:{exc}"
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("local_action_matrix_requires_loopback_base_url")
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    def write_artifact(results: list[dict[str, Any]], *, complete: bool) -> dict[str, Any]:
        with sync_engine.connect() as connection:
            live_bots = int(connection.execute(text("SELECT count(*) FROM bot_configs WHERE is_live IS TRUE")).scalar() or 0)
        artifact = {
        "artifact_version": "finn_v2.local_action_matrix.v1",
        "complete": complete,
        "synthetic_local_only": True,
        "production_connections": 0,
        "broker_orders": 0,
        "live_trading_calls": 0,
        "live_bot_count": live_bots,
        "contracts_total": len(ACTION_SPECS),
        "contracts_passed": sum(item["status"] == "PASS" for item in results),
        "contracts_failed": sum(item["status"] != "PASS" for item in results),
        "results": results,
        }
        output.write_text(json.dumps(artifact, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return artifact

    results: list[dict[str, Any]] = []
    for spec in ACTION_SPECS:
        results.append(_run_contract(base_url, spec))
        write_artifact(results, complete=False)
    artifact = write_artifact(results, complete=True)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    print(json.dumps({"output": str(output), "sha256": digest, "passed": artifact["contracts_passed"], "total": len(results)}, sort_keys=True))
    if artifact["contracts_failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
