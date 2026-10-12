import asyncio
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from backend.services import finn_coach_feed_service as module
from backend.services.finn_v2_confirmation_service import FinnV2ConfirmationService


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
