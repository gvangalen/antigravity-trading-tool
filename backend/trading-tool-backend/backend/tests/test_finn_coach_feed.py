import asyncio
import hashlib
import json
from datetime import date, datetime, timedelta, timezone
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


def test_watchlist_feed_copy_suggests_analysis_without_claiming_changes():
    copy = module._fallback("watchlist_added", "BTC/USDT", {"trading_pair": "BTC/USDT"})
    assert "BTC/USDT" in copy["nl"]["title"]
    assert "niets aan je analyse gewijzigd" in copy["nl"]["body"]


def test_watchlist_feed_reads_exact_owned_row_before_publishing():
    class _Result:
        def mappings(self):
            return self

        def first(self):
            return {"id": 71, "created_at": datetime(2026, 11, 19, 10, 0),
                    "quote_currency": "USDT"}

    session = SimpleNamespace(execute=AsyncMock(return_value=_Result()))
    feed = module.FinnCoachFeedService(session)
    feed.publish = AsyncMock(return_value="feed-item")
    result = asyncio.run(feed.publish_watchlist_addition(
        user_id=7, symbol="btc", market_id=34,
    ))

    assert result == "feed-item"
    assert session.execute.await_args.args[1] == {
        "user_id": 7, "symbol": "BTC", "market_id": 34,
    }
    arguments = feed.publish.await_args.kwargs
    assert arguments["event_key"] == "watchlist-added:BTC:34"
    assert arguments["evidence"] == {"trading_pair": "BTC/USDT", "market_id": 34}
    assert arguments["source_observed_at"] == datetime(2026, 11, 19, 10, 0, tzinfo=timezone.utc)
    assert arguments["revision"].startswith("71:")


def test_chat_watchlist_addition_is_recorded_without_repeating_in_active_feed(monkeypatch):
    feed = SimpleNamespace(
        publish_watchlist_addition=AsyncMock(return_value="feed-item"),
        set_status=AsyncMock(),
    )
    monkeypatch.setattr(module, "FinnCoachFeedService", lambda session: feed)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    asyncio.run(module.record_watchlist_feed_change(
        session, user_id=7, symbol="BTC", market_id=34,
        added=True, discussed_in_chat=True,
    ))

    feed.set_status.assert_awaited_once_with(
        user_id=7, item_id="feed-item", status="handled",
    )
    session.commit.assert_awaited_once()


def test_web_watchlist_addition_remains_unread_for_feed(monkeypatch):
    feed = SimpleNamespace(
        publish_watchlist_addition=AsyncMock(return_value="feed-item"),
        set_status=AsyncMock(),
    )
    monkeypatch.setattr(module, "FinnCoachFeedService", lambda session: feed)
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())

    asyncio.run(module.record_watchlist_feed_change(
        session, user_id=7, symbol="BTC", market_id=34, added=True,
    ))

    feed.set_status.assert_not_awaited()
    session.commit.assert_awaited_once()


@pytest.mark.parametrize("terminal_status, expected", [
    ("completed", "handled"),
    ("clarification_required", "read"),
    ("failed", None),
])
def test_discussion_status_changes_only_after_usable_owned_reply(terminal_status, expected):
    class Result:
        def first(self):
            return ("feed-id",)

    session = SimpleNamespace(execute=AsyncMock(return_value=Result()))
    feed = module.FinnCoachFeedService(session)
    item_id = "00000000-0000-0000-0000-000000000099"
    changed = asyncio.run(feed.record_discussion_outcome(
        user_id=7, item_id=item_id, terminal_status=terminal_status,
    ))
    assert changed is (expected is not None)
    if expected is None:
        session.execute.assert_not_awaited()
    else:
        query, params = session.execute.await_args.args
        assert "event_type <> 'proposal_pending'" in str(query)
        assert params == {"id": item_id, "user_id": 7, "status": expected}


def test_calendar_only_score_date_is_not_presented_as_a_source_instant():
    assert module._utc_source_moment(date(2026, 11, 19)) is None
    assert module._utc_source_moment(datetime(2026, 11, 19, 10, 0)) == datetime(
        2026, 11, 19, 10, 0, tzinfo=timezone.utc,
    )


def test_journey_cards_use_exact_market_and_resolve_when_strategy_exists(monkeypatch):
    class Rows:
        def __init__(self, values):
            self.values = values

        def mappings(self):
            return self

        def first(self):
            return self.values[0] if self.values else None

        def all(self):
            return self.values


    class Session:
        def __init__(self, linked=False):
            self.linked = linked

        async def execute(self, query, params):
            sql = str(query)
            assert params["user_id"] == 7
            if "FROM watchlists w" in sql:
                assert params["market_id"] == 34
                return Rows([{"id": 71, "quote_currency": "USDT"}])
            if "FROM strategies" in sql:
                assert params["setup_ids"] == [42]
                return Rows([{"id": 91, "setup_id": 42, "name": "BTC Strategie",
                         "created_at": datetime.now(timezone.utc)}]
                            if self.linked else [])
            if "FROM bot_configs b" in sql:
                return Rows([(42,)] if self.linked else [])
            if "event_type='strategy_next_step'" in sql:
                return Rows([{"event_key": "strategy-next-step:42"}])
            if "event_type='paper_next_step'" in sql:
                return Rows([])
            raise AssertionError(sql)

    class Setups:
        def __init__(self, _session):
            pass

        async def get_all_setups(self, user_id):
            assert user_id == 7
            return [{"id": 42, "name": "BTC plan", "symbol": "BTC", "market_id": 34,
                              "created_at": datetime.now(timezone.utc)}]

    monkeypatch.setattr("backend.infrastructure.repositories.setup_repository.SetupRepository", Setups)
    service = module.FinnCoachFeedService(Session())
    service.publish = AsyncMock(return_value="card")
    service.resolve = AsyncMock()
    assert asyncio.run(service.reconcile_journey_next_steps(
        user_id=7, symbol="BTC", market_id=34)) == ["card"]
    assert service.publish.await_args.kwargs["evidence"]["trading_pair"] == "BTC/USDT"
    assert service.publish.await_args.kwargs["event_type"] == "strategy_next_step"

    linked_service = module.FinnCoachFeedService(Session(linked=True))
    linked_service.publish = AsyncMock()
    linked_service.resolve = AsyncMock()
    assert asyncio.run(linked_service.reconcile_journey_next_steps(
        user_id=7, symbol="BTC", market_id=34)) == []
    linked_service.resolve.assert_any_await(user_id=7, event_key="strategy-next-step:42")


def test_analysis_ready_requires_verified_score_and_no_setup(monkeypatch):
    class Rows:
        def __init__(self, values):
            self.values = values

        def mappings(self):
            return self

        def first(self):
            return self.values[0] if self.values else None

        def all(self):
            return self.values


    class Session:
        async def execute(self, query, params):
            sql = str(query)
            if "FROM watchlists w" in sql:
                return Rows([{"id": 71, "quote_currency": "USDT"}])
            if "event_type='strategy_next_step'" in sql:
                return Rows([])
            if "event_type='paper_next_step'" in sql:
                return Rows([])
            raise AssertionError(sql)

    class Setups:
        def __init__(self, _session):
            pass

        async def get_all_setups(self, user_id):
            return []

    class Match:
        status = "available"

        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol, *, setups, market_id):
            assert (user_id, symbol, setups, market_id) == (7, "BTC", [], 34)
            return {"source_status": self.status,
                    "benchmark_score": 52 if self.status == "available" else None,
                    "as_of": "2026-11-19"}

    monkeypatch.setattr("backend.infrastructure.repositories.setup_repository.SetupRepository", Setups)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", Match)
    service = module.FinnCoachFeedService(Session())
    service.publish = AsyncMock(return_value="card")
    service.resolve = AsyncMock()
    assert asyncio.run(service.reconcile_journey_next_steps(
        user_id=7, symbol="BTC", market_id=34)) == ["card"]
    assert service.publish.await_args.kwargs["revision"] == "available"
    Match.status = "stale_sources"
    service.publish.reset_mock()
    assert asyncio.run(service.reconcile_journey_next_steps(
        user_id=7, symbol="BTC", market_id=34)) == []
    service.publish.assert_not_awaited()
    service.resolve.assert_any_await(user_id=7, event_key="analysis-ready:BTC:34")


def test_paper_next_step_appears_only_for_strategy_without_bot(monkeypatch):
    class Rows:
        def __init__(self, values):
            self.values = values

        def mappings(self):
            return self

        def first(self):
            return self.values[0] if self.values else None

        def all(self):
            return self.values

    class Session:
        bot_exists = False

        async def execute(self, query, params):
            sql = str(query)
            if "FROM watchlists w" in sql:
                return Rows([{"id": 71, "quote_currency": "USDT"}])
            if "FROM strategies" in sql:
                return Rows([{"id": 91, "setup_id": 42, "name": "BTC Strategie",
                              "created_at": datetime.now(timezone.utc)}])
            if "FROM bot_configs b" in sql:
                assert "s.user_id=b.user_id" in sql
                return Rows([(42,)] if self.bot_exists else [])
            if "event_type='strategy_next_step'" in sql:
                return Rows([])
            if "event_type='paper_next_step'" in sql:
                return Rows([{"event_key": "paper-next-step:42"}])
            raise AssertionError(sql)

    class Setups:
        def __init__(self, _session):
            pass

        async def get_all_setups(self, user_id):
            return [{"id": 42, "name": "BTC plan", "symbol": "BTC", "market_id": 34,
                     "created_at": datetime.now(timezone.utc) - timedelta(hours=2)}]

    monkeypatch.setattr("backend.infrastructure.repositories.setup_repository.SetupRepository", Setups)
    session = Session()
    service = module.FinnCoachFeedService(session)
    service.publish = AsyncMock(return_value="card")
    service.resolve = AsyncMock()
    assert asyncio.run(service.reconcile_journey_next_steps(
        user_id=7, symbol="BTC", market_id=34)) == ["card"]
    assert service.publish.await_args.kwargs["event_type"] == "paper_next_step"
    assert service.publish.await_args.kwargs["evidence"]["trading_pair"] == "BTC/USDT"

    session.bot_exists = True
    service.publish.reset_mock()
    assert asyncio.run(service.reconcile_journey_next_steps(
        user_id=7, symbol="BTC", market_id=34)) == []
    service.publish.assert_not_awaited()
    service.resolve.assert_any_await(user_id=7, event_key="paper-next-step:42")



@pytest.mark.parametrize("locale,closed_title", [
    ("nl", "Voorstel niet meer actief"),
    ("en", "Proposal no longer active"),
    ("de", "Vorschlag nicht mehr aktiv"),
])
def test_resolved_proposal_history_does_not_keep_waiting_for_confirmation(locale, closed_title):
    row = {
        "id": "4b60dd31-963f-42e9-8306-48f38626b118",
        "event_type": "proposal_pending", "subject_type": "proposal",
        "subject_id": "old-proposal", "status": "resolved", "symbol": "AAPL",
        "copy_json": {language: {"title": "Voorstel wacht op jou",
                               "body": "Wacht op jouw afzonderlijke bevestiging."}
                      for language in ("nl", "en", "de")},
        "evidence": {},
    }
    item = module.FinnCoachFeedService._serialize(row, locale)
    assert item["title"] == closed_title
    assert "wacht op jou" not in item["title"].lower()
    assert "wacht op jouw afzonderlijke bevestiging" not in item["description"].lower()
    assert item["status"] == "resolved"


def test_fallback_preserves_subject_and_never_claims_an_entry_signal():
    copy = module._fallback("plan_match", "BTC Full Base", {})
    assert set(copy) == {"nl", "en", "de"}
    assert all("BTC Full Base" in item["body"] for item in copy.values())
    assert "geen instapsignaal" in copy["nl"]["body"]
    assert "not an entry signal" in copy["en"]["body"]


def test_missing_indicator_bot_review_is_owner_and_pair_scoped(monkeypatch):
    class Rows:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def all(self):
            return self.rows

    class Session:
        async def execute(self, query, params):
            statement = str(query)
            if "FROM bot_configs b" in statement:
                assert params == {"user_id": 7, "symbol": "BTC", "market_id": 123}
                assert "JOIN strategies s ON s.id=b.strategy_id AND s.user_id=b.user_id" in statement
                assert "s.setup_id IS NOT NULL" in statement
                return Rows([{"id": 9, "name": "BTC Paper", "setup_id": 42, "is_live": False},
                             {"id": 10, "name": "BTC Live", "setup_id": 42, "is_live": True}])
            return Rows([])

    class Setups:
        def __init__(self, _session):
            pass

        async def get_all_setups(self, user_id):
            assert user_id == 7
            return [{"id": 42, "name": "BTC plan", "symbol": "BTC", "market_id": 123,
                     "setup_type": "trade", "min_benchmark_score": 40,
                     "max_benchmark_score": 60}]

    class Match:
        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol, **kwargs):
            assert (user_id, symbol, kwargs["market_id"]) == (7, "BTC", 123)
            return {"indicative_component_scores": {"market": 60, "macro": 35, "technical": 40},
                    "indicative_benchmark_score": 45,
                    "benchmark_weights": {"market_score": 1 / 3, "macro_score": 1 / 3,
                                          "technical_score": 1 / 3},
                    "missing_indicators": {"macro": ["us02y", "us10y"]}}

    monkeypatch.setattr("backend.infrastructure.repositories.setup_repository.SetupRepository", Setups)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", Match)
    service = module.FinnCoachFeedService(Session())
    published = []

    async def publish(**kwargs):
        published.append(kwargs)
        return "item"

    service.publish = publish
    service.resolve = AsyncMock()
    assert asyncio.run(service.reconcile_missing_indicator_bots(
        user_id=7, symbol="BTC", market_id=123)) == ["item", "item"]
    assert {item["subject_id"] for item in published} == {"9", "10"}
    assert all(item["evidence"]["candidate_only"] for item in published)
    assert "koopt niet automatisch" in module._fallback(
        "data_blocked", "BTC Live", published[1]["evidence"])["nl"]["body"]


def test_daily_report_notification_has_one_factual_translation_per_locale():
    copy = module._fallback("daily_report_ready", "Dagrapport", {"report_date": "2026-11-04"})
    assert set(copy) == {"nl", "en", "de"}
    assert all(item["body"] for item in copy.values())
    assert "staat klaar" in copy["nl"]["title"]
    assert "2026-11-04" in copy["nl"]["body"]
    assert "Paper" not in copy["nl"]["body"]


def test_verified_paper_sale_offers_reflection_only_after_filled_order():
    filled = module._fallback("bot_decision", "BTC bot", {
        "symbol": "BTC", "action": "sell", "status": "executed",
        "order_status": "filled",
    })
    unverified = module._fallback("bot_decision", "BTC bot", {
        "symbol": "BTC", "action": "sell", "status": "executed",
        "order_status": None,
    })
    assert "reflectie" in filled["nl"]["body"]
    assert "reflectie" not in unverified["nl"]["body"]


@pytest.mark.parametrize("report_type,expected", [
    ("weekly", "weekrapport"),
    ("monthly", "maandrapport"),
    ("quarterly", "kwartaalrapport"),
])
def test_periodic_report_notification_names_the_saved_period(report_type, expected):
    copy = module._fallback("periodic_report_ready", report_type, {
        "report_type": report_type, "report_date": "2026-11-04",
    })
    assert expected in copy["nl"]["title"]
    assert set(copy) == {"nl", "en", "de"}
    assert all(row["body"] for row in copy.values())


def test_weekly_reflection_copy_uses_closed_week_coverage():
    copy = module._fallback("weekly_reflection", "Weekreflectie", {
        "week_start": "2026-11-09", "trades": 3, "plans": 2, "notes": 1,
    })
    assert "3 gesloten trades" in copy["nl"]["body"]
    assert "2 met vastgelegd plan" in copy["nl"]["body"]
    assert "vóór een volgende trade" in copy["nl"]["body"]


def test_weekly_feed_evidence_names_inclusive_sunday(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000091"

    async def detail(_self, *, user_id, item_id: str):
        return {"id": item_id, "event_type": "weekly_reflection", "subject_type": "reflection",
                "subject_id": "2026-11-09", "symbol": None, "status": "read",
                "source_observed_at": "2026-11-16T05:15:00Z",
                "evidence": {"week_start": "2026-11-09", "week_end": "2026-11-16"}}

    class Session:
        async def execute(self, _query, params):
            assert params == {"user_id": 7, "week_start": __import__("datetime").date(2026, 11, 9)}
            class Result:
                def mappings(self):
                    return self
                def first(self):
                    return {"summary": {"trades": 1, "plans": 1},
                            "generated_at": datetime(2026, 11, 16, 5, 15, tzinfo=timezone.utc)}
            return Result()

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    historical, current = asyncio.run(FinnV2ReasoningContextService(Session())._current_feed_evidence(
        SimpleNamespace(user_id=7, client_context_json={"feed_item_id": item_id})))
    assert historical.facts["historical_event_facts"]["week_end"] == "2026-11-15"
    assert historical.facts["historical_event_facts"]["week_end_exclusive"] == "2026-11-16"
    assert current.facts["current_weekly_reflection"]["trades"] == 1


def test_paper_bot_fallback_distinguishes_decision_from_execution():
    planned = module._fallback("bot_decision", "AAPL plan", {
        "symbol": "AAPL", "action": "buy", "status": "planned", "amount_eur": 400,
    })
    executed = module._fallback("bot_decision", "AAPL plan", {
        "symbol": "AAPL", "action": "buy", "status": "executed",
        "order_status": "filled", "amount_eur": 400,
    })
    assert "wil kopen" in planned["nl"]["title"]
    assert "nog niet bevestigd" in planned["nl"]["body"]
    assert "heeft gekocht" in executed["nl"]["title"]
    assert "€400,00" in executed["nl"]["body"]
    unverified = module._fallback("bot_decision", "AAPL plan", {
        "symbol": "AAPL", "action": "buy", "status": "executed",
        "order_status": None, "amount_eur": 400,
    })
    assert "gevulde Paper-order ontbreekt" in unverified["nl"]["body"]
    held = module._fallback("bot_decision", "AAPL plan", {
        "symbol": "AAPL", "action": "hold", "status": "planned",
    })
    assert "wacht" in held["nl"]["title"]
    assert "geen gemiste winst" in held["nl"]["body"]


def test_historical_paper_card_uses_owner_verified_filled_order_on_read():
    row = {
        "id": "11111111-1111-1111-1111-111111111111", "event_type": "bot_decision",
        "symbol": "AAPL", "evidence": {"symbol": "AAPL", "action": "buy",
            "status": "executed", "order_status": None, "amount_eur": 400},
        "copy_json": module._bot_fallback("AAPL", {"symbol": "AAPL",
            "action": "buy", "status": "executed", "order_status": None}),
        "verified_decision_status": "executed", "verified_order_status": "filled",
        "verified_decision_ts": datetime(2026, 11, 10, 14, tzinfo=timezone.utc),
        "verified_filled_amount_eur": 393.01, "created_at": None,
        "updated_at": None, "source_observed_at": datetime(2026, 11, 10, 14, tzinfo=timezone.utc), "expires_at": None,
        "fingerprint": "old", "copy_source": "verified_facts",
    }
    rendered = module.FinnCoachFeedService._serialize(row, "nl")
    assert "heeft gekocht" in rendered["title"]
    assert "€393,01" in rendered["description"]
    assert rendered["evidence"]["order_status"] == "filled"


def test_historical_paper_card_does_not_borrow_later_same_day_fill():
    old = datetime(2026, 11, 16, 6, 0, 18, tzinfo=timezone.utc)
    row = {
        "id": "11111111-1111-1111-1111-111111111111", "event_type": "bot_decision",
        "symbol": "AAPL", "evidence": {"symbol": "AAPL", "action": "hold",
            "status": "planned", "source_observed_at": old.isoformat()},
        "copy_json": module._bot_fallback("AAPL", {"symbol": "AAPL", "action": "hold",
            "status": "planned"}),
        "verified_decision_status": "executed", "verified_order_status": "filled",
        "verified_decision_ts": datetime(2026, 11, 16, 11, 45, 18, tzinfo=timezone.utc),
        "verified_filled_amount_eur": 393.01, "created_at": None,
        "updated_at": None, "source_observed_at": old, "expires_at": None,
    }
    rendered = module.FinnCoachFeedService._serialize(row, "nl")
    assert rendered["evidence"]["status"] == "planned"
    assert "wacht" in rendered["title"]
    assert "€393,01" not in rendered["description"]


def test_setup_feed_uses_owner_saved_pair_or_marks_pair_unset():
    base = {"id": "11111111-1111-1111-1111-111111111111", "event_type": "plan_review",
            "subject_type": "setup", "symbol": "BTC", "evidence": {},
            "copy_json": {"nl": {"title": "Beoordeling beperkt", "body": "Planupdate"}}}
    paired = module.FinnCoachFeedService._serialize({**base, "verified_setup_name": "BTC plan",
        "verified_setup_market_id": 17, "verified_setup_quote_currency": "EUR"}, "nl")
    assert paired["evidence"]["trading_pair"] == "BTC/EUR"
    assert paired["evidence"]["setup_name"] == "BTC plan"
    unpaired = module.FinnCoachFeedService._serialize({**base, "verified_setup_name": "BTC concept",
        "verified_setup_market_id": None, "verified_setup_quote_currency": None,
        "evidence": {"trading_pair": "BTC/USDT"}}, "nl")
    assert "trading_pair" not in unpaired["evidence"]
    assert unpaired["evidence"]["trading_pair_status"] == "not_saved_on_setup"


def test_single_setup_data_blocked_feed_uses_owner_saved_setup_context():
    row = {"id": "11111111-1111-1111-1111-111111111111", "event_type": "data_blocked",
           "subject_type": "asset", "subject_id": "BTC", "symbol": "BTC",
           "evidence": {"setup_ids": ["113"], "source_status": "stale_sources"},
           "copy_json": {"nl": {"title": "Beoordeling beperkt", "body": "Brondata ontbreekt"}},
           "verified_setup_name": "BTC basisplan", "verified_setup_market_id": 17,
           "verified_setup_quote_currency": "EUR"}
    rendered = module.FinnCoachFeedService._serialize(row, "nl")
    assert rendered["evidence"]["setup_name"] == "BTC basisplan"
    assert rendered["evidence"]["trading_pair"] == "BTC/EUR"
    assert rendered["evidence"]["setup_ids"] == ["113"]


def test_historical_paper_card_does_not_claim_execution_without_filled_order():
    row = {
        "id": "11111111-1111-1111-1111-111111111111", "event_type": "bot_decision",
        "symbol": "AAPL", "evidence": {"symbol": "AAPL", "action": "buy",
            "status": "executed", "order_status": None, "amount_eur": 400},
        "copy_json": module._bot_fallback("AAPL", {"symbol": "AAPL",
            "action": "buy", "status": "executed", "order_status": None}),
        "verified_decision_status": "executed", "verified_order_status": None,
        "verified_filled_amount_eur": None, "created_at": None,
        "updated_at": None, "source_observed_at": None, "expires_at": None,
        "fingerprint": "old", "copy_source": "verified_facts",
    }
    rendered = module.FinnCoachFeedService._serialize(row, "nl")
    assert "niet bevestigd" in rendered["title"]


def test_paper_feed_discussion_separates_historical_execution_from_current_quote():
    instruction = _feed_evidence_instruction([{
        "source": "owner_scoped_feed", "facts": {"event_type": "bot_decision",
            "historical_event_facts": {"status": "executed"}},
    }])
    assert "historical Paper bot decision" in instruction
    assert "Do not add or label a current market quote" in instruction
    assert "A later decision is not the answer to the selected card" in instruction


def test_paper_bot_fallback_covers_other_persisted_outcomes():
    for status in ("ready", "approved", "awaiting_exchange"):
        assert "wil kopen" in module._bot_fallback("AAPL plan", {
            "symbol": "AAPL", "action": "buy", "status": status,
        })["nl"]["title"]
    assert "kon niet kopen" in module._bot_fallback("AAPL plan", {
        "symbol": "AAPL", "action": "buy", "status": "failed",
    })["nl"]["title"]
    skipped = module._bot_fallback("AAPL plan", {
        "symbol": "AAPL", "action": "buy", "status": "skipped", "amount_eur": 400,
    })["nl"]
    assert "niet gekocht" in skipped["title"]
    assert "€400" not in skipped["body"]


def test_bot_copy_verifies_identity_amount_and_execution_boundary():
    evidence = {"symbol": "AAPL", "action": "buy", "status": "planned",
                "amount_eur": 400, "reasons": ["Score 50; setup 61–75"]}
    copy = {locale: {"title": f"AAPL Paper {locale}", "body": "AAPL bot plans to buy €400."}
            for locale in module.LOCALES}
    assert module._verified_bot_copy(copy, "AAPL plan", evidence)
    copy["nl"]["body"] = "AAPL bot heeft gekocht voor €400."
    assert not module._verified_bot_copy(copy, "AAPL plan", evidence)
    copy["nl"]["body"] = "AAPL bot plans to buy €900."
    assert not module._verified_bot_copy(copy, "AAPL plan", evidence)
    copy["nl"]["body"] = "AAPL koopt niet; er is geen koop gepland."
    assert not module._verified_bot_copy(copy, "AAPL plan", evidence)


def test_legacy_bot_copy_renders_factual_outcome():
    row = {"id": "00000000-0000-0000-0000-000000000001", "event_type": "bot_decision",
           "symbol": "AAPL", "evidence": {"subject": "AAPL plan", "symbol": "AAPL",
                                          "action": "buy", "status": "planned"},
           "copy_json": {"nl": {"title": "Paper-beslissing",
                                "body": "Voor AAPL plan is een Paper-beslissing vastgelegd."}}}
    rendered = module.FinnCoachFeedService._serialize(row, "nl")
    assert "wil kopen" in rendered["title"]
    assert "Paper-beslissing vastgelegd" not in rendered["description"]


def test_luna_writes_paper_outcome_from_typed_decision(monkeypatch):
    writes = []

    class Result:
        def first(self):
            return (1,)

    async def execute(_sql, params):
        writes.append(params)
        return Result()

    async def detail(_self, **_kwargs):
        return {"event_type": "bot_decision", "copy_source": "fact_fallback",
                "status": "unread", "fingerprint": "fingerprint", "source_observed_at": None,
                "evidence": {"subject": "AAPL plan", "symbol": "AAPL", "action": "buy",
                             "status": "executed", "order_status": "filled", "amount_eur": 400,
                             "reasons": ["Planvoorwaarden bereikt"]}}

    async def provider(**kwargs):
        assert kwargs["model_override"] == "gpt-6-luna"
        assert "executed" in kwargs["prompt"]
        return {"parsed": {
            "title_nl": "Je AAPL-bot heeft gekocht · Paper",
            "body_nl": "AAPL is gekocht voor €400. De planvoorwaarden waren bereikt.",
            "title_en": "Your AAPL bot bought · Paper",
            "body_en": "AAPL was bought for €400. The plan conditions were met.",
            "title_de": "Dein AAPL-Bot hat gekauft · Paper",
            "body_de": "AAPL wurde für €400 gekauft. Die Planbedingungen waren erfüllt.",
        }}

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr(module, "ask_gpt_structured_response_async", provider)
    session = SimpleNamespace(execute=execute, commit=AsyncMock())
    assert asyncio.run(module.FinnCoachFeedService(session).generate_copy(
        user_id=7, item_id="00000000-0000-0000-0000-000000000001"))
    assert any("copy" in params and "heeft gekocht" in params["copy"] for params in writes)


def test_active_feed_collapses_repeated_planned_decisions_but_keeps_history():
    class Result:
        def mappings(self):
            return self

        def all(self):
            return [
                {"id": f"00000000-0000-0000-0000-{number:012d}",
                 "event_type": "bot_decision", "subject_id": "bot-7", "symbol": "AAPL",
                 "evidence": {"subject": "AAPL plan", "action": "buy", "status": "planned",
                              "reasons": ["Planvoorwaarden bereikt"]},
                 "copy_json": {"nl": {"title": "AAPL Paper", "body": "Koopbeslissing voor AAPL."}}}
                for number in (2, 1)]

    async def execute(_sql, _params):
        return Result()

    service = module.FinnCoachFeedService(SimpleNamespace(execute=execute))
    assert len(asyncio.run(service.list(user_id=7))) == 1
    assert len(asyncio.run(service.list(user_id=7, history=True))) == 2


def test_history_cursor_queries_older_owner_items_in_stable_order():
    before = datetime(2026, 11, 16, 6, tzinfo=timezone.utc)
    cursor_id = "00000000-0000-0000-0000-000000000050"
    observed = {}

    class Result:
        def mappings(self):
            return self
        def all(self):
            return []

    async def execute(query, params):
        observed["query"] = str(query)
        observed["params"] = params
        return Result()

    service = module.FinnCoachFeedService(SimpleNamespace(execute=execute))
    assert asyncio.run(service.list(user_id=7, history=True, limit=51,
        before_created_at=before, before_id=cursor_id)) == []
    assert observed["params"]["user_id"] == 7
    assert observed["params"]["before_created_at"] == before
    assert observed["params"]["before_id"] == cursor_id
    assert "ELSE f.created_at END) < CAST(:before_created_at AS TIMESTAMPTZ)" in observed["query"]
    assert "f.id < CAST(:before_id AS UUID)" in observed["query"]
    assert "WHEN f.event_type='bot_decision'" in observed["query"]
    # Backfilled bot decisions can be created weeks after their visible event
    # date. Pagination must use the displayed decision time, not insertion time.
    assert observed["query"].count("COALESCE(f.source_observed_at, f.created_at)") == 4
    assert "GREATEST(f.created_at" not in observed["query"]
    assert "ELSE f.created_at" in observed["query"]
    assert "END DESC, f.id DESC" in observed["query"]


def test_paused_live_bot_feed_explains_deferred_execution_in_each_locale():
    copy = module._fallback("live_bot_paused", "BTC Live Later", {
        "status": "paused", "is_live": True, "is_active": False,
    })
    assert set(copy) == {"nl", "en", "de"}
    assert all("BTC Live Later" in item["body"] for item in copy.values())
    assert "geen orders" in copy["nl"]["body"]
    assert "No orders" in copy["en"]["body"]
    assert "keine Orders" in copy["de"]["body"]


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


def test_completed_feed_discussion_is_handled_after_saved_chat_reply(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000098"
    run = SimpleNamespace(
        id="run-c", user_id=7, conversation_id="conversation-c", status="planned",
        message="Wat betekent deze analyse?", trace_id="trace-c",
        client_context_json={"feed_item_id": item_id},
    )

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 7
        return {"id": item_id, "event_type": "analysis_ready",
                "subject_type": "asset", "subject_id": "71", "symbol": "BTC",
                "evidence": {"trading_pair": "BTC/USDT", "market_id": 34}}

    recorded = AsyncMock(return_value=True)
    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr(module.FinnCoachFeedService, "record_discussion_outcome", recorded)
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
        run_id="run-c", user_id=7, response_id="response-c",
        answer=FinnResponsesVerifiedAnswer("completed", "De benchmark is beschikbaar.", None, ()),
        locale="nl",
    ))

    recorded.assert_awaited_once_with(
        user_id=7, item_id=item_id, terminal_status="completed",
    )
    service._commit_session_if_possible.assert_awaited_once()


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

        async def for_asset(self, user_id, symbol, *, setups=None, market_id=None):
            assert (user_id, symbol) == (7, "ETH")
            return {"source_status": "stale_sources", "matches": [
                {"setup_id": 11, "name": "ETH Eigen Plan", "status": "insufficient_data"}]}

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", MatchService)
    monkeypatch.setattr(
        "backend.infrastructure.repositories.setup_repository.SetupRepository.get_setup_by_id",
        AsyncMock(return_value={"id": 11, "symbol": "ETH", "market_id": None}),
    )
    service = FinnV2ReasoningContextService(SimpleNamespace())
    historical, current = asyncio.run(service._current_feed_evidence(SimpleNamespace(
        user_id=7, client_context_json={"feed_item_id": item_id})))
    assert current.facts["current_setup"]["name"] == "ETH Eigen Plan"
    assert current.facts["current_setup"]["status"] == "insufficient_data"
    assert historical.facts["historical_notification"] is True
    assert historical.facts["selection_origin"] == "current_run"
    assert historical.facts["current_trade_signal_confirmed"] is False
    assert historical.facts["historical_event_facts"]["benchmark_score"] == 72
    assert historical.facts["historical_source_observed_at"] == "2026-10-10T10:00:00Z"
    assert historical.freshness == "historical"
    assert historical.as_of.isoformat() == "2026-10-10T10:00:00+00:00"
    assert current.freshness == "stale"


def test_strategy_next_step_discussion_sees_strategy_added_after_card(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000032"

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 7
        return {"id": item_id, "event_type": "strategy_next_step", "subject_type": "setup",
                "subject_id": "11", "symbol": "BTC", "status": "read",
                "source_observed_at": "2026-11-19T10:00:00Z",
                "evidence": {"setup_name": "BTC Plan", "market_id": 31,
                             "trading_pair": "BTC/USDT"}}

    class MatchService:
        last_source_row = {"calculated_at": datetime(2026, 11, 19, 11, tzinfo=timezone.utc)}

        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol, *, setups=None, market_id=None):
            assert (user_id, symbol, market_id) == (7, "BTC", 31)
            return {"source_status": "available", "benchmark_score": 54,
                    "as_of": "2026-11-19", "matches": []}

    class Rows:
        def mappings(self):
            return self

        def first(self):
            return {"id": 91, "name": "BTC Strategie", "setup_type": "trade",
                    "execution_ready": "false"}

    class Session:
        async def execute(self, query, params):
            assert "FROM strategies" in str(query)
            assert params == {"user_id": 7, "setup_id": 11}
            return Rows()

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", MatchService)
    monkeypatch.setattr(
        "backend.infrastructure.repositories.setup_repository.SetupRepository.get_setup_by_id",
        AsyncMock(return_value={"id": 11, "name": "BTC Plan", "symbol": "BTC",
                                "market_id": 31, "quote_currency": "USDT"}),
    )
    historical, current = asyncio.run(FinnV2ReasoningContextService(Session())._current_feed_evidence(
        SimpleNamespace(user_id=7, client_context_json={"feed_item_id": item_id})))
    assert historical.facts["historical_notification"] is True
    assert current.facts["current_linked_strategy"] == {
        "id": 91, "name": "BTC Strategie", "setup_type": "trade",
        "execution_ready_status": "draft",
    }
    assert current.facts["current_benchmark_score"] == 54


def test_paper_next_step_discussion_sees_bot_added_after_card(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000033"

    async def detail(_self, *, user_id, item_id: str):
        return {"id": item_id, "event_type": "paper_next_step", "subject_type": "setup",
                "subject_id": "11", "symbol": "BTC", "status": "read",
                "evidence": {"setup_name": "BTC Plan", "strategy_id": 91,
                             "market_id": 31, "trading_pair": "BTC/USDT"}}

    class MatchService:
        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol, *, setups=None, market_id=None):
            return {"source_status": "available", "benchmark_score": 54,
                    "as_of": "2026-11-19", "matches": []}

    class Rows:
        def __init__(self, row):
            self.row = row

        def mappings(self):
            return self

        def first(self):
            return self.row

    class Session:
        async def execute(self, query, params):
            assert params == {"user_id": 7, "setup_id": 11}
            sql = str(query)
            if "FROM strategies" in sql:
                return Rows({"id": 91, "name": "BTC Strategie", "setup_type": "trade",
                             "execution_ready": "false"})
            if "FROM bot_configs b" in sql:
                assert "s.user_id=b.user_id" in sql
                return Rows({"id": 123, "name": "Paper bot", "is_live": False,
                             "is_active": False})
            raise AssertionError(sql)

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", MatchService)
    monkeypatch.setattr(
        "backend.infrastructure.repositories.setup_repository.SetupRepository.get_setup_by_id",
        AsyncMock(return_value={"id": 11, "name": "BTC Plan", "symbol": "BTC",
                                "market_id": 31, "quote_currency": "USDT"}),
    )
    historical, current = asyncio.run(FinnV2ReasoningContextService(Session())._current_feed_evidence(
        SimpleNamespace(user_id=7, client_context_json={"feed_item_id": item_id})))
    assert historical.facts["historical_notification"] is True
    assert current.facts["current_linked_bot"] == {
        "id": 123, "name": "Paper bot", "is_live": False, "is_active": False,
    }


def test_data_blocked_single_saved_setup_keeps_identity_when_match_unavailable(monkeypatch):
    item_id = "00000000-0000-0000-0000-000000000022"

    async def detail(_self, *, user_id, item_id: str):
        assert user_id == 7
        return {"id": item_id, "event_type": "data_blocked", "subject_type": "asset",
                "subject_id": "BTC", "symbol": "BTC", "status": "read",
                "source_observed_at": "2026-11-16T06:00:00Z",
                "evidence": {"setup_ids": [11], "setup_name": "BTC Plan",
                             "trading_pair": "BTC/USDT"}}

    class MatchService:
        def __init__(self, _session):
            pass

        async def for_asset(self, user_id, symbol, *, setups=None, market_id=None):
            assert (user_id, symbol, market_id) == (7, "BTC", 31)
            assert setups[0]["id"] == 11
            return {"source_status": "stale_sources", "matches": [],
                    "component_source_status": {"macro": "missing"}}

    monkeypatch.setattr(module.FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", MatchService)
    monkeypatch.setattr(
        "backend.infrastructure.repositories.setup_repository.SetupRepository.get_setup_by_id",
        AsyncMock(return_value={"id": 11, "name": "BTC Plan", "symbol": "BTC",
                                "market_id": 31, "quote_currency": "USDT"}),
    )
    historical, current = asyncio.run(FinnV2ReasoningContextService(SimpleNamespace())._current_feed_evidence(
        SimpleNamespace(user_id=7, client_context_json={"feed_item_id": item_id})))
    assert historical.facts["historical_event_facts"]["trading_pair"] == "BTC/USDT"
    assert current.facts["current_setup"] == {
        "id": 11, "name": "BTC Plan", "status": "not_assessed",
        "trading_pair": "BTC/USDT", "trading_pair_status": "saved",
    }


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

        async def get_latest_quoted_snapshot(self, _symbol):
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


@pytest.mark.parametrize("newer", [True, False])
def test_repeated_paper_decision_refreshes_only_newer_visible_assessment(newer):
    first_at = datetime(2026, 11, 16, 15, 15, tzinfo=timezone.utc)
    observed_at = first_at + (timedelta(hours=2, minutes=45) if newer else -timedelta(minutes=15))
    digest = hashlib.sha256("hold:planned:None:0:[]".encode()).hexdigest()
    statements = []

    class Result:
        def mappings(self):
            return self

        def first(self):
            return {"id": "11111111-1111-1111-1111-111111111111", "fingerprint": digest,
                    "status": "unread", "source_observed_at": first_at}

    class Session:
        async def execute(self, sql, params):
            statements.append((str(sql), params))
            return Result()

    created = asyncio.run(module.FinnCoachFeedService(Session()).publish(
        user_id=7, event_key="bot-decision:23", event_type="bot_decision",
        subject_type="bot", subject_id="9", subject="AAPL bot", symbol="AAPL",
        evidence={"action": "hold", "status": "planned", "decision_id": 23,
                  "source_observed_at": observed_at},
        source_observed_at=observed_at, expires_at=observed_at + timedelta(days=2),
        revision="hold:planned:None:0:[]",
    ))
    assert created is None
    updates = [(sql, params) for sql, params in statements if "UPDATE finn_coach_feed_items" in sql]
    assert len(updates) == int(newer)
    if newer:
        assert updates[0][1]["source_observed_at"] == observed_at
        assert json.loads(updates[0][1]["evidence"])["decision_id"] == 23
    assert not any("INSERT INTO finn_coach_feed_items" in sql for sql, _ in statements)


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
