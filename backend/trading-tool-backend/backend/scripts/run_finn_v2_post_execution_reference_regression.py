#!/usr/bin/env python3
"""Prove immediate demonstrative reads after confirmed FINN mutations.

The public route is deliberate: no client-side IDs, cached action-results, or
test resolver state may bridge the confirmation-to-next-turn boundary.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse
import uuid

from sqlalchemy import text

from backend.infrastructure.database import sync_engine
from backend.scripts.run_finn_v2_full_action_matrix import _create_local_user, _runtime_record
from backend.scripts.run_finn_v2_persisted_runtime_gate import run_gate
from backend.scripts.run_finn_v2_sequential_action_chain import _run_action
from backend.utils.auth_utils import create_access_token


def _reference_read(
    *, base_url: str, token: str, conversation_id: str, message: str,
    entity_type: str, expected_id: str, expected_operation_id: str,
) -> dict:
    observed = run_gate(
        base_url=base_url,
        bearer_token=token,
        conversation_id=conversation_id,
        message=message,
        timeout_seconds=45,
    )
    record = _runtime_record(observed["run_id"])
    projection = dict(record["terminal_projection"] or {})
    supplied = dict(projection.get("supplied_inputs") or {})
    target = dict((record.get("runtime_state") or {}).get("canonical_entity_target") or {})
    resolved_id = target.get("entity_id")
    return {
        "message": message,
        "run_id": observed["run_id"],
        "operation_id": observed["final_operation_id"],
        "terminal_status": observed["status"],
        "runtime_contract_id": record["runtime_contract_id"],
        "supplied_inputs": supplied,
        "canonical_entity_target": target,
        "polling_sse_parity": observed["polling_sse_contract_projection"],
        "expected_entity_id": str(expected_id),
        "resolved_entity_id": str(resolved_id) if resolved_id is not None else None,
        "passed": all((
            observed["status"] == "completed",
            observed["final_operation_id"] == expected_operation_id,
            target.get("entity_type") == entity_type,
            str(resolved_id) == str(expected_id),
            bool(record["runtime_contract_id"]),
            observed["polling_sse_contract_projection"],
        )),
    }


def _verified_conversation_projection(conversation_id: str) -> dict:
    with sync_engine.connect() as connection:
        row = connection.execute(
            text("""
                SELECT
                    context_json -> 'verified_action_result' AS action_result,
                    context_json -> 'active_conversation_target' AS active_target,
                    context_json ->> 'verified_action_result_revision' AS revision
                FROM finn_v2_conversations
                WHERE id = :conversation_id
            """),
            {"conversation_id": conversation_id},
        ).mappings().one_or_none()
    return dict(row or {})


def _execution_conversation(step: dict) -> str:
    """Use only the public execute response for the next browser-like turn."""
    conversation_id = str((step.get("proposal_lifecycle") or {}).get("execution_conversation_id") or "")
    if not conversation_id:
        raise AssertionError("post_execution_reference_missing_public_execution_conversation_id")
    return conversation_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:18001")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    base_url = args.base_url.rstrip("/")
    if urlparse(base_url).hostname not in {"127.0.0.1", "localhost"}:
        raise ValueError("post_execution_reference_regression_requires_loopback_base_url")

    primary = _create_local_user()
    other = _create_local_user()
    token = create_access_token({"sub": str(primary["id"]), "role": "user"})
    other_token = create_access_token({"sub": str(other["id"]), "role": "user"})
    suffix = uuid.uuid4().hex[:8]
    setup_name = f"Reference Setup {suffix}"
    strategy_name = f"Reference Strategy {suffix}"

    create_setup = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        message=f"Maak een trade setup voor BTC op 4H met de naam {setup_name}.",
        operation_id="create_setup",
    )
    # The frontend receives this identity from the public execute endpoint.
    # Never fall back to the pre-confirmation run response in this regression.
    conversation_id = _execution_conversation(create_setup)
    update_setup = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        conversation_id=conversation_id,
        message="Wijzig deze setup naar timeframe 1D.",
        operation_id="update_setup",
    )
    # The browser regression occurs after the confirmation boundary: a second
    # natural ``deze setup`` mutation must resolve the action result that the
    # first update just persisted, without a name or client-side ID.
    update_setup_again = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        conversation_id=_execution_conversation(update_setup),
        message="Wijzig deze setup terug naar timeframe 4H.",
        operation_id="update_setup",
    )
    # A restored browser session can legitimately begin a fresh V2
    # conversation. The wording stays demonstrative, so only the latest
    # persisted, owner-scoped action result may supply its target.
    update_setup_after_boundary = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        message="Wijzig deze setup naar timeframe 1D.",
        operation_id="update_setup",
    )
    # This deliberately began a fresh conversation to prove persisted
    # owner-scoped lineage. From here on, model the browser exactly: bind the
    # next turn to the conversation returned by that public execution.
    conversation_id = _execution_conversation(update_setup_after_boundary)
    setup_read = _reference_read(
        base_url=base_url,
        token=token,
        conversation_id=_execution_conversation(update_setup_again),
        message="Welk timeframe gebruikt deze setup nu?",
        entity_type="setup",
        expected_id=str((update_setup_after_boundary.get("action_result") or {}).get("entity_id") or ""),
        expected_operation_id="read_active_setup",
    )
    create_strategy = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        conversation_id=_execution_conversation(update_setup_after_boundary),
        message=(
            f"Maak voor deze setup een vaste strategie met de naam {strategy_name}, "
            "100 euro per uitvoering, entry 76000, stop-loss 72000, "
            "targets 83000 en 87000 en gebalanceerd risico."
        ),
        operation_id="create_strategy",
    )
    update_strategy = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        conversation_id=_execution_conversation(create_strategy),
        message="Wijzig deze strategie en zet het bedrag naar 150 euro.",
        operation_id="update_strategy",
    )
    # Exercise the corresponding post-confirmation Strategy reference. This
    # cannot be replaced by a passive read: the resolver must produce the ID
    # required by the next write action itself.
    update_strategy_again = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        conversation_id=_execution_conversation(update_strategy),
        message="Wijzig deze strategie en zet het bedrag terug naar 100 euro.",
        operation_id="update_strategy",
    )
    update_strategy_after_boundary = _run_action(
        base_url=base_url,
        token=token,
        other_token=other_token,
        message="Wijzig deze strategie en zet het bedrag naar 125 euro.",
        operation_id="update_strategy",
    )
    strategy_read = _reference_read(
        base_url=base_url,
        token=token,
        conversation_id=_execution_conversation(update_strategy_again),
        message="Vat deze strategie samen.",
        entity_type="strategy",
        expected_id=str((update_strategy_after_boundary.get("action_result") or {}).get("entity_id") or ""),
        expected_operation_id="read_linked_strategy",
    )
    conversation_id = _execution_conversation(update_strategy_after_boundary)
    conversation_projection = _verified_conversation_projection(conversation_id)
    projection_result = dict(conversation_projection.get("action_result") or {})
    projection_target = dict(conversation_projection.get("active_target") or {})
    steps = [
        create_setup,
        update_setup,
        update_setup_again,
        update_setup_after_boundary,
        setup_read,
        create_strategy,
        update_strategy,
        update_strategy_again,
        update_strategy_after_boundary,
        strategy_read,
    ]
    artifact = {
        "artifact_version": "finn_v2.post_execution_reference_regression.v1",
        "synthetic_local_user": True,
        "conversation_id": conversation_id,
        "steps": steps,
        "verified_conversation_projection": conversation_projection,
        "passed": all(step.get("passed") for step in steps) and all((
            projection_result.get("operation_id") == "update_strategy",
            projection_result.get("entity_id") == (update_strategy_after_boundary.get("action_result") or {}).get("entity_id"),
            projection_target.get("entity_type") == "strategy",
            projection_target.get("entity_id") == (update_strategy_after_boundary.get("action_result") or {}).get("entity_id"),
        )),
    }
    output = Path(args.output).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(payload, encoding="utf-8")
    temporary.replace(output)
    print(json.dumps({
        "passed": artifact["passed"],
        "output": str(output),
        "sha256": hashlib.sha256(payload.encode()).hexdigest(),
    }, sort_keys=True))
    if not artifact["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
