import asyncio
import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.services import finn_coach_feed_service as module
from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService
from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
from backend.services.finn_v2_orchestrator_service import FinnV2OrchestratorService
from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor, _feed_evidence_instruction
from backend.services.finn_v2_responses_answer_verifier import FinnResponsesVerifiedAnswer
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.api.ai_assistant_api import _feed_context_boundary


def test_fallback_preserves_subject_and_never_claims_an_entry_signal():
    copy = module._fallback("plan_match", "BTC Full Base", {})
    assert set(copy) == {"nl", "en", "de"}
    assert all("BTC Full Base" in item["body"] for item in copy.values())
    assert "geen instapsignaal" in copy["nl"]["body"]
    assert "not an entry signal" in copy["en"]["body"]


def test_proposal_copy_uses_exact_typed_amount_and_budget_meaning():
    amount = module._fallback("proposal_pending", "ETH DCA", {
        "amount_kind": "base_amount", "amount_eur": "120.50",
    })
    assert "ETH DCA" in amount["nl"]["body"]
    assert "Basisbedrag: €120,50" in amount["nl"]["body"]
    assert "Base amount: €120.50" in amount["en"]["body"]
    budget = module._fallback("proposal_pending", "Paper Bot", {
        "amount_kind": "budget_total_eur", "amount_eur": "1000",
    })
    assert "Botbudgetlimiet: €1000,00" in budget["nl"]["body"]
    assert "beschikbaar saldo" not in budget["nl"]["body"]


def test_proposal_feed_uses_typed_saved_name_and_amount(monkeypatch):
    captured = {}

    async def publish(_self, **kwargs):
        captured.update(kwargs)
        return "feed-id"

    monkeypatch.setattr(module.FinnCoachFeedService, "publish", publish)
    service = FinnV2ConfirmationService.__new__(FinnV2ConfirmationService)
    service.session = SimpleNamespace(execute=lambda *_args, **_kwargs: None)
    proposal = SimpleNamespace(
        id="proposal-1", asset="ETH", operation_type="create_strategy",
        expires_at=datetime.now(timezone.utc), payload_hash="hash",
        payload_json={"change": {"strategy_fields": {
            "name": "ETH DCA eigen plan", "base_amount": 120.5,
        }}},
    )
    assert asyncio.run(service._publish_feed_proposal(proposal, user_id=7)) == "feed-id"
    assert captured["subject"] == "ETH DCA eigen plan"
    assert captured["evidence"]["amount_eur"] == 120.5
    assert captured["evidence"]["amount_kind"] == "base_amount"


def test_pending_update_feed_names_the_exact_owned_setup(monkeypatch):
    captured = {}
    query = {}

    class Result:
        def mappings(self):
            return self

        def one_or_none(self):
            return {"name": "ETH Plan B"}

    async def execute(_statement, params):
        query.update(params)
        return Result()

    async def publish(_self, **kwargs):
        captured.update(kwargs)
        return "feed-id"

    monkeypatch.setattr(module.FinnCoachFeedService, "publish", publish)
    proposal = SimpleNamespace(
        id="proposal-b", asset="ETH", operation_type="update_setup",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5), payload_hash="hash-b",
        payload_json={"target": {"target_type": "setup", "target_id": "22"},
                      "change": {"changed_fields": {"timeframe": "4H"}}},
    )
    service = module.FinnCoachFeedService(SimpleNamespace(execute=execute))
    assert asyncio.run(service.publish_pending_proposal(proposal, user_id=7)) == "feed-id"
    assert query == {"target_id": 22, "user_id": 7}
    assert captured["subject"] == "ETH Plan B"
    assert captured["evidence"]["target_name"] == "ETH Plan B"
    assert captured["evidence"]["target_id"] == 22


def test_pending_update_does_not_expose_a_target_outside_the_owner_scope():
    class Result:
        def mappings(self):
            return self

        def one_or_none(self):
            return None

    async def execute(_statement, _params):
        return Result()

    proposal = SimpleNamespace(
        operation_type="update_setup",
        payload_json={"target": {"target_id": "22"}},
    )
    resolved = asyncio.run(module.FinnCoachFeedService(
        SimpleNamespace(execute=execute),
    )._proposal_target(proposal, user_id=7))
    assert resolved == ("setup", None, None)


def test_discuss_proposal_uses_fresh_owner_scoped_evidence_not_client_claims(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000001"

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 7
        return {"id": item_id, "event_type": "proposal_pending", "subject_id": "p-1",
                "symbol": "ETH", "status": "unread"}

    async def get_by_id(_self, *, proposal_id, user_id):
        assert (proposal_id, user_id) == ("p-1", 7)
        return SimpleNamespace(id="p-1", status="draft", asset="ETH",
            operation_type="create_strategy", expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            payload_json={"change": {"strategy_fields": {"name": "ETH Exact Plan"}}})

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr(
        "backend.infrastructure.repositories.finn_v2_proposal_repository.FinnV2ProposalRepository.get_by_id_for_user",
        get_by_id,
    )
    service = FinnV2ReasoningContextService(SimpleNamespace())
    run = SimpleNamespace(user_id=7, client_context_json={
        "feed_item_id": item_id, "feed_proposal_name": "Forged Name",
        "feed_current_status": "confirmed"})
    evidence = asyncio.run(service._current_feed_evidence(run))[0]
    assert evidence.facts["proposal_name"] == "ETH Exact Plan"
    assert evidence.facts["proposal_status"] == "awaiting_separate_confirmation"
    assert evidence.facts["proposed_changes"] == {"name": "ETH Exact Plan"}
    assert evidence.facts["confirmation_authorized"] is False
    assert "Forged Name" not in str(evidence.dict())


def test_proposal_follow_up_rereads_owner_scoped_open_change(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000099"

    async def saved_context(_self, *, conversation_id, user_id):
        assert (conversation_id, user_id) == ("conversation-b", 7)
        return {"feed_event": {"item_id": item_id, "read_only_context": True}}

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 7
        return {"id": item_id, "event_type": "proposal_pending", "subject_id": "p-b",
                "symbol": "ETH", "status": "unread"}

    async def get_by_id(_self, *, proposal_id, user_id):
        assert (proposal_id, user_id) == ("p-b", 7)
        return SimpleNamespace(id="p-b", status="draft", asset="ETH",
            operation_type="update_setup", expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
            payload_json={"change": {"changed_fields": {
                "timeframe": "4H", "secret_internal_note": "never expose",
            }}})

    async def target(_self, proposal, *, user_id):
        assert user_id == 7
        return "setup", 22, "ETH Plan B"

    monkeypatch.setattr(
        "backend.infrastructure.repositories.finn_v2_conversation_repository.FinnV2ConversationRepository.get_context",
        saved_context,
    )
    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr(module.FinnCoachFeedService, "_proposal_target", target)
    monkeypatch.setattr(
        "backend.infrastructure.repositories.finn_v2_proposal_repository.FinnV2ProposalRepository.get_by_id_for_user",
        get_by_id,
    )
    evidence = asyncio.run(FinnV2ReasoningContextService(SimpleNamespace())._current_feed_evidence(
        SimpleNamespace(user_id=7, conversation_id="conversation-b", client_context_json={}),
    ))[0]
    assert evidence.facts["proposal_status"] == "awaiting_separate_confirmation"
    assert evidence.facts["target_name"] == "ETH Plan B"
    assert evidence.facts["proposed_changes"] == {"timeframe": "4H"}
    assert evidence.facts["confirmation_authorized"] is False
    assert "secret_internal_note" not in str(evidence.dict())
    instruction = _feed_evidence_instruction([{"source": evidence.source, "facts": evidence.facts}])
    assert '"timeframe": "4H"' in instruction
    assert "still pending, not saved" in instruction
    assert "discussion never confirms a proposal" in instruction
    assert "secret_internal_note" not in instruction
    assert instruction in FinnResponsesFrontDoor._model_led_instructions(
        "nl", feed_evidence=[{"source": evidence.source, "facts": evidence.facts}],
    )


def test_direct_responses_read_persists_selected_feed_for_next_turn(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000099"
    run = SimpleNamespace(
        id="run-b", user_id=7, conversation_id="conversation-b", status="planned",
        message="Wat betekent deze update?", trace_id="trace-b",
        client_context_json={"feed_item_id": item_id},
    )

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 7
        return {"id": item_id, "event_type": "proposal_pending",
                "subject_type": "proposal", "subject_id": "proposal-b",
                "symbol": "ETH", "evidence": {"target_name": "ETH Plan B"}}

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    service = FinnV2RunService.__new__(FinnV2RunService)
    service.session = SimpleNamespace()
    service.runs = SimpleNamespace(
        get_by_id_for_user=AsyncMock(return_value=run), update_status=AsyncMock(),
    )
    service.runtime_contracts = SimpleNamespace(
        get_for_run=AsyncMock(return_value=SimpleNamespace(state_json={"responses_exchange": {}})),
        record_verified_setup_subject=AsyncMock(),
        materialize_terminal=AsyncMock(return_value=SimpleNamespace(terminal_projection_json={})),
    )
    service.traces = SimpleNamespace(append_event=AsyncMock())
    service.conversations = SimpleNamespace(
        set_selected_feed_event=AsyncMock(), set_responses_cursor=AsyncMock(),
    )
    service._trace_payload = lambda *_args, **_kwargs: {}
    service._commit_session_if_possible = AsyncMock()
    asyncio.run(service.complete_responses_read(
        run_id="run-b", user_id=7, response_id="response-b",
        answer=FinnResponsesVerifiedAnswer("completed", "Dit voorstel wacht op bevestiging.", None, ()),
        locale="nl",
    ))
    selected = service.conversations.set_selected_feed_event.call_args.kwargs
    assert selected["conversation_id"] == "conversation-b"
    assert selected["user_id"] == 7
    assert selected["run_id"] == "run-b"
    assert selected["feed_event"]["item_id"] == item_id
    assert selected["feed_event"]["action_authorized"] is False
    service.conversations.set_responses_cursor.assert_awaited_once()


def test_discuss_setup_rechecks_current_match_and_marks_old_notification_historical(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000002"

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 7
        return {"id": item_id, "event_type": "plan_match", "subject_type": "setup",
                "subject_id": "11", "symbol": "ETH", "status": "read",
                "source_observed_at": "2026-10-10T10:00:00Z",
                "evidence": {"benchmark_score": 72, "status": "matches"}}

    class MatchService:
        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol):
            assert (user_id, symbol) == (7, "ETH")
            return {"source_status": "stale_sources", "matches": [
                {"setup_id": 11, "name": "ETH Eigen Plan", "status": "insufficient_data"}]}

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", MatchService)
    service = FinnV2ReasoningContextService(SimpleNamespace())
    historical, current = asyncio.run(service._current_feed_evidence(SimpleNamespace(
        user_id=7, client_context_json={"feed_item_id": item_id})))
    assert current.facts["current_setup"]["name"] == "ETH Eigen Plan"
    assert current.facts["current_setup"]["status"] == "insufficient_data"
    assert historical.facts["historical_notification"] is True
    assert historical.facts["current_trade_signal_confirmed"] is False
    assert historical.facts["historical_event_facts"]["benchmark_score"] == 72
    assert historical.facts["historical_source_observed_at"] == "2026-10-10T10:00:00Z"
    assert historical.freshness == "historical"
    assert historical.as_of.isoformat() == "2026-10-10T10:00:00+00:00"
    assert current.freshness == "stale"


def test_feed_selection_replaces_prior_plan_referent_for_this_turn():
    selected = FinnV2OrchestratorService._selected_feed_context({
        "last_verified_context": {"resolved_entities": {"name": "QA Plan A"}},
        "active_guided_operation": {"name": "QA Plan A"},
    }, {
        "event_type": "plan_match", "subject_type": "setup", "subject_id": "222",
        "symbol": "ETH", "evidence": {"subject": "QA Plan B"},
    })
    assert selected == {"feed_event": {
        "event_type": "plan_match", "subject_type": "setup", "subject_id": "222",
        "symbol": "ETH", "subject": "QA Plan B", "read_only_context": True,
        "action_authorized": False,
    }}
    assert "last_verified_context" not in selected
    assert "active_guided_operation" not in selected


def test_proposal_feed_selection_carries_exact_plan_target_without_authorizing_action():
    selected = FinnV2OrchestratorService._selected_feed_context({
        "last_verified_context": {"resolved_entities": {"name": "ETH Plan A"}},
    }, {
        "id": "feed-b", "event_type": "proposal_pending", "subject_type": "proposal",
        "subject_id": "proposal-b", "symbol": "ETH",
        "evidence": {"subject": "ETH Plan B", "target_type": "setup",
                     "target_id": 22, "target_name": "ETH Plan B"},
    })["feed_event"]
    assert selected["subject_id"] == "proposal-b"
    assert selected["item_id"] == "feed-b"
    assert selected["target_id"] == 22
    assert selected["target_name"] == "ETH Plan B"
    assert selected["action_authorized"] is False
    assert "Plan A" not in str(selected)


def test_feed_boundary_discards_stale_client_plan_and_draft_before_selection():
    incoming = {
        "feed_item_id": "feed-b", "locale": "nl", "session_id": "conversation-1",
        "symbol": "BTC", "setup_id": 111, "setup_name": "QA Plan A",
        "strategy_id": 8, "bot_id": 9, "current_flow": "update_setup",
        "finn_draft": {"name": "QA Plan A"}, "page": "/setup",
    }
    assert _feed_context_boundary(incoming) == {
        "feed_item_id": "feed-b", "locale": "nl", "session_id": "conversation-1",
    }
    assert _feed_context_boundary({"setup_id": 111}) == {"setup_id": 111}


def test_discuss_market_move_can_explain_recorded_change_without_calling_it_current(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000003"

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 7
        return {"id": item_id, "event_type": "market_move", "subject_type": "asset",
                "subject_id": "BTC", "symbol": "BTC", "status": "read",
                "source_observed_at": "2026-10-10T10:00:00Z",
                "evidence": {"change_24h": 10.5, "status": "measured_move"}}

    class MatchService:
        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol):
            assert (user_id, symbol) == (7, "BTC")
            return {"source_status": "stale_sources", "matches": []}

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", MatchService)
    historical, current = asyncio.run(FinnV2ReasoningContextService(SimpleNamespace())._current_feed_evidence(
        SimpleNamespace(user_id=7, client_context_json={"feed_item_id": item_id})))
    assert historical.facts["historical_event_facts"]["change_24h"] == 10.5
    assert historical.freshness == "historical"
    assert current.facts["current_source_status"] == "stale_sources"
    assert current.freshness == "stale"
    assert current.facts["current_trade_signal_confirmed"] is False


def test_missing_score_emits_one_owner_asset_blocker_without_false_match(monkeypatch):
    assessment = {
        "source_status": "stale_sources", "component_source_status": {
            "market_score": "fresh", "macro_score": "stale_source", "technical_score": "fresh",
        },
        "component_source_observed_at": {"macro": {"DXY": "2026-10-01T00:00:00Z"}},
        "matches": [
            {"setup_id": 11, "name": "BTC A", "status": "insufficient_data"},
            {"setup_id": 12, "name": "BTC B", "status": "insufficient_data"},
        ],
    }

    class MatchService:
        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol):
            assert (user_id, symbol) == (7, "BTC")
            return assessment

    class MarketRepo:
        def __init__(self, _session):
            pass

        async def get_latest_snapshot(self, _symbol):
            return None

    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", MatchService)
    monkeypatch.setattr("backend.infrastructure.repositories.market_data_repository.MarketDataRepository", MarketRepo)
    class Rows:
        def mappings(self):
            return self

        def all(self):
            return []

    class Session:
        async def execute(self, _query, params):
            assert params == {"user_id": 7, "symbol": "BTC"}
            return Rows()

    service = module.FinnCoachFeedService(Session())
    published = []
    resolved = []

    async def publish(**kwargs):
        published.append(kwargs)
        return "item-one"

    async def resolve(**kwargs):
        resolved.append(kwargs)

    service.publish = publish
    service.resolve = resolve
    assert asyncio.run(service.reconcile_score_asset(user_id=7, symbol="btc")) == ["item-one"]
    assert len(published) == 1
    assert published[0]["event_type"] == "data_blocked"
    assert published[0]["priority"] > 3  # a blocker outranks positive plan matches
    assert published[0]["evidence"]["setup_ids"] == ["11", "12"]
    assert {row["event_key"] for row in resolved} == {"plan-match:11", "plan-match:12", "market-move:BTC"}


def test_list_is_read_only_and_scoped_to_owner(monkeypatch):
    async def forbidden_provider(**_kwargs):
        raise AssertionError("feed GET called OpenAI")

    monkeypatch.setattr(module, "ask_gpt_structured_response_async", forbidden_provider)
    observed = []

    class Result:
        def mappings(self):
            return self

        def all(self):
            return []

    class Session:
        async def execute(self, query, params):
            observed.append((str(query), params))
            return Result()

    assert asyncio.run(module.FinnCoachFeedService(Session()).list(user_id=7)) == []
    assert observed[0][1]["user_id"] == 7
    assert "user_id=:user_id" in observed[0][0]
    assert "finn_v2_proposals" in observed[0][0]


def test_generated_trading_instruction_cannot_become_feed_copy(monkeypatch):
    async def model(**_kwargs):
        return {"parsed": {"focus": "Voor <subject> kun je nu veilig instappen."}}

    monkeypatch.setattr(module, "ask_gpt_structured_response_async", model)
    statements = []

    class Claim:
        def first(self):
            return ("item",)

    class Session:
        async def execute(self, query, params):
            statements.append((str(query), params))
            return Claim()

        async def commit(self):
            pass

    service = module.FinnCoachFeedService(Session())

    async def detail(**_kwargs):
        return {"id": "00000000-0000-0000-0000-000000000001",
                "copy_source": "fact_fallback", "status": "unread",
                "event_type": "plan_match", "subject_type": "setup",
                "evidence": {"subject": "BTC Full Base", "status": "matches"},
                "fingerprint": "abc"}

    service.detail = detail
    assert asyncio.run(service.generate_copy(user_id=7, item_id="00000000-0000-0000-0000-000000000001")) is False
    assert len(statements) == 1  # attempt recorded, no fabricated copy persisted


def test_context_focus_uses_only_server_verified_copy():
    copy = module._fallback("plan_match", "BTC Exact Setup", {}, focus="context")
    assert "BTC Exact Setup" in copy["nl"]["body"]
    assert "geen instapsignaal" in copy["nl"]["body"]
    assert "not an entry signal" in copy["en"]["body"]
    assert "kein Einstiegssignal" in copy["de"]["body"]


def test_luna_lead_is_personal_but_cannot_introduce_trade_action_or_figures():
    assert module._verified_lead("Er is een update over BTC Full Base.", "BTC Full Base", "nl")
    assert module._verified_lead("There is an update about BTC Full Base.", "BTC Full Base", "en")
    assert module._verified_lead("Koop nu BTC Full Base.", "BTC Full Base", "nl") is None
    assert module._verified_lead("BTC Full Base biedt een kans die je vandaag moet grijpen.", "BTC Full Base", "nl") is None
    assert module._verified_lead("Voor BTC Full Base is direct handelen verstandig.", "BTC Full Base", "nl") is None
    assert module._verified_lead("Apple presteert beter dan BTC Full Base.", "BTC Full Base", "nl") is None
    assert module._verified_lead("BTC Full Base is 120% zeker.", "BTC Full Base", "nl") is None


@pytest.mark.parametrize("previous_status", ["handled", "archived", "resolved", "unread"])
def test_same_observation_does_not_reopen_after_acknowledgement_or_expiry(previous_status):
    digest = hashlib.sha256("same-revision".encode()).hexdigest()
    statements = []

    class Result:
        def mappings(self):
            return self

        def first(self):
            return {"id": "old", "fingerprint": digest, "status": previous_status}

    class Session:
        async def execute(self, sql, _params):
            statements.append(str(sql))
            return Result()

    created = asyncio.run(module.FinnCoachFeedService(Session()).publish(
        user_id=7, event_key="plan-match:11", event_type="plan_match",
        subject_type="setup", subject_id="11", subject="BTC Setup", symbol="BTC",
        evidence={"status": "matches"}, revision="same-revision",
        expires_at=datetime.now(timezone.utc),
    ))
    assert created is None
    assert len(statements) == 2
    assert not any("INSERT INTO finn_coach_feed_items" in sql for sql in statements)


def test_cleared_condition_can_reopen_after_same_score_returns():
    digest = hashlib.sha256("same-revision".encode()).hexdigest()
    statements = []

    class Result:
        def __init__(self, row):
            self.row = row

        def mappings(self):
            return self

        def first(self):
            return self.row

    class Session:
        async def execute(self, sql, _params):
            statements.append(str(sql))
            if "SELECT id, fingerprint" in str(sql):
                return Result({"id": "old", "fingerprint": f"resolved:{digest}", "status": "resolved"})
            return Result(("new",))

    created = asyncio.run(module.FinnCoachFeedService(Session()).publish(
        user_id=7, event_key="plan-match:11", event_type="plan_match",
        subject_type="setup", subject_id="11", subject="BTC Setup", symbol="BTC",
        evidence={"status": "matches"}, revision="same-revision",
    ))
    assert created == "new"
    assert any("INSERT INTO finn_coach_feed_items" in sql for sql in statements)


def test_clearing_handled_match_marks_transition_without_losing_history_status():
    statements = []

    class Session:
        async def execute(self, sql, _params):
            statements.append(str(sql))

    asyncio.run(module.FinnCoachFeedService(Session()).resolve(
        user_id=7, event_key="plan-match:11"))
    assert "CASE WHEN f.status IN ('unread','read') THEN 'resolved' ELSE f.status END" in statements[0]
    assert "CONCAT('resolved:', f.fingerprint)" in statements[0]
    assert "ORDER BY created_at DESC, id DESC LIMIT 1" in statements[0]
