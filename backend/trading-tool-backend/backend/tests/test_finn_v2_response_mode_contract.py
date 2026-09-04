import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.domain.finn_v2_contract import FinnV2ModeContractError, INTERACTION_MODES, normalize_interaction_mode
from backend.services.finn_v2_delivery_service import FinnV2DeliveryService
from backend.services.finn_v2_run_service import FinnV2RunService


def _response_payload(mode: str) -> dict:
    return {
        "mode": mode,
        "content": "Een geverifieerd antwoord.",
        "response_source": "v2_runtime",
        "verifier_status": "passed",
        "evidence": [],
        "uncertainty": [],
        "proposal_id": None,
        "confirmation_required": False,
    }


def test_legacy_fact_normalizes_to_read_but_unknown_mode_is_typed_contract_error():
    assert normalize_interaction_mode("FACT") == "READ"

    with pytest.raises(FinnV2ModeContractError, match="finn_v2_mode_contract_invalid"):
        normalize_interaction_mode("NOT_A_MODE")


def test_terminal_envelope_reconstructs_historical_fact_as_read():
    service = FinnV2RunService(session=object())
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id="run-legacy-fact",
        user_id=7,
        conversation_id="conversation-1",
        status="completed",
        interaction_mode="FACT",
        visibility="visible",
        response_json=_response_payload("FACT"),
        policy_json=None,
        created_at=now,
        updated_at=now,
        completed_at=now,
        error_code=None,
        error_message=None,
        retryable=False,
    )
    service.delivery.get_delivery_artifacts = lambda **_kwargs: asyncio.sleep(0, result={})
    service.runtime_contracts = SimpleNamespace(get_for_run=lambda **_kwargs: asyncio.sleep(0, result=None))

    envelope = asyncio.run(service.envelope_from_run(run))

    assert envelope.mode == "READ"
    assert envelope.response.mode == "READ"


def test_terminal_envelope_returns_typed_failure_for_unknown_historical_mode():
    service = FinnV2RunService(session=object())
    now = datetime.now(timezone.utc)
    run = SimpleNamespace(
        id="run-invalid-mode",
        user_id=7,
        conversation_id="conversation-1",
        status="completed",
        interaction_mode="UNKNOWN",
        visibility="visible",
        response_json=_response_payload("UNKNOWN"),
        policy_json=None,
        created_at=now,
        updated_at=now,
        completed_at=now,
        error_code=None,
        error_message=None,
        retryable=False,
    )
    service.delivery.get_delivery_artifacts = lambda **_kwargs: asyncio.sleep(0, result={})
    service.runtime_contracts = SimpleNamespace(get_for_run=lambda **_kwargs: asyncio.sleep(0, result=None))

    envelope = asyncio.run(service.envelope_from_run(run))

    assert envelope.run_id == "run-invalid-mode"
    assert envelope.error_code == "finn_v2_mode_contract_invalid"
    assert envelope.response.mode == "UNAVAILABLE"


def test_delivery_polling_and_sse_return_a_typed_failure_for_unknown_historical_mode():
    service = FinnV2DeliveryService(session=object())
    service.runs.get_by_id_for_user = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(id="run-invalid-mode", conversation_id="conversation-1", status="completed"),
    )
    service.verified.get_latest_for_run = lambda **_kwargs: asyncio.sleep(
        0,
        result=SimpleNamespace(response_json=_response_payload("UNKNOWN")),
    )

    envelope = asyncio.run(service.get_delivery_envelope(user_id=7, run_id="run-invalid-mode"))

    async def _collect():
        return [event async for event in service.stream_delivery_events(user_id=7, run_id="run-invalid-mode")]

    events = asyncio.run(_collect())

    assert envelope.error_code == "finn_v2_mode_contract_invalid"
    assert events[0].event == "run.failed"
    assert events[0].payload["status"] == envelope.status


@pytest.mark.parametrize("mode", INTERACTION_MODES)
def test_canonical_modes_remain_unchanged_in_terminal_reconstruction(mode):
    assert normalize_interaction_mode(mode) == mode
