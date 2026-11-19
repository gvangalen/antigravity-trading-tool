import asyncio
import hashlib
import json
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone


def test_paper_risk_feed_uses_saved_limit_and_verified_bot_valuation(monkeypatch):
    from backend.infrastructure.repositories.bot_repository import BotRepository
    from backend.services.finn_coach_feed_service import FinnCoachFeedService, _fallback

    observed = datetime.now(timezone.utc)
    rows = [
        {"bot_id": 7, "name": "BTC-bot", "symbol": "BTC", "cash": 30,
         "qty": 1, "position_value": 70, "invested": 65, "is_live": False,
         "portfolio_initialized": True, "price_available": True,
         "price_quote_currency": "USDT", "fx_as_of": observed,
         "price_as_of": observed, "source_price_as_of": observed},
        {"bot_id": 8, "name": "ETH-bot", "symbol": "ETH", "cash": 60,
         "qty": 1, "position_value": 40, "invested": 35, "is_live": False,
         "portfolio_initialized": True, "price_available": True,
         "price_quote_currency": "USDT", "fx_as_of": observed,
         "price_as_of": observed, "source_price_as_of": observed},
        {"bot_id": 9, "name": "SOL-bot", "symbol": "SOL", "cash": 10,
         "qty": 1, "position_value": None, "invested": 10, "is_live": False,
         "portfolio_initialized": True, "price_available": False},
        {"bot_id": 10, "name": "Old-bot", "symbol": "AAPL", "cash": 10,
         "qty": 1, "position_value": 90, "invested": 80, "is_live": False,
         "portfolio_initialized": True, "price_available": True,
         "price_quote_currency": "EUR",
         "price_as_of": observed - timedelta(hours=2),
         "source_price_as_of": observed - timedelta(hours=2)},
        {"bot_id": 11, "name": "Skewed-bot", "symbol": "BTC", "cash": 10,
         "qty": 1, "position_value": 90, "invested": 80, "is_live": False,
         "portfolio_initialized": True, "price_available": True,
         "price_quote_currency": "USDT",
         "price_as_of": observed - timedelta(minutes=119),
         "source_price_as_of": observed,
         "fx_as_of": observed - timedelta(minutes=119)},
    ]

    class Result:
        def mappings(self):
            return self

        def all(self):
            return [
                {"id": 7, "max_asset_exposure_pct": 50, "market_id": 23,
                 "quote_currency": "USDT"},
                {"id": 8, "max_asset_exposure_pct": 50, "market_id": 24,
                 "quote_currency": "USDT"},
                {"id": 9, "max_asset_exposure_pct": 50, "market_id": 25,
                 "quote_currency": "USDT"},
                {"id": 10, "max_asset_exposure_pct": 50, "market_id": None,
                 "quote_currency": None},
                {"id": 11, "max_asset_exposure_pct": 50, "market_id": 26,
                 "quote_currency": "USDT"},
            ]

    class Session:
        async def execute(self, statement, params):
            assert params == {"user_id": 42}
            if "finn_coach_feed_items" in str(statement):
                return type("Existing", (), {"mappings": lambda self: self,
                    "all": lambda self: [{"event_key": "position-risk:99"}]})()
            return Result()

    async def context(self, user_id):
        assert user_id == 42
        return {"bots": rows, "read_at": observed}

    published, resolved = [], []

    async def publish(self, **kwargs):
        published.append(kwargs)
        return "feed-1"

    async def resolve(self, **kwargs):
        resolved.append(kwargs["event_key"])

    monkeypatch.setattr(BotRepository, "get_portfolio_intelligence_context", context)
    monkeypatch.setattr(FinnCoachFeedService, "publish", publish)
    monkeypatch.setattr(FinnCoachFeedService, "resolve_position_risk", resolve)

    created = asyncio.run(FinnCoachFeedService(Session()).reconcile_paper_position_risks(user_id=42))

    assert created == ["feed-1"]
    assert resolved == ["position-risk:99", "position-risk:8", "position-risk:9",
                        "position-risk:10", "position-risk:11"]
    assert len(published) == 1
    alert = published[0]
    assert alert["event_type"] == "position_risk"
    assert alert["event_key"] == "position-risk:7"
    assert alert["evidence"]["trading_pair"] == "BTC/USDT"
    assert alert["evidence"]["exposure_pct"] == 70
    assert alert["evidence"]["limit_pct"] == 50
    assert alert["source_observed_at"] == observed
    assert "Er is niets gewijzigd" in _fallback("position_risk", "BTC-bot", alert["evidence"])["nl"]["body"]


def test_paper_risk_review_has_independent_owner_dispatch_schedule():
    from backend.celery_task.celery_app import celery_app
    from backend.celery_task.queue_policy import DISPATCHER_TASK_NAME

    entry = celery_app.conf.beat_schedule["dispatch_paper_position_risks"]
    assert entry["task"] == DISPATCHER_TASK_NAME
    assert entry["kwargs"]["task_name"] == (
        "backend.celery_task.portfolio_snapshot_task.reconcile_paper_position_risk")


def test_retryable_paper_risk_task_reports_its_own_outcome(monkeypatch):
    from backend.celery_task import finn_v2_task, portfolio_snapshot_task
    from backend.infrastructure import database
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    events = []

    class Session:
        async def commit(self):
            events.append("feed_committed")

    @asynccontextmanager
    async def session_factory():
        yield Session()

    async def review(self, *, user_id):
        events.append(("review", user_id))
        return []

    monkeypatch.setattr(database, "async_session_factory", session_factory)
    monkeypatch.setattr(finn_v2_task, "_run_async", lambda coro: asyncio.run(coro))
    monkeypatch.setattr(FinnCoachFeedService, "reconcile_paper_position_risks", review)

    result = portfolio_snapshot_task.reconcile_paper_position_risk.run(42)

    assert result == {"status": "ok", "user_id": 42, "created_count": 0}
    assert events == [("review", 42), "feed_committed"]


def test_discuss_paper_risk_rereads_current_position_in_same_owner(monkeypatch):
    from types import SimpleNamespace

    from backend.services.finn_coach_feed_service import FinnCoachFeedService
    from backend.services.finn_v2_reasoning_context_service import FinnV2ReasoningContextService
    from backend.services.paper_position_risk_service import PaperPositionRiskService

    item_id = "00000000-0000-0000-0000-000000000123"

    async def detail(self, *, user_id, item_id):
        assert user_id == 42
        return {"event_type": "position_risk", "subject_type": "bot",
                "subject_id": "7", "symbol": "BTC", "status": "read",
                "source_observed_at": "2026-11-14T10:00:00Z",
                "evidence": {"status": "above_saved_limit", "exposure_pct": 70,
                             "limit_pct": 50, "trading_pair": "BTC/USDT"}}

    async def evaluate(self, user_id):
        assert user_id == 42
        return {7: {"status": "within_limit", "exposure_pct": 40,
                    "limit_pct": 50,
                    "valuation_as_of": datetime(2026, 11, 15, 10, tzinfo=timezone.utc)}}

    monkeypatch.setattr(FinnCoachFeedService, "detail", detail)
    monkeypatch.setattr(PaperPositionRiskService, "evaluate", evaluate)

    historical, current = asyncio.run(
        FinnV2ReasoningContextService(SimpleNamespace())._current_feed_evidence(
            SimpleNamespace(user_id=42, client_context_json={"feed_item_id": item_id})))

    assert historical.facts["historical_event_facts"]["exposure_pct"] == 70
    assert current.facts["current_position_risk"]["exposure_pct"] == 40
    assert current.facts["current_position_risk"]["status"] == "within_limit"
    assert current.facts["current_position_risk"]["valuation_as_of"] == "2026-11-15T10:00:00+00:00"
    json.dumps([historical.facts, current.facts])
    assert current.source == "owner_scoped_current_paper_portfolio"
    assert current.facts["current_trade_signal_confirmed"] is False


def test_clicked_paper_risk_card_answers_from_current_owner_read_without_model():
    from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor
    from backend.services.finn_v2_responses_answer_verifier import FinnResponsesAnswerVerifier

    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=42,
                                   run_id="selected-risk-test", model_led_coach=True)
    evidence = [
        {"source": "owner_scoped_feed", "facts": {
            "feed_item_id": "risk-1", "event_type": "position_risk", "symbol": "BTC",
            "historical_notification": True, "selection_origin": "current_run",
            "historical_event_facts": {"limit_pct": 50, "exposure_pct": 70}}},
        {"source": "owner_scoped_current_paper_portfolio", "facts": {
            "feed_item_id": "risk-1", "current_position_risk": {
                "symbol": "BTC", "trading_pair": "BTC/USDT", "status": "above_saved_limit",
                "limit_pct": 50, "exposure_pct": 70,
                "valuation_as_of": "2026-11-19T11:00:00+00:00"}}},
    ]
    message = ("Bespreek dit positierisico voor mijn BTC Paper-bot. Welke opgeslagen "
               "limiet is overschreden en wat controleer ik? Wijzig niets en plaats geen order.")
    response = asyncio.run(front.run(message=message, instructions="", conversation_context={},
                                     verified_asset="BTC", locale="nl", feed_evidence=evidence))
    assert "BTC/USDT" in response.response.text
    assert "70%" in response.response.text and "50%" in response.response.text
    assert "koers- en FX-bron" in response.response.text
    assert "plaats geen order" in response.response.text
    json.dumps(list(response.response.tool_trace))
    verified = asyncio.run(FinnResponsesAnswerVerifier().verify(
        message=message, result=response.response, locale="nl"))
    assert verified.status == "completed", (verified.reason, verified.rejection_details)


def test_clicked_paper_risk_card_does_not_reuse_historical_exposure_if_current_read_is_unavailable():
    from backend.services.finn_v2_factual_source_answer import render_selected_paper_position_risk

    result = {"results": [{"scope": "read_selected_paper_position_risk", "status": "completed",
        "data": {"historical": {"limit_pct": 50, "exposure_pct": 70}, "current": {
            "symbol": "BTC", "trading_pair": "BTC/USDT", "status": "unavailable",
            "limit_pct": 50, "exposure_pct": None}}}]}
    answer = render_selected_paper_position_risk(result, symbol="BTC")
    assert "geen bruikbare, gedateerde Paper-waardering" in answer
    assert "70%" not in answer


def test_historical_paper_exit_checks_current_owner_portfolio_quantity():
    from backend.services.finn_v2_factual_source_answer import render_paper_exit_position_status

    def read(quantity):
        return {"results": [{"scope": "read_portfolio", "status": "completed",
            "data": {"environment": "paper", "read_at": "2026-11-19T15:00:00+00:00",
                     "bots": [{"symbol": "AAPL", "is_live": False,
                               "position_qty": quantity}]}}]}

    closed = render_paper_exit_position_status(read(0), symbol="AAPL")
    still_open = render_paper_exit_position_status(read(1.5), symbol="AAPL")
    assert "geen open positie meer" in closed
    assert "nog 1,5 AAPL open" in still_open
    assert "Europe/Amsterdam" in closed
    assert "gevulde verkoop alleen" in closed
    assert "niet eenduidig" in render_paper_exit_position_status({"results": [{
        "scope": "read_portfolio", "status": "completed", "data": {
            "environment": "paper", "read_at": "2026-11-19T15:00:00+00:00",
            "bots": [{"symbol": "AAPL", "is_live": False, "position_qty": 0},
                     {"symbol": "AAPL", "is_live": False, "position_qty": 1}],
        }}]}, symbol="AAPL")


def test_paper_exit_followup_reads_current_portfolio_before_claiming_closure():
    from backend.services.finn_v2_responses_front_door import FinnResponsesFrontDoor

    front = FinnResponsesFrontDoor(client=object(), session=object(), user_id=42,
                                   run_id="paper-exit-followup", model_led_coach=True)
    calls = []

    async def read(call):
        calls.append(call)
        return {"status": "completed", "results": [{"scope": "read_portfolio",
            "status": "completed", "data": {"environment": "paper",
                "read_at": "2026-11-19T15:00:00+00:00", "bots": [{
                    "symbol": "AAPL", "is_live": False, "position_qty": 0,
                }]}}]}

    front.reads = read
    result = asyncio.run(front.run(
        message="Is de AAPL-positie echt gesloten na die Paper-exit?",
        instructions="", conversation_context={}, verified_asset="AAPL", locale="nl",
    ))
    assert len(calls) == 1
    assert calls[0].read_tools == ("read_portfolio",)
    assert calls[0].inputs == {"environment": "paper"}
    assert "geen open positie meer" in result.response.text
    assert "Paper-portefeuille" in result.response.text


def test_active_risk_card_updates_and_only_worsening_reopens_handled_alert():
    from backend.services.finn_coach_feed_service import FinnCoachFeedService

    observed = datetime.now(timezone.utc)
    first_revision = "7:50.00:above_saved_limit"
    first_digest = hashlib.sha256(first_revision.encode()).hexdigest()

    class Result:
        def __init__(self, row=None):
            self.row = row

        def mappings(self):
            return self

        def first(self):
            return self.row

    class Session:
        def __init__(self, fingerprint, *, status="unread", prior_exposure=51):
            self.fingerprint = fingerprint
            self.status = status
            self.prior_exposure = prior_exposure
            self.statements = []

        async def execute(self, statement, params):
            sql = str(statement)
            self.statements.append((sql, params))
            if "SELECT id, fingerprint" in sql:
                return Result({"id": "00000000-0000-0000-0000-000000000001",
                               "fingerprint": self.fingerprint, "status": self.status,
                               "source_observed_at": observed - timedelta(minutes=5),
                               "evidence": {"exposure_pct": self.prior_exposure,
                                            "alert_peak_pct": self.prior_exposure}})
            return Result(("new-event",))

    def publish(session, exposure, revision):
        return asyncio.run(FinnCoachFeedService(session).publish(
            user_id=42, event_key="position-risk:7", event_type="position_risk",
            subject_type="bot", subject_id="7", subject="BTC-bot", symbol="BTC",
            evidence={"status": "above_saved_limit", "symbol": "BTC",
                      "trading_pair": "BTC/USDT", "exposure_pct": exposure,
                      "limit_pct": 50},
            source_observed_at=observed,
            expires_at=observed + timedelta(hours=1), revision=revision))

    same_band = Session(first_digest)
    assert publish(same_band, 59, first_revision) is None
    updates = [(sql, params) for sql, params in same_band.statements
               if "UPDATE finn_coach_feed_items" in sql]
    assert len(updates) == 1
    assert json.loads(updates[0][1]["evidence"])["exposure_pct"] == 59
    assert not any("INSERT INTO finn_coach_feed_items" in sql for sql, _ in same_band.statements)

    improving = Session(first_digest, status="handled", prior_exposure=90)
    assert publish(improving, 70, first_revision) is None
    assert not any("INSERT INTO finn_coach_feed_items" in sql for sql, _ in improving.statements)

    worsening = Session(first_digest, status="handled", prior_exposure=90)
    assert publish(worsening, 100, first_revision) == "new-event"
    assert any("INSERT INTO finn_coach_feed_items" in sql for sql, _ in worsening.statements)

    new_episode = Session(f"resolved:{first_digest}", status="handled", prior_exposure=90)
    assert publish(new_episode, 70, first_revision) == "new-event"
    assert any("INSERT INTO finn_coach_feed_items" in sql for sql, _ in new_episode.statements)
