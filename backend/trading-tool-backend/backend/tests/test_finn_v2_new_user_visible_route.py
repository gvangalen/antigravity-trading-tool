import asyncio
from types import SimpleNamespace

from backend.api import ai_assistant_api
from backend.main import app
from backend.schemas.assistant_schema import AssistantChatRequest
from backend.schemas.finn_v2_state_schema import FinancialStateSnapshot
from backend.services.finn_v2_evidence_validator_service import FinnV2EvidenceValidatorService
from backend.services.finn_v2_visible_delivery_service import FinnV2VisibleDeliveryError


class _FakeValidationRepo:
    def __init__(self):
        self.rows = {}

    async def get_for_snapshot_version(self, **kwargs):
        return self.rows.get(
            (
                kwargs["snapshot_id"],
                kwargs["user_id"],
                kwargs["validator_version"],
            )
        )

    async def create(self, **kwargs):
        self.rows[(kwargs["snapshot_id"], kwargs["user_id"], kwargs["validator_version"])] = SimpleNamespace(**kwargs)


class _StubFinnPlanService:
    async def hydrate_context(self, user_id, context):
        return dict(context or {})

    def sanitize_context_for_query(self, query, context):
        return dict(context or {})


def test_evidence_validator_handles_empty_snapshot_without_none_payload_crash():
    service = FinnV2EvidenceValidatorService(session=object())
    service.validations = _FakeValidationRepo()
    service.redaction = SimpleNamespace(payload_to_jsonable=lambda value: value.dict())

    snapshot = FinancialStateSnapshot.parse_obj(
        {
            "snapshot_id": "snap-empty",
            "run_id": "run-empty",
            "user_id": 351,
            "revision": 1,
            "evidence_set_hash": "hash-empty",
            "nodes": [],
            "edges": [],
            "tool_outcomes": [],
            "assembled_at": "2026-08-18T00:00:00Z",
        }
    )

    validation = asyncio.run(service.validate_snapshot(snapshot))

    assert validation.validation_id.startswith("finn-v2-validation-")
    assert validation.integrity_status == "valid"
    assert all(domain.status == "not_collected" for domain in validation.domains)


def test_assistant_chat_v2_only_new_user_returns_verified_v2_envelope(monkeypatch):
    async def _identity_context(db, user_id, payload=None, *, query=None):
        payload = dict(payload or {})
        payload.update(
            {
                "locale": "nl",
                "user_id": user_id,
                "symbol": None,
                "asset": None,
                "surface": "assistant_visible_v2",
                "missing_context": ["asset", "setup", "scores", "latest_report"],
                "trader_profile_used": False,
                "trader_profile": {
                    "asset_focus": [],
                    "trader_types": [],
                    "risk_profiles": [],
                    "behavior_flags": [],
                    "investment_goals": [],
                    "experience_levels": [],
                    "primary_timeframes": [],
                },
            }
        )
        return payload

    async def _visible_delivery(**kwargs):
        return {
            "response": "Ik kan je helpen om je profiel, assets, setup en strategie te begrijpen en veilige vervolgstappen voor te bereiden.",
            "intent": "capability",
            "state": {"current_flow": "finn_v2_visible", "run_id": "run-new-user", "surface": "assistant"},
            "summary": "Nieuwe user veilig op V2 afgehandeld.",
            "can_confirm": False,
            "actions": [],
            "response_trace": {
                "trace_id": kwargs["trace_id"],
                "run_id": "run-new-user",
                "pipeline_version": "finn_v2",
                "router_name": "finn_v2_orchestrator",
                "selected_handler": "FinnV2VisibleDeliveryService.deliver_assistant_envelope",
                "response_source": "finn_v2_verified",
                "validation_result": {"validation_id": "validation-1", "integrity_status": "valid"},
                "reasoning_result": {"reasoning_result_id": "reasoning-1", "status": "completed", "mode": "CAPABILITY"},
                "verifier_result": {"verifier_result_id": "verifier-1", "status": "passed"},
                "verified_response": {"verified_response_id": "verified-1", "mode": "CAPABILITY"},
                "delivery_envelope": {"run_id": "run-new-user", "status": "completed"},
            },
        }

    async def _graph_context(*, db, user_id, query, context_payload=None):
        return await _identity_context(db, user_id, context_payload, query=query)

    try:
        monkeypatch.setattr(ai_assistant_api, "_new_finn_plan_service", lambda db, trace_id=None: _StubFinnPlanService())
        monkeypatch.setattr(ai_assistant_api, "_enrich_with_trader_profile", _identity_context)
        monkeypatch.setattr(ai_assistant_api, "_apply_canonical_finn_context_graph", _graph_context)
        monkeypatch.setattr(ai_assistant_api, "_apply_assistant_rate_limit", lambda **kwargs: None)
        monkeypatch.setattr(ai_assistant_api, "_record_finn_product_event", lambda **kwargs: None)
        monkeypatch.setattr(ai_assistant_api, "_try_v2_visible_delivery", _visible_delivery)

        response = asyncio.run(
            ai_assistant_api.assistant_chat(
                request=AssistantChatRequest(
                    query="Hoi FINN, wat kun je voor mij doen?",
                    context={},
                    history=[],
                    session_id=None,
                ),
                raw_request=SimpleNamespace(
                    scope={"path": "/api/assistant/chat"},
                    state=SimpleNamespace(trace_id="trace-new-user-v2"),
                    headers={},
                    client=SimpleNamespace(host="127.0.0.1"),
                ),
                x_trace_id="trace-new-user-v2",
                current_user={"id": 351, "email": "new-user@example.net", "role": "user"},
                service=object(),
                db=object(),
            )
        )

        payload = response.dict()
        assert payload["flow"] == "finn_v2_visible"
        assert payload["response_trace"]["run_id"] == "run-new-user"
        assert payload["response_trace"]["pipeline_version"] == "finn_v2"
        assert payload["response_trace"]["router_name"] == "finn_v2_orchestrator"
        assert payload["response_trace"]["selected_handler"] == "FinnV2VisibleDeliveryService.deliver_assistant_envelope"
        assert payload["response_trace"]["verified_response"]["mode"] == "CAPABILITY"
        assert payload["response_trace"]["verified_response"]["verified_response_id"] == "verified-1"
        assert payload["response_trace"]["reasoning_result"]["reasoning_result_id"] == "reasoning-1"
        assert payload["response_trace"]["verifier_result"]["verifier_result_id"] == "verifier-1"
        assert payload["response_trace"]["delivery_envelope"]["status"] == "completed"
        assert payload["response"]
    finally:
        app.dependency_overrides.clear()


def test_assistant_chat_v2_only_capability_failure_keeps_internal_run_id(monkeypatch):
    selection = SimpleNamespace(
        selected_runtime="v2",
        visible_allowed=True,
        fallback_allowed=False,
        dict=lambda: {"selected_runtime": "v2", "runtime_mode": "v2_only"},
    )

    class Selector:
        def select(self, **kwargs):
            return selection

    class Delivery:
        async def deliver_assistant_envelope(self, **kwargs):
            raise FinnV2VisibleDeliveryError(
                "v2_delivery_failure",
                run_id="run-capability-failed",
                failure_stage="delivery_envelope",
            )

    monkeypatch.setattr(ai_assistant_api, "FinnV2RuntimeSelectorService", Selector)
    monkeypatch.setattr(ai_assistant_api, "FinnV2VisibleDeliveryService", lambda db: Delivery())

    payload = asyncio.run(
        ai_assistant_api._try_v2_visible_delivery(
            db=object(),
            user_id=352,
            message="Hoi FINN, wat kun je voor mij doen?",
            context_payload={"locale": "nl", "missing_context": ["asset", "setup", "strategy"]},
            transport="chat",
            request_path="/assistant/chat",
            request_id="req-capability-fail",
            trace_id="trace-capability-fail",
        )
    )

    assert payload["state"]["current_flow"] == "finn_v2_visible_failed"
    assert payload["response_trace"]["run_id"] == "run-capability-failed"
    assert payload["response_trace"]["error"] == "v2_delivery_failure"
    assert payload["response_trace"]["failure_stage"] == "delivery_envelope"


def test_try_v2_visible_delivery_uses_isolated_v2_session(monkeypatch):
    selection = SimpleNamespace(
        selected_runtime="v2",
        visible_allowed=True,
        fallback_allowed=False,
        dict=lambda: {"selected_runtime": "v2", "runtime_mode": "v2_only"},
    )

    class Selector:
        def select(self, **kwargs):
            return selection

    observed = {}

    class _SessionContext:
        def __init__(self, session):
            self.session = session

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, exc_type, exc, tb):
            return False

    async def _factory():
        raise AssertionError("factory should not be awaited directly")

    isolated_session = object()

    def _session_factory():
        return _SessionContext(isolated_session)

    class Delivery:
        def __init__(self, db):
            observed["delivery_db"] = db

        async def deliver_assistant_envelope(self, **kwargs):
            return {"response": "ok", "intent": "evaluation", "response_trace": {"run_id": "run-iso"}}

    monkeypatch.setattr(ai_assistant_api, "FinnV2RuntimeSelectorService", Selector)
    monkeypatch.setattr(ai_assistant_api, "FinnV2VisibleDeliveryService", Delivery)
    monkeypatch.setattr(ai_assistant_api, "async_session_factory", _session_factory)

    outer_db = object()
    payload = asyncio.run(
        ai_assistant_api._try_v2_visible_delivery(
            db=outer_db,
            user_id=370,
            message="Bekijk mijn BTC-profiel, indicatoren, setup, strategie en gekoppelde bot.",
            context_payload={"symbol": "BTC", "setup_id": 282, "strategy_id": 298, "bot_id": 159},
            transport="chat",
            request_path="/api/assistant/chat",
            request_id="req-isolated-v2",
            trace_id="trace-isolated-v2",
        )
    )

    assert observed["delivery_db"] is isolated_session
    assert observed["delivery_db"] is not outer_db
    assert payload["response_trace"]["runtime_selection"]["runtime_mode"] == "v2_only"
