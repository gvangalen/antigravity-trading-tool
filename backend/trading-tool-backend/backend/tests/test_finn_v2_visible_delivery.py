import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.schemas.finn_v2_response_schema import VerifiedResponse
from backend.services.finn_v2_visible_delivery_service import FinnV2VisibleDeliveryError, FinnV2VisibleDeliveryService


def test_visible_delivery_maps_verified_response_to_assistant_contract():
    service = FinnV2VisibleDeliveryService(session=object())
    service.gateway.run_foundation_now = lambda **kwargs: asyncio.sleep(0, result="run-1")
    service.delivery.get_delivery_artifacts = lambda **kwargs: asyncio.sleep(
        0,
        result={
            "delivery_envelope": {
                "run_id": "run-1",
                "conversation_id": "finn-v2-conv-1",
                "status": "completed",
                "delivery_source": "finn_v2_verified",
            },
            "verified_response": VerifiedResponse.parse_obj(
                {
                    "verified_response_id": "vr-1",
                    "run_id": "run-1",
                    "user_id": 1,
                    "mode": "CREATE_PROPOSAL",
                    "direct_answer": "Ik kan een BTC-voorstel voorbereiden.",
                    "main_observation": "BTC voorstel klaar voor review.",
                    "supporting_points": [],
                    "claims": [],
                    "uncertainty_summary": None,
                    "uncertainty_codes": [],
                    "next_step": None,
                    "follow_up_question": None,
                    "proposal_id": "proposal-1",
                    "confirmation_required": True,
                    "verifier_status": "passed",
                    "evidence_set_hash": "hash-1",
                    "verifier_result_id": "verifier-1",
                    "created_at": datetime.now(timezone.utc),
                }
            ).dict(),
            "orchestrator_result": {"outcome": "reasoning_ready"},
            "policy_result": {"allowed": True},
            "reasoning_result": {"mode": "CREATE_PROPOSAL"},
            "verifier_result": {"passed": True},
            "tool_calls": [{"tool_name": "read_active_asset"}],
            "validation_result": {"integrity_status": "valid"},
            "financial_state_snapshot": {"asset": "BTC"},
        },
    )

    envelope = asyncio.run(
        service.deliver_assistant_envelope(
            user_id=1,
            message="Werk mijn BTC setup bij.",
            context_payload={"page": "setup"},
            transport="chat",
            request_path="/assistant/chat",
            request_id="req-1",
            trace_id="trace-1",
        )
    )

    assert envelope["can_confirm"] is True
    assert envelope["actions"][0]["proposal_id"] == "proposal-1"
    assert envelope["response_trace"]["response_source"] == "finn_v2_verified"
    assert envelope["response_trace"]["pipeline_version"] == "finn_v2"
    assert envelope["response_trace"]["tool_calls"][0]["tool_name"] == "read_active_asset"
    assert envelope["session_id"] == "finn-v2-conv-1"


def test_visible_delivery_returns_pending_contract_with_same_run_id():
    service = FinnV2VisibleDeliveryService(session=object())
    service.gateway.run_foundation_now = lambda **kwargs: asyncio.sleep(0, result="run-pending")
    service.delivery.get_delivery_artifacts = lambda **kwargs: asyncio.sleep(
        0,
        result={"delivery_envelope": {"conversation_id": "finn-v2-conv-pending", "status": "planned", "error_code": None}, "verified_response": None},
    )

    envelope = asyncio.run(
        service.deliver_assistant_envelope(
            user_id=1,
            message="Werk mijn BTC setup bij.",
            context_payload={"page": "setup"},
            transport="chat",
            request_path="/assistant/chat",
            request_id="req-1",
            trace_id="trace-1",
        )
    )

    assert envelope["intent"] == "processing"
    assert envelope["state"]["current_flow"] == "finn_v2_visible_pending"
    assert envelope["state"]["run_id"] == "run-pending"
    assert envelope["response_trace"]["run_id"] == "run-pending"
    assert envelope["session_id"] == "finn-v2-conv-pending"


def test_visible_delivery_returns_terminal_failure_contract_with_same_run_id():
    service = FinnV2VisibleDeliveryService(session=object())
    service.gateway.run_foundation_now = lambda **kwargs: asyncio.sleep(0, result="run-failed")
    service.delivery.get_delivery_artifacts = lambda **kwargs: asyncio.sleep(
        0,
        result={"delivery_envelope": {"conversation_id": "finn-v2-conv-failed", "status": "failed", "error_code": "orchestrator_failed"}, "verified_response": None},
    )

    envelope = asyncio.run(
        service.deliver_assistant_envelope(
            user_id=1,
            message="Werk mijn BTC setup bij.",
            context_payload={"page": "setup"},
            transport="chat",
            request_path="/assistant/chat",
            request_id="req-1",
            trace_id="trace-1",
        )
    )

    assert envelope["intent"] == "unavailable"
    assert envelope["state"]["current_flow"] == "finn_v2_visible_terminal_failed"
    assert envelope["state"]["run_id"] == "run-failed"
    assert envelope["response_trace"]["error"] == "orchestrator_failed"
    assert envelope["session_id"] == "finn-v2-conv-failed"


def test_visible_delivery_preserves_run_id_when_delivery_chain_raises():
    service = FinnV2VisibleDeliveryService(session=object())
    service.gateway.run_foundation_now = lambda **kwargs: asyncio.sleep(0, result="run-capability-1")
    service.delivery.get_delivery_artifacts = lambda **kwargs: asyncio.sleep(0, result={"delivery_envelope": {"run_id": "run-capability-1"}})

    envelope = asyncio.run(
        service.deliver_assistant_envelope(
            user_id=1,
            message="Hoi FINN, wat kun je voor mij doen?",
            context_payload={"missing_context": ["asset", "setup"]},
            transport="chat",
            request_path="/assistant/chat",
            request_id="req-capability-1",
            trace_id="trace-capability-1",
        )
    )

    assert envelope["intent"] == "unavailable"
    assert envelope["state"]["run_id"] == "run-capability-1"
    assert envelope["response_trace"]["run_id"] == "run-capability-1"


def test_visible_post_execution_runner_reads_only_browser_equivalent_public_contracts(monkeypatch):
    """The host-side parity runner must not inspect a different local database.

    A browser only receives the owner-scoped run and proposal routes. Keeping
    this boundary explicit makes the confirmation-to-follow-up regression
    meaningful when the runtime itself is running inside Docker.
    """
    from backend.scripts import run_finn_v2_visible_post_execution_reference_regression as runner

    calls = []

    def fake_request_json(*, url, method, headers, body, timeout):
        calls.append((url, method, headers, body, timeout))
        if url.endswith("/runs/run-visible-1"):
            return {
                "run_id": "run-visible-1",
                "runtime_trace": {"contract_id": "contract-visible-1"},
                "response": {"proposal_id": "proposal-visible-1"},
            }, 200
        if url.endswith("/proposals/proposal-visible-1"):
            return {"proposal_id": "proposal-visible-1", "payload_hash": "hash-visible-1"}, 200
        raise AssertionError(url)

    monkeypatch.setattr(runner, "_request_json", fake_request_json)

    record = runner._public_runtime_record(
        base_url="http://127.0.0.1:18001",
        token="local-test-token",
        run_id="run-visible-1",
    )

    assert record == {
        "runtime_contract_id": "contract-visible-1",
        "runtime_state": {},
        "terminal_projection": {"contract_id": "contract-visible-1"},
        "proposal": {"id": "proposal-visible-1", "payload_hash": "hash-visible-1"},
    }
    assert [(method, url.rsplit("/", 1)[-1]) for url, method, *_ in calls] == [
        ("GET", "run-visible-1"),
        ("GET", "proposal-visible-1"),
    ]
