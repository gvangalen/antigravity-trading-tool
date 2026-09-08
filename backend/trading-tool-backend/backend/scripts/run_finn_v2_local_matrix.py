#!/usr/bin/env python3
"""Run a non-production FINN V2 matrix through the public local gateway.

The runner creates only synthetic fixture users in the local database. It never
contacts production, reads production credentials, or confirms live actions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_persisted_runtime_gate import _request_json, run_gate
from backend.utils.auth_utils import create_access_token


CASES = (
    ("capability", "Wat kun je voor mij doen?", "capability", {"completed"}),
    ("concept", "Wat betekent RSI?", "explain_financial_concept", {"completed"}),
    ("off_topic", "Schrijf een gedicht over de zee.", "off_topic", {"unavailable"}),
    ("read_active_asset", "Welke asset is actief?", "read_active_asset", {"completed"}),
    ("indicator_configuration", "Welke indicatoren staan voor BTC ingesteld?", "read_indicator_configuration", {"completed"}),
)


def _post(url: str, payload: dict) -> dict:
    request = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode())


def _seed_fixture(user_id: int) -> None:
    """Seed only the synthetic user's local FINN context.

    These rows never leave the local PostgreSQL container and are deliberately
    limited to read context. Action cases create their own isolated records.
    """
    preferences = json.dumps({"selected_asset": "BTC", "risk_profile": "balanced"})
    indicator_config = json.dumps({"period": 14, "source": "close"})
    with sync_engine.begin() as connection:
        connection.execute(
            text("UPDATE users SET ai_preferences = CAST(:preferences AS jsonb) WHERE id = :user_id"),
            {"preferences": preferences, "user_id": user_id},
        )
        connection.execute(
            text("INSERT INTO watchlists (user_id, symbol, created_at) VALUES (:user_id, 'BTC', NOW())"),
            {"user_id": user_id},
        )
        connection.execute(
            text(
                """
                INSERT INTO user_indicator_configs
                    (user_id, indicator, category, symbol, asset_class, priority, enabled, config_json, provenance, created_at, updated_at)
                VALUES
                    (:user_id, 'rsi', 'technical', 'BTC', 'crypto', 100, TRUE, CAST(:config AS jsonb), 'local_fixture', NOW(), NOW())
                """
            ),
            {"user_id": user_id, "config": indicator_config},
        )
        connection.execute(
            text(
                """
                INSERT INTO asset_catalog (symbol, display_name, asset_class, provider, content_hash, payload_json)
                VALUES ('BTC', 'Bitcoin', 'crypto', 'local_fixture', 'local-fixture-btc-v1', CAST(:payload AS jsonb))
                ON CONFLICT (symbol) DO NOTHING
                """
            ),
            {"payload": json.dumps({"symbol": "BTC", "fixture": True})},
        )


def _seed_safe_watchlist_proposal(user_id: int) -> tuple[str, str]:
    """Create only local provenance for one non-financial contract exercise."""
    with sync_engine.begin() as connection:
        source = connection.execute(
            text(
                """
                SELECT r.id AS run_id, s.id AS snapshot_id, s.evidence_set_hash,
                       v.id AS validation_id, o.id AS orchestrator_id
                FROM finn_v2_runs r
                JOIN finn_v2_state_snapshots s ON s.run_id = r.id
                JOIN finn_v2_validation_results v ON v.run_id = r.id
                JOIN finn_v2_orchestrator_results o ON o.run_id = r.id
                WHERE r.user_id = :user_id AND r.status = 'completed'
                ORDER BY r.created_at DESC
                LIMIT 1
                """
            ),
            {"user_id": user_id},
        ).mappings().one()
        proposal_id = f"local-finn-proposal-{uuid.uuid4().hex}"
        policy_id = f"local-finn-policy-{uuid.uuid4().hex}"
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=5)
        payload = {
            "operation_type": "watchlist_add",
            "target": {"target_type": "watchlist", "target_id": None, "asset": "ETH"},
            "change": {"asset": "ETH", "operation": "add"},
            "source_run_id": source["run_id"],
            "source_snapshot_id": source["snapshot_id"],
            "source_validation_id": source["validation_id"],
            "evidence_set_hash": source["evidence_set_hash"],
            "idempotency_key": f"local-finn-proposal-{uuid.uuid4().hex}",
            "expires_at": expires_at.isoformat(),
        }
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        connection.execute(
            text(
                """
                INSERT INTO finn_v2_policy_decisions
                    (id, run_id, user_id, orchestrator_result_id, snapshot_id, validation_id,
                     policy_class, operation_type, allowed, proposal_allowed,
                     confirmation_required, step_up_required, execution_allowed, shadow_safe,
                     evidence_set_hash, decision_json, policy_version)
                VALUES
                    (:id, :run_id, :user_id, :orchestrator_id, :snapshot_id, :validation_id,
                     'local_fixture', 'watchlist_add', TRUE, TRUE,
                     TRUE, FALSE, TRUE, TRUE, :evidence_set_hash,
                     CAST(:decision AS jsonb), 'local-fixture-v1')
                """
            ),
            {
                "id": policy_id, "run_id": source["run_id"], "user_id": user_id,
                "orchestrator_id": source["orchestrator_id"], "snapshot_id": source["snapshot_id"],
                "validation_id": source["validation_id"], "evidence_set_hash": source["evidence_set_hash"],
                "decision": json.dumps({"fixture": "local_non_financial"}),
            },
        )
        connection.execute(
            text(
                """
                INSERT INTO finn_v2_proposals
                    (id, run_id, user_id, policy_decision_id, status, operation_type,
                     target_type, target_id, asset, payload_json, payload_hash,
                     evidence_set_hash, idempotency_key, requires_step_up_auth, expires_at)
                VALUES
                    (:id, :run_id, :user_id, :policy_id, 'draft', 'watchlist_add',
                     'watchlist', NULL, 'ETH', CAST(:payload AS jsonb), :payload_hash,
                     :evidence_set_hash, :idempotency_key, FALSE, :expires_at)
                """
            ),
            {
                "id": proposal_id, "run_id": source["run_id"], "user_id": user_id,
                "policy_id": policy_id, "payload": payload_json, "payload_hash": payload_hash,
                "evidence_set_hash": source["evidence_set_hash"],
                "idempotency_key": payload["idempotency_key"], "expires_at": expires_at,
            },
        )
    return proposal_id, payload_hash


def _exercise_safe_execution(*, base_url: str, token: str, user_id: int) -> dict:
    proposal_id, payload_hash = _seed_safe_watchlist_proposal(user_id)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    published, publish_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/publish",
        method="POST", headers=headers, body={}, timeout=10,
    )
    confirmation_token = str(published.get("confirmation_token") or "")
    confirm_payload = {
        "idempotency_key": f"local-finn-confirm-{uuid.uuid4().hex}",
        "confirmation_token": confirmation_token,
        "expected_payload_hash": payload_hash,
    }
    confirmed, confirm_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/confirm",
        method="POST", headers=headers, body=confirm_payload, timeout=10,
    )
    confirmation_token = ""
    execute_payload = {
        "idempotency_key": f"local-finn-execute-{uuid.uuid4().hex}",
        "expected_payload_hash": payload_hash,
    }
    executed, execute_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/execute",
        method="POST", headers=headers, body=execute_payload, timeout=10,
    )
    replayed, replay_status = _request_json(
        url=f"{base_url}/api/assistant/v2/proposals/{proposal_id}/execute",
        method="POST", headers=headers, body=execute_payload, timeout=10,
    )
    return {
        "operation_id": "watchlist_add",
        "proposal_created": publish_status == 200,
        "confirmation_succeeded": confirm_status == 200 and bool(confirmed.get("confirmed")),
        "execution_succeeded": execute_status == 200 and executed.get("status") == "succeeded",
        "idempotency_replay": replay_status == 200 and replayed.get("status") == "already_executed",
        "live_trading_calls": 0,
        "live_bot_activation_calls": 0,
    }


def _proposal_projection_for_run(run_id: str) -> dict:
    with sync_engine.connect() as connection:
        row = connection.execute(
            text(
                """
                SELECT terminal_projection_json->'proposal_lifecycle' AS lifecycle,
                       (SELECT count(*) FROM finn_v2_proposals WHERE run_id = :run_id) AS proposal_count
                FROM finn_v2_runtime_contracts
                WHERE run_id = :run_id
                """
            ),
            {"run_id": run_id},
        ).mappings().one()
    lifecycle = dict(row["lifecycle"] or {})
    return {
        "proposal_persisted": int(row["proposal_count"] or 0) == 1,
        "proposal_projection_status": lifecycle.get("status"),
        "proposal_projection_operation": lifecycle.get("operation_id"),
    }
def _exercise_guided_setup(*, base_url: str, token: str) -> dict:
    """Use three real conversation turns to prove typed setup-state continuity."""
    first = run_gate(
        base_url=base_url, bearer_token=token,
        message="Maak een swing setup voor BTC.", timeout_seconds=60.0,
    )
    conversation_id = first["conversation_id"]
    second = run_gate(
        base_url=base_url, bearer_token=token, conversation_id=conversation_id,
        message="4 uur", timeout_seconds=60.0,
    )
    third = run_gate(
        base_url=base_url, bearer_token=token, conversation_id=conversation_id,
        message="Noem deze BTC swing lokaal.", timeout_seconds=60.0,
    )
    proposal = _proposal_projection_for_run(third["run_id"])
    return {
        "conversation_reused": bool(conversation_id) and second["conversation_id"] == conversation_id and third["conversation_id"] == conversation_id,
        "initial_operation": first["initial_operation_id"],
        "continuation_operation": second["final_operation_id"],
        "proposal_operation": third["final_operation_id"],
        "guided_operation_preserved": all(
            item == "create_setup"
            for item in (first["initial_operation_id"], second["final_operation_id"], third["final_operation_id"])
        ),
        "terminal_status": third["status"],
        **proposal,
        "polling_sse_contract_projection": all(
            item["polling_sse_contract_projection"] for item in (first, second, third)
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    parser.add_argument("--case", choices=[item[0] for item in CASES])
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    email = f"finn.local.matrix.{uuid.uuid4().hex[:12]}@tradamind.com"
    user = _post(f"{base_url}/api/auth/register", {"first_name": "FINN", "last_name": "Local", "email": email, "password": "LocalFixtureOnly-123!", "locale": "nl"})
    user_id = int(user["id"])
    _seed_fixture(user_id)
    # Mint a normal short-lived token only in this local process. It is never
    # printed, persisted, or accepted outside the local JWT configuration.
    token = create_access_token({"sub": str(user_id), "role": str(user.get("role") or "user")})
    selected = [item for item in CASES if args.case is None or item[0] == args.case]
    results = []
    for case_id, message, expected_operation, expected_statuses in selected:
        observed = run_gate(
            base_url=base_url,
            bearer_token=token,
            message=message,
            timeout_seconds=60.0,
        )
        run_id = observed["run_id"]
        terminal, poll_status = _request_json(
            url=f"{base_url}/api/assistant/v2/runs/{run_id}",
            method="GET",
            headers={"Authorization": f"Bearer {token}"},
            body=None,
            timeout=2,
        )
        trace = dict(terminal.get("runtime_trace") or {})
        results.append({"case_id": case_id, "run_id": run_id, "run_id_present": bool(run_id), "http_status": poll_status, "status": terminal.get("status"), "expected_operation_id": expected_operation, "expected_terminal_statuses": sorted(expected_statuses), "actual_operation_id": trace.get("final_operation_id"), "operation_matches": expected_operation == trace.get("final_operation_id"), "terminal_status_matches": terminal.get("status") in expected_statuses, "dispatch_count": trace.get("dispatch_count"), "attempt_count": trace.get("attempt_count"), "supplied_inputs": trace.get("supplied_inputs"), "missing_inputs": trace.get("missing_inputs"), "terminal_reason": trace.get("terminal_reason"), "contract_id_present": bool(observed["contract_id"]), "polling_sse_contract_projection": observed["polling_sse_contract_projection"], "elapsed_ms": observed["elapsed_ms"]})
    safe_execution = _exercise_safe_execution(base_url=base_url, token=token, user_id=user_id)
    guided_setup = _exercise_guided_setup(base_url=base_url, token=token)
    passed = all(item["http_status"] == 200 and item["terminal_status_matches"] and item["operation_matches"] and item["dispatch_count"] == 1 and item["attempt_count"] == 1 and item["contract_id_present"] and item["polling_sse_contract_projection"] for item in results) and all(safe_execution[key] for key in ("proposal_created", "confirmation_succeeded", "execution_succeeded", "idempotency_replay")) and guided_setup["conversation_reused"] and guided_setup["guided_operation_preserved"] and guided_setup["proposal_persisted"] and guided_setup["proposal_projection_status"] == "draft" and guided_setup["proposal_projection_operation"] == "create_setup" and guided_setup["polling_sse_contract_projection"]
    print(json.dumps({"synthetic_user": True, "fixture_seeded": True, "user_id_present": bool(user_id), "cases": results, "safe_execution": safe_execution, "guided_setup": guided_setup, "passed": passed}, sort_keys=True))
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
