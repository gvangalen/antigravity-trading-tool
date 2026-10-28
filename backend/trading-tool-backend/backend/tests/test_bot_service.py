import asyncio
import json
from decimal import Decimal
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from datetime import date, datetime, timedelta, timezone

from backend.schemas.bot_schema import BotConfigCreateSchema, BotConfigUpdateSchema, BotManualOrderSchema
from backend.domain.finn_dca_plan_contract import split_confirmed_dca_plan
from backend.services.bot_service import BotService, _dca_schedule_status


def test_paper_price_reads_saved_exact_market_only():
    now = datetime.now(timezone.utc)
    service = BotService(_FakeSession())
    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {"symbol": "ETH", "market_id": 73, "quote_currency": "EUR", "is_live": False}
        async def get_valuatable_exact_market_prices(self, market_ids):
            assert market_ids == [73]
            return {73: {"symbol": "ETH", "quote_currency": "EUR", "price": 2100,
                         "source_observed_at": now}}
        async def get_valuatable_market_prices(self, symbols):
            raise AssertionError("legacy base price must not be read")
        async def get_portfolio_fx_rates(self):
            return {}
    service.repository = Repo()
    result = asyncio.run(service.get_paper_price_eur(7, 9))
    assert result["price_eur"] == 2100
    assert result["quote_currency"] == "EUR"


def test_paper_price_rejects_mismatched_exact_market_row():
    service = BotService(_FakeSession())
    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {"symbol": "ETH", "market_id": 73, "quote_currency": "EUR", "is_live": False}
        async def get_valuatable_exact_market_prices(self, market_ids):
            return {73: {"symbol": "ETH", "quote_currency": "USDT", "price": 2100,
                         "observed_at": datetime.now(timezone.utc)}}
    service.repository = Repo()
    with pytest.raises(HTTPException) as error:
        asyncio.run(service.get_paper_price_eur(7, 9))
    assert error.value.status_code == 409


def test_legacy_empty_reason_object_is_not_shown_as_literal_json():
    class Repo:
        async def get_bot_history(self, user_id, start, end):
            assert user_id == 7
            return [{
                "id": 11, "bot_id": 3, "bot_name": "Paper", "symbol": "ETH",
                "decision_date": end, "decision_ts": None, "action": "buy",
                "confidence": "medium", "amount_eur": 1.25,
                "scores_json": "{}", "reason_json": "{}", "status": "executed",
            }, {
                "id": 12, "bot_id": 3, "bot_name": "Paper", "symbol": "ETH",
                "decision_date": end, "decision_ts": None, "action": "hold",
                "confidence": "medium", "amount_eur": 0,
                "scores_json": "{}", "reason_json": '{"reason":"Daglimiet bereikt"}',
                "status": "blocked",
            }]

    service = BotService(_FakeSession())
    service.repository = Repo()
    history = asyncio.run(service.get_bot_history(7, 30))
    assert history[0]["reasons"] == []
    assert history[1]["reasons"] == ["Daglimiet bereikt"]


def test_history_keeps_saved_reduction_and_check_time_without_marking_it_stale():
    checked = datetime.now(timezone.utc) - timedelta(days=3)

    class Repo:
        async def get_bot_history(self, user_id, start, end):
            return [{
                "id": 25, "bot_id": 3, "bot_name": "Paper", "is_live": False,
                "symbol": "ETH", "decision_date": checked.date(), "decision_ts": checked,
                "action": "buy", "confidence": "medium", "amount_eur": 40,
                "scores_json": json.dumps({
                    "guardrails_checked_at": checked.isoformat(),
                    "guardrails_result": {
                        "allowed": True, "original_amount_eur": 100,
                        "adjusted_amount_eur": 40, "blocked_by": None,
                        "explanations": [{"code": "daily_allocation_trimmed", "from_amount_eur": 100, "to_amount_eur": 40}],
                    },
                }),
                "reason_json": "[]", "status": "planned",
            }]

    service = BotService(_FakeSession())
    service.repository = Repo()
    row = asyncio.run(service.get_bot_history(7, 30))[0]
    assert row["safety_check"]["state"] == "reduced"
    assert row["safety_check"]["reason_code"] == "daily_allocation_trimmed"
    assert row["safety_check"]["proposed_amount_eur"] == 100
    assert row["safety_check"]["allowed_amount_eur"] == 40
    assert row["safety_check"]["checked_at"] == checked.isoformat()


def test_removing_optional_paper_limit_requires_risk_acknowledgement():
    service = BotService.__new__(BotService)
    existing = {"id": 3, "is_live": False, "mode": "manual", "budget_daily_limit_eur": 50}
    merged = {**existing, "budget_daily_limit_eur": 0}
    event = service._bot_update_pressure_event(existing, merged, {"budget_daily_limit_eur": 0})
    assert event and "uitgeschakeld" in event["reasons"][0]


def test_legacy_reduced_safety_without_explanations_stays_readable():
    service = BotService.__new__(BotService)
    safety = service._safety_contract({
        "id": 30, "bot_id": 3, "status": "planned",
        "guardrails_result": {
            "allowed": True, "original_amount_eur": 100,
            "adjusted_amount_eur": 50,
        },
    }, is_live=False, historical=True)
    assert safety["state"] == "reduced"
    assert safety["reason_code"] == "reduced"


def test_manual_confirmed_fill_stays_successful_if_snapshot_fails(monkeypatch):
    calls = []

    def confirmed_fill(user_id, bot_id, decision_id):
        calls.append((user_id, bot_id, decision_id))

    def failed_snapshot(_user_id):
        raise RuntimeError("snapshot unavailable")

    monkeypatch.setattr("backend.services.bot_service.sync_execute_manual_decision", confirmed_fill)
    monkeypatch.setattr("backend.services.bot_service.sync_snapshot_all_for_user", failed_snapshot)
    result = asyncio.run(BotService(_FakeSession()).mark_bot_executed(2, 3, 1))
    assert calls == [(1, 2, 3)]
    assert result["ok"] is True
    assert result["snapshot_updated"] is False


def test_bot_today_uses_verified_score_2_components_without_changing_decisions(monkeypatch):
    class Repo:
        async def get_active_bots_with_setups(self, user_id):
            return [{"id": 8, "name": "Paper", "symbol": "ETH", "timeframe": "1D",
                     "setup_type": "dca", "setup_name": "ETH DCA"}]

        async def get_bot_decisions_by_date(self, user_id, day):
            return []

        async def get_daily_scores_row(self, *args):
            raise AssertionError("raw daily scores must not drive the bot summary")

    calls = []

    async def verified(self, user_id, symbol, *, setups=None):
        calls.append((user_id, symbol, setups))
        return {"reported_scores": {"macro_score": None, "technical_score": 40,
                                     "market_score": 30}}

    monkeypatch.setattr(
        "backend.services.setup_market_match_service.SetupMarketMatchService.for_asset",
        verified,
    )
    service = BotService(_FakeSession())
    service.repository = Repo()

    result = asyncio.run(service.get_bot_today(7, "ETH", lean=True))

    assert calls == [(7, "ETH", [])]
    assert result["scores"] == {"macro": None, "technical": 40,
                                "market": 30, "setup": None}
    assert result["decisions"] == []


def test_bot_today_does_not_relabel_an_old_decision_score_as_current(monkeypatch):
    class Repo:
        async def get_active_bots_with_setups(self, user_id):
            return [{"id": 8, "name": "Paper", "symbol": "ETH", "timeframe": "1D",
                     "setup_type": "trade", "setup_name": "ETH Plan"}]

        async def get_bot_decisions_by_date(self, user_id, day):
            return [{"id": 12, "bot_id": 8, "symbol": "ETH", "action": "hold",
                     "confidence": "low", "scores_json": json.dumps({
                         "macro": 10, "market": 10, "technical": 10,
                         "combined": 10, "setup_match": {"score": 10},
                     }), "reason_json": "[]", "setup_id": 9, "strategy_id": 10,
                     "status": "planned", "created_at": None, "updated_at": None}]

    async def verified(self, user_id, symbol, *, setups=None):
        return {"reported_scores": {"macro_score": None, "technical_score": 40,
                                     "market_score": 30}}

    monkeypatch.setattr(
        "backend.services.setup_market_match_service.SetupMarketMatchService.for_asset", verified,
    )
    service = BotService(_FakeSession())
    service.repository = Repo()

    result = asyncio.run(service.get_bot_today(7, "ETH", lean=True))

    assert result["scores"]["market"] == 30
    old = result["decisions"][0]
    assert old["action"] == "hold"
    assert old["scores_json"]["score_semantics"] == "legacy_unverified"
    assert old["scores_json"]["market"] is None
    assert old["scores_json"]["combined"] is None
    assert old["setup_match"] is None


def test_bot_today_does_not_show_decision_for_previous_setup_revision(monkeypatch):
    decision_at = datetime(2026, 10, 11, 10, 0)

    class Repo:
        async def get_active_bots_with_setups(self, user_id):
            return [{"id": 8, "name": "Paper", "symbol": "ETH", "timeframe": "1D",
                     "setup_type": "trade", "setup_name": "ETH Plan", "setup_id": 9,
                     "setup_last_validated": decision_at + timedelta(minutes=5)}]

        async def get_bot_decisions_by_date(self, user_id, day):
            return [{"id": 12, "bot_id": 8, "symbol": "ETH", "action": "hold",
                     "decision_ts": decision_at, "setup_id": 9, "strategy_id": 10,
                     "scores_json": json.dumps({"score_semantics": "verified_score_2",
                                                  "setup_match": {"status": "outside_conditions"}}),
                     "reason_json": "[]", "created_at": decision_at}]

    async def verified(self, user_id, symbol, *, setups=None):
        return {"reported_scores": {"macro_score": 20, "technical_score": 50,
                                     "market_score": 30}}

    monkeypatch.setattr(
        "backend.services.setup_market_match_service.SetupMarketMatchService.for_asset", verified,
    )
    service = BotService(_FakeSession())
    service.repository = Repo()

    result = asyncio.run(service.get_bot_today(7, "ETH", lean=True))

    assert result["scores"]["macro"] == 20
    decision = result["decisions"][0]
    assert decision["decision_stale"] is True
    assert decision["action"] is None
    assert decision["setup_match"] is None
    assert decision["guardrails_result"] is None


def test_bot_today_marks_pre_funding_hold_as_previous_decision(monkeypatch):
    decision_at = datetime(2026, 10, 11, 10, 0)

    class Repo:
        async def get_active_bots_with_setups(self, user_id):
            return [{"id": 8, "name": "Paper", "symbol": "ETH", "timeframe": "1D",
                     "setup_type": "trade", "setup_name": "ETH Plan", "setup_id": 9,
                     "strategy_id": 10, "setup_last_validated": None,
                     "bot_updated_at": decision_at + timedelta(minutes=5)}]

        async def get_bot_decisions_by_date(self, user_id, day):
            return [{"id": 12, "bot_id": 8, "symbol": "ETH", "action": "hold",
                     "status": "planned", "decision_ts": decision_at,
                     "setup_id": 9, "strategy_id": 10,
                     "scores_json": json.dumps({"score_semantics": "verified_score_2"}),
                     "created_at": decision_at}]

    async def verified(self, user_id, symbol, *, setups=None):
        return {"reported_scores": {"macro_score": 20, "technical_score": 40,
                                     "market_score": 40}}

    monkeypatch.setattr(
        "backend.services.setup_market_match_service.SetupMarketMatchService.for_asset", verified,
    )
    service = BotService(_FakeSession())
    service.repository = Repo()

    decision = asyncio.run(service.get_bot_today(7, "ETH", lean=True))["decisions"][0]

    assert decision["decision_stale"] is True
    assert decision["action"] is None
    assert decision["previous_decision_at"] == decision_at.isoformat()


def test_bot_today_prefers_recorded_setup_revision_over_decision_timestamp(monkeypatch):
    decision_at = datetime(2026, 10, 11, 10, 10)
    setup_revision = datetime(2026, 10, 11, 10, 5)

    class Repo:
        async def get_active_bots_with_setups(self, user_id):
            return [{"id": 8, "name": "Paper", "symbol": "ETH", "timeframe": "1D",
                     "setup_type": "trade", "setup_name": "ETH Plan", "setup_id": 9,
                     "setup_last_validated": setup_revision}]

        async def get_bot_decisions_by_date(self, user_id, day):
            return [{"id": 12, "bot_id": 8, "symbol": "ETH", "action": "buy",
                     "decision_ts": decision_at, "setup_id": 9, "strategy_id": 10,
                     "scores_json": json.dumps({"score_semantics": "verified_score_2",
                                                  "setup_revision": datetime(2026, 10, 11, 10, 0).isoformat()}),
                     "reason_json": "[]", "created_at": decision_at}]

    async def verified(self, user_id, symbol, *, setups=None):
        return {"reported_scores": {"macro_score": 20, "technical_score": 50,
                                     "market_score": 30}}

    monkeypatch.setattr(
        "backend.services.setup_market_match_service.SetupMarketMatchService.for_asset", verified,
    )
    service = BotService(_FakeSession())
    service.repository = Repo()

    decision = asyncio.run(service.get_bot_today(7, "ETH", lean=True))["decisions"][0]

    assert decision["decision_stale"] is True
    assert decision["action"] is None


def test_bot_today_hides_old_decision_after_strategy_relink(monkeypatch):
    class Repo:
        async def get_active_bots_with_setups(self, user_id):
            return [{"id": 8, "name": "Paper", "symbol": "ETH", "timeframe": "1D",
                     "setup_type": "trade", "setup_name": "ETH Plan", "setup_id": 9,
                     "strategy_id": 11, "setup_last_validated": None}]

        async def get_bot_decisions_by_date(self, user_id, day):
            return [{"id": 12, "bot_id": 8, "symbol": "ETH", "action": "buy",
                     "decision_ts": datetime(2026, 10, 11, 10, 10),
                     "setup_id": 9, "strategy_id": 10,
                     "scores_json": json.dumps({"score_semantics": "verified_score_2",
                                                  "setup_revision": None}),
                     "created_at": None}]

    async def verified(self, user_id, symbol, *, setups=None):
        return {"reported_scores": {"macro_score": 20, "technical_score": 50,
                                     "market_score": 30}}

    monkeypatch.setattr(
        "backend.services.setup_market_match_service.SetupMarketMatchService.for_asset", verified,
    )
    service = BotService(_FakeSession())
    service.repository = Repo()

    decision = asyncio.run(service.get_bot_today(7, "ETH", lean=True))["decisions"][0]

    assert decision["decision_stale"] is True
    assert decision["action"] is None


class _FakeResult:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeMappingResult:
    def __init__(self, row=None):
        self._row = row

    def mappings(self):
        return self

    def first(self):
        return self._row


class _FakeSession:
    def __init__(self, *, duplicate_strategy_bot_id=None):
        self.duplicate_strategy_bot_id = duplicate_strategy_bot_id
        self.executed = []
        self.commits = 0

    async def execute(self, query, params=None):
        sql = str(query).lower()
        params = params or {}
        self.executed.append({"sql": sql, "params": params})
        if "lower(name)" in sql:
            return _FakeResult(None)
        if "from strategies s" in sql:
            return _FakeResult((params.get("strategy_id"), "BTC", None, None))
        if "from bot_configs" in sql and "strategy_id" in sql:
            row = (self.duplicate_strategy_bot_id,) if self.duplicate_strategy_bot_id else None
            return _FakeResult(row)
        return _FakeResult(None)

    async def commit(self):
        self.commits += 1


def test_explicit_paper_funding_is_separate_from_budget_and_atomic(monkeypatch):
    session = _FakeSession()
    service = BotService(session)
    events = []

    async def validate(payload, _user_id, **_kwargs):
        payload["symbol"] = "ETH"

    class Repo:
        async def create_bot_config(self, payload):
            events.append(("create", payload["budget_total_eur"], payload["paper_initial_cash_eur"]))
            return 41

        async def seed_initial_paper_cash(self, **fields):
            events.append(("fund", fields["symbol"], fields["amount_eur"]))
            assert session.commits == 0
            return True

        async def get_bot_config(self, _user_id, bot_id):
            return {"id": bot_id, "strategy_id": 5, "symbol": "ETH",
                    "paper_initial_cash_eur": 25, "budget_total_eur": 100,
                    "is_live": False, "mode": "manual"}

    monkeypatch.setattr(service, "validate_bot_payload", validate)
    service.repository = Repo()
    result = asyncio.run(service.create_bot_config(BotConfigCreateSchema(
        name="ETH Paper", strategy_id=5, budget_total_eur=100,
        paper_initial_cash_eur=25,
    ), user_id=7))

    assert events == [("create", 100, 25), ("fund", "ETH", 25)]
    assert session.commits == 1
    assert result["bot"]["budget"]["total_eur"] == 100
    assert result["bot"]["paper_initial_cash_eur"] == 25


def test_deferred_live_creation_persists_paused_and_notifies_finn(monkeypatch):
    session = _FakeSession()
    service = BotService(session)
    events = []

    async def validate(payload, _user_id, **_kwargs):
        payload["symbol"] = "BTC"

    class Repo:
        async def create_bot_config(self, payload):
            events.append(("create", payload["is_live"], payload["is_active"]))
            return 77

        async def get_bot_config(self, _user_id, bot_id):
            return {"id": bot_id, "name": "BTC Live Later", "strategy_id": 5,
                    "symbol": "BTC", "is_live": True, "is_active": False,
                    "mode": "auto"}

    async def publish(_self, **fields):
        events.append(("feed", fields["event_type"], fields["subject_id"]))
        assert session.commits == 0

    monkeypatch.setattr(service, "validate_bot_payload", validate)
    monkeypatch.setattr(
        "backend.services.bot_service.FinnCoachFeedService.publish", publish,
    )
    service.repository = Repo()
    result = asyncio.run(service.create_bot_config(BotConfigCreateSchema(
        name="BTC Live Later", strategy_id=5, mode="auto",
        is_live=True, is_active=False,
    ), user_id=7))

    assert events == [("create", True, False), ("feed", "live_bot_paused", "77")]
    assert result["bot"]["is_active"] is False
    assert session.commits == 1


def test_existing_unused_paper_bot_can_receive_one_explicit_initial_credit(monkeypatch):
    session = _FakeSession()
    service = BotService(session)
    events = []

    async def validate(_payload, _user_id, **_kwargs):
        return None

    class Repo:
        async def lock_live_account(self, _user_id):
            events.append("account_lock")

        async def lock_bot_config(self, _user_id, _bot_id):
            events.append("bot_lock")

        async def get_bot_config(self, _user_id, _bot_id):
            return {"id": 41, "strategy_id": 5, "symbol": "ETH", "mode": "auto",
                    "is_live": False, "is_active": True, "paper_initial_cash_eur": 0,
                    "budget_total_eur": 100, "budget_daily_limit_eur": 20,
                    "budget_min_order_eur": 1, "budget_max_order_eur": 20,
                    "base_currency": "EUR"}

        async def can_seed_existing_paper_bot(self, **_fields):
            events.append("eligibility")
            return True

        async def update_bot_config(self, _user_id, _bot_id, fields):
            events.append(("update", fields["paper_initial_cash_eur"]))
            return 41

        async def seed_initial_paper_cash(self, **fields):
            assert session.commits == 0
            events.append(("credit", fields["symbol"], fields["amount_eur"]))
            return True

    monkeypatch.setattr(service, "validate_bot_payload", validate)
    service.repository = Repo()
    asyncio.run(service.update_bot_config(41, BotConfigUpdateSchema(
        paper_initial_cash_eur=25, risk_acknowledged=True,
    ), user_id=7))

    assert events == ["account_lock", "bot_lock", "eligibility", ("update", 25), ("credit", "ETH", 25)]
    assert session.commits == 2  # bot+credit transaction, then behavioral audit


def test_null_mode_fields_cannot_bypass_live_budget_validation():
    class Repo:
        def __init__(self):
            self.updated = False

        async def lock_live_account(self, _user_id):
            return None

        async def lock_bot_config(self, _user_id, _bot_id):
            return None

        async def get_bot_config(self, _user_id, bot_id):
            return {
                "id": bot_id, "is_live": True, "is_active": True, "mode": "manual",
                "budget_total_eur": 100, "budget_daily_limit_eur": 50,
                "budget_min_order_eur": 1, "budget_max_order_eur": 50,
            }

        async def update_bot_config(self, *_args):
            self.updated = True

    service = BotService(_FakeSession())
    repo = Repo()
    service.repository = repo
    with pytest.raises(HTTPException, match="expliciete budgetlimieten") as exc:
        asyncio.run(service.update_bot_config(
            9, BotConfigUpdateSchema(is_live=None, mode=None, budget_total_eur=0), 1,
        ))
    assert exc.value.status_code == 400
    assert not repo.updated


def test_bot_with_order_history_cannot_be_deleted():
    class Repo:
        def __init__(self):
            self.deleted = False

        async def lock_bot_config(self, user_id, bot_id):
            return None

        async def get_bot_config(self, user_id, bot_id):
            return {"id": bot_id}

        async def has_execution_history(self, user_id, bot_id):
            return True

        async def delete_bot_config(self, user_id, bot_id):
            self.deleted = True

    service = BotService(_FakeSession())
    repo = Repo()
    service.repository = repo
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.delete_bot_config(9, 1))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "BOT_HISTORY_PRESERVED"
    assert not repo.deleted


def test_saved_safety_check_reports_block_and_staleness():
    service = BotService.__new__(BotService)
    checked = datetime.now(timezone.utc)
    decision = {
        "id": 12, "bot_id": 9, "status": "planned",
        "requested_amount_eur": 100,
        "guardrails_checked_at": checked.isoformat(),
        "guardrails_result": {
            "allowed": False, "adjusted_amount_eur": 0,
            "original_amount_eur": 100, "blocked_by": "insufficient_funds",
            "reason": "Onvoldoende kassaldo",
        },
    }
    blocked = service._safety_contract(decision, is_live=False)
    assert blocked["state"] == "blocked"
    assert blocked["allowed_amount_eur"] == 0
    assert blocked["reason_code"] == "insufficient_funds"

    decision["guardrails_checked_at"] = (checked - timedelta(hours=2)).isoformat()
    assert service._safety_contract(decision, is_live=True)["state"] == "stale"


def test_execution_failure_overrides_earlier_allowed_proposal():
    service = BotService.__new__(BotService)
    decision = {
        "id": 12, "bot_id": 9, "status": "failed_execution",
        "execution_failure": "De actuele daglimiet laat dit bedrag niet meer toe.",
        "guardrails_checked_at": datetime.now(timezone.utc).isoformat(),
        "guardrails_result": {
            "allowed": True, "original_amount_eur": 50,
            "adjusted_amount_eur": 50, "blocked_by": None,
            "reason": "Het voorstel paste binnen de oude limieten.",
        },
    }
    safety = service._safety_contract(decision, is_live=False)
    assert safety["state"] == "error"
    assert safety["reason_code"] == "failed_execution"
    assert safety["reason"] == decision["execution_failure"]
    assert safety["proposed_amount_eur"] == 50
    assert safety["checked_amount_eur"] == 50
    assert safety["allowed_amount_eur"] == 0


def test_account_trades_use_confirmed_fill_value_and_historical_environment():
    class Repo:
        async def get_account_bot_trades(self, user_id, limit, offset):
            assert (user_id, limit, offset) == (7, 3, 0)
            return [{
                "execution_id": 55, "bot_id": 9, "bot_name": "BTC Bot",
                "symbol": "BTC", "side": "buy", "filled_qty": 0.0004,
                "avg_fill_price": 50000, "quote_amount_eur": 50,
                "status": "partial", "executed_at": datetime.now(timezone.utc),
                "execution_environment": "live", "source": "manual", "executed_by": None,
            }]

    service = BotService(_FakeSession())
    service.repository = Repo()
    page = asyncio.run(service.get_account_bot_trades(7, 2, 0))
    assert page["has_more"] is False
    assert page["items"][0]["amount_eur"] == 20
    assert page["items"][0]["environment"] == "live"
    assert page["items"][0]["execution_mode"] == "manual"


def test_paused_bot_rejects_manual_sell_before_order_creation():
    class PausedRepo:
        def __init__(self):
            self.created_orders = 0

        async def lock_live_account(self, user_id):
            return None

        async def lock_bot_config(self, user_id, bot_id):
            return None

        async def get_bot_config(self, user_id, bot_id):
            return {"id": bot_id, "is_live": False, "is_active": False}

        async def create_manual_order(self, *_args, **_kwargs):
            self.created_orders += 1

    service = BotService(_FakeSession())
    repo = PausedRepo()
    service.repository = repo
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="sell", quantity=0.001, price=50000)
    with pytest.raises(HTTPException, match="gepauzeerd") as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))
    assert exc.value.status_code == 409
    assert repo.created_orders == 0


def test_paper_order_preflight_uses_virtual_cash_not_unused_budget(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual")
            return bot

        async def get_paper_cash(self, **_fields):
            return 0.0

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "EUR"}

        async def get_portfolio_fx_rates(self):
            return {}

        async def get_valuatable_market_prices(self, _symbols):
            return {"BTC": {"price": 50000, "observed_at": datetime.now(timezone.utc), "quote_currency": "EUR"}}

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    async def no_live_context(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    monkeypatch.setattr(service, "require_live_manual_order_preflight_context", no_live_context)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.0002, price=50000,
                                   idempotency_key="paper-cash-test")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.preflight_manual_order(payload, user_id=7))
    assert exc.value.status_code == 400
    assert "kassaldo" in str(exc.value.detail).lower()


def test_live_manual_order_rejects_asset_outside_bot_before_exchange():
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo()
    service.repository = repo
    payload = BotManualOrderSchema(
        bot_id=9, symbol="ETH", side="sell", quantity=1, price=100,
        idempotency_key="cross-asset-sell", risk_acknowledged=True,
        live_preflight_token="token",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 400
    assert "Orderasset" in str(exc.value.detail)
    assert repo.created_orders == 0


@pytest.mark.parametrize("route", ["preview_manual_order", "preflight_manual_order", "create_manual_order"])
def test_pair_bound_live_bot_rejects_base_symbol_manual_order_before_quote_or_execution(route):
    class PairRepo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(market_id=123, is_live=True, is_active=True)
            return bot

    service = BotService(_FakeSession())
    repo = PairRepo()
    service.repository = repo
    payload = BotManualOrderSchema(
        bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000,
        idempotency_key="pair-bound-manual", risk_acknowledged=True,
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(getattr(service, route)(payload, user_id=7))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "EXACT_MARKET_EXECUTION_PENDING"
    assert repo.created_orders == 0


@pytest.mark.parametrize("route", ["preview_manual_order", "create_manual_order"])
def test_pair_bound_paper_buy_checks_setup_before_quote_or_execution(route, monkeypatch):
    class PairRepo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(market_id=123, quote_currency="EUR", is_live=False,
                       is_active=True, setup_id=42)
            return bot

        async def get_valuatable_exact_market_prices(self, market_ids):
            raise AssertionError("outside setup must be checked before fetching a quote")

    service = BotService(_FakeSession())
    repo = PairRepo()
    service.repository = repo

    async def outside(*_args, **_kwargs):
        return {"allowed": False, "status": "outside_conditions",
                "message": "Benchmark 36,7 ligt onder minimum 61. Deze Paper-koop wacht.",
                "safe_next_step": "Controleer de setupvoorwaarden."}

    monkeypatch.setattr(service, "_paper_manual_buy_match", outside)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001,
                                   price=50000, idempotency_key="pair-outside")
    if route == "preview_manual_order":
        result = asyncio.run(service.preview_manual_order(payload, user_id=7))
        assert result["blocked"] is True
        assert result["setup_match_status"] == "outside_conditions"
        assert "Benchmark 36,7" in result["message"]
    else:
        with pytest.raises(HTTPException) as exc:
            asyncio.run(service.create_manual_order(payload, user_id=7))
        assert exc.value.detail["code"] == "PAPER_SETUP_MATCH_REQUIRED"
    assert repo.created_orders == 0


def test_pair_bound_paper_preview_uses_exact_market_quote_and_not_base_quote(monkeypatch):
    service = BotService(_FakeSession())

    class PairRepo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(market_id=123, quote_currency="EUR", is_live=False,
                       is_active=True, setup_id=42, budget_max_order_eur=100)
            return bot

        async def get_valuatable_exact_market_prices(self, market_ids):
            assert market_ids == [123]
            return {123: {"symbol": "BTC", "quote_currency": "EUR", "price": 50000,
                          "source_observed_at": datetime.now(timezone.utc)}}

        async def get_valuatable_market_prices(self, symbols):
            raise AssertionError("base asset quote must not be used for a saved pair")

        async def get_paper_cash(self, **_fields):
            return 100.0

    service.repository = PairRepo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True, "status": "matches"}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.0002,
                                   price=50000, value_eur=10, idempotency_key="pair-allowed")
    result = asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert result["ok"] is True
    assert result["price"] == 50000
    assert result["price_source_quote_currency"] == "EUR"
    assert result["paper_preview_token"]


def test_pair_bound_paper_confirmation_rechecks_exact_quote_and_books_once(monkeypatch):
    from unittest.mock import AsyncMock

    service = BotService(_FakeSession())

    class PairRepo(_ManualOrderRepo):
        def __init__(self):
            super().__init__()
            self.locked_setup = False

        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(market_id=123, quote_currency="EUR", is_live=False,
                       is_active=True, setup_id=42, mode="manual", budget_max_order_eur=100)
            return bot

        async def lock_manual_paper_setup(self, user_id, setup_id, symbol, market_id):
            assert (user_id, setup_id, symbol, market_id) == (7, 42, "BTC", 123)
            self.locked_setup = True

        async def get_valuatable_exact_market_prices(self, market_ids):
            assert market_ids == [123]
            return {123: {"symbol": "BTC", "quote_currency": "EUR", "price": 50000,
                          "source_observed_at": datetime.now(timezone.utc)}}

        async def get_valuatable_market_prices(self, symbols):
            raise AssertionError("base quote must not be used")

        async def get_paper_cash(self, **_fields):
            return 100.0

    repo = PairRepo()
    repo.create_bot_execution = AsyncMock(return_value=1)
    repo.insert_bot_ledger = AsyncMock()
    service.repository = repo

    async def allowed(*_args, **_kwargs):
        return {"allowed": True, "status": "matches"}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    monkeypatch.setattr("backend.services.bot_service.sync_snapshot_all_for_user", lambda _user_id: None)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.0002,
                                   price=50000, value_eur=10, idempotency_key="pair-confirm")
    preview = asyncio.run(service.preview_manual_order(payload, user_id=7))
    payload.quantity = preview["quantity"]
    payload.price = preview["price"]
    payload.price_currency = preview["price_currency"]
    payload.value_eur = preview["gross_eur"]
    payload.paper_preview_token = preview["paper_preview_token"]
    result = asyncio.run(service.create_manual_order(payload, user_id=7))
    assert result["status"] == "filled"
    assert repo.locked_setup
    assert repo.created_orders == 1
    assert repo.insert_bot_ledger.await_count == 1


@pytest.mark.parametrize("field,value", [
    ("quantity", float("nan")), ("price", float("nan")),
    ("value_eur", float("inf")), ("quantity", float("inf")),
])
def test_manual_order_rejects_nonfinite_amounts(field, value):
    service = BotService.__new__(BotService)
    values = {"bot_id": 9, "symbol": "BTC", "side": "sell", "quantity": 0.001, "price": 50000}
    values[field] = value

    with pytest.raises(HTTPException) as exc:
        service._validate_manual_order_payload(BotManualOrderSchema(**values))

    assert exc.value.status_code == 400


def test_paper_manual_buy_rejects_guardrail_cash_trimming():
    service = BotService.__new__(BotService)
    bot = {
        "is_live": False, "is_active": True, "budget_total_eur": 1000,
        "budget_daily_limit_eur": 1000, "budget_min_order_eur": 10,
        "budget_max_order_eur": 1000, "max_asset_exposure_pct": 100,
    }
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.002, price=50000)
    stats = {"executed_cash": 0, "today_spent": 0, "net_qty": 0}
    with pytest.raises(HTTPException) as exc:
        service._validate_manual_order_budget_context(bot, stats, payload, 100, paper_cash_eur=50)
    assert exc.value.status_code == 400
    assert "Paper-kassaldo" in str(exc.value.detail)


def test_paper_manual_preview_uses_actual_cash(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual")
            return bot

        async def get_paper_cash(self, **_fields):
            return 0.0

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "EUR"}

        async def get_portfolio_fx_rates(self):
            return {}

        async def get_valuatable_market_prices(self, _symbols):
            return {"BTC": {"price": 50000, "observed_at": datetime.now(timezone.utc), "quote_currency": "EUR"}}

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.0002, price=50000,
                                   idempotency_key="paper-cash-empty-test")
    result = asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert result["guardrails"]["allowed"] is False
    assert result["guardrails"]["blocked_by"] == "insufficient_funds"
    assert "kassaldo" in result["message"].lower()


def test_paper_manual_preview_explains_saved_minimum_order(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual", budget_min_order_eur=100)
            return bot

        async def get_paper_cash(self, **_fields):
            return 1000.0

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "EUR"}

        async def get_portfolio_fx_rates(self):
            return {}

        async def get_valuatable_market_prices(self, _symbols):
            return {"BTC": {"price": 50000, "observed_at": datetime.now(timezone.utc), "quote_currency": "EUR"}}

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000,
                                   value_eur=50, idempotency_key="paper-minimum-preview")
    result = asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert result["blocked"] is True
    assert result["guardrails"]["blocked_by"] == "below_min_order"
    assert "€100.00" in result["message"]
    assert "€50.00" in result["message"]


def test_paper_full_position_close_below_buy_minimum_is_consistent_in_preview_and_confirmation(monkeypatch):
    service = BotService(_FakeSession())
    quantity = 0.001995

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual", budget_min_order_eur=100)
            return bot

        async def get_bot_ledger_stats(self, user_id, bot_id, day):
            return {"executed_cash": -100, "today_spent": 100, "net_qty": quantity}

        async def get_paper_cash(self, **_fields):
            return 900.0

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "EUR"}

        async def get_portfolio_fx_rates(self):
            return {}

        async def get_valuatable_market_prices(self, _symbols):
            return {"BTC": {"price": 50000, "observed_at": datetime.now(timezone.utc), "quote_currency": "EUR"}}

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="sell", quantity=quantity, price=50000,
                                   idempotency_key="paper-full-close")
    result = asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert result["ok"] is True
    assert result["gross_eur"] == 99.75
    assert result["paper_preview_token"]

    bot = asyncio.run(service.repository.get_bot_config(7, 9))
    stats = asyncio.run(service.repository.get_bot_ledger_stats(7, 9, date.today()))
    service._validate_manual_order_budget_context(bot, stats, payload, result["gross_eur"])

    partial = BotManualOrderSchema(bot_id=9, symbol="BTC", side="sell", quantity=quantity / 2,
                                   price=50000, idempotency_key="paper-partial-close")
    partial_preview = asyncio.run(service.preview_manual_order(partial, user_id=7))
    assert partial_preview["blocked"] is True
    assert partial_preview["guardrails"]["blocked_by"] == "below_min_order"
    with pytest.raises(HTTPException) as exc:
        service._validate_manual_order_budget_context(bot, stats, partial, partial.quantity * 50000)
    assert exc.value.status_code == 400

    live_bot = {**bot, "is_live": True}
    with pytest.raises(HTTPException) as exc:
        service._validate_manual_order_budget_context(live_bot, stats, payload, result["gross_eur"])
    assert exc.value.status_code == 400


def test_paper_manual_preview_converts_usdt_price_to_eur(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual", symbol="BTC", budget_max_order_eur=500)
            return bot

        async def get_paper_cash(self, **_fields):
            return 500.0

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "USDT"}

        async def get_portfolio_fx_rates(self):
            return {"USDT": {"eur_per_unit": 0.8, "observed_at": datetime.now(timezone.utc)}}

        async def get_valuatable_market_prices(self, _symbols):
            return {"BTC": {"price": 125, "observed_at": datetime.now(timezone.utc), "quote_currency": "USDT"}}

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=1, price=125, value_eur=100,
                                   idempotency_key="paper-fx-test")
    result = asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert result["price"] == 100.0
    assert result["price_currency"] == "EUR"
    assert result["price_source_quote_currency"] == "USDT"
    assert result["price_is_fx_converted"] is True
    assert result["gross_eur"] == 100.0
    assert result["quantity"] == 0.9975
    assert result["paper_preview_token"]


def test_paper_preview_rejects_price_row_with_other_quote(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual")
            return bot

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "EUR"}

        async def get_valuatable_market_prices(self, _symbols):
            return {"BTC": {"price": 80000, "observed_at": datetime.now(timezone.utc),
                            "quote_currency": "USDT"}}

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001,
                                   price=80000, idempotency_key="wrong-quote")
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert exc.value.status_code == 409
    assert "koersvaluta" in str(exc.value.detail)


def test_manual_paper_preview_and_confirmation_require_fresh_trade_quote(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        price_at = datetime.now(timezone.utc)

        async def get_paper_cash(self, **_fields):
            return 500.0

        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual")
            return bot

        async def get_valuatable_market_prices(self, symbols):
            return {"BTC": {"price": 50000, "quote_currency": "EUR",
                            "observed_at": self.price_at}}

    repo = Repo()
    service.repository = repo

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001,
                                   price=50000, price_currency="EUR", value_eur=50,
                                   idempotency_key="stale-between-preview-and-commit")
    preview = asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert preview["paper_preview_token"]
    payload.quantity = preview["quantity"]
    payload.paper_preview_token = preview["paper_preview_token"]
    repo.price_at = datetime.now(timezone.utc) - timedelta(minutes=31)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=7))
    assert exc.value.status_code == 409
    assert repo.created_orders == 0
    with pytest.raises(HTTPException) as preview_exc:
        asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert preview_exc.value.status_code == 409


def test_manual_paper_confirmation_rechecks_quote_after_cash_lock(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        price_at = datetime.now(timezone.utc)

        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual")
            return bot

        async def get_paper_cash(self, **_fields):
            self.price_at = datetime.now(timezone.utc) - timedelta(minutes=31)
            return 500.0

        async def get_valuatable_market_prices(self, symbols):
            return {"BTC": {"price": 50000, "quote_currency": "EUR",
                            "observed_at": self.price_at}}

    repo = Repo()
    service.repository = repo

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(
        bot_id=9, symbol="BTC", side="buy", quantity=0.001,
        price=50000, price_currency="EUR", value_eur=50,
        idempotency_key="quote-stale-during-lock",
    )
    preview = asyncio.run(service.preview_manual_order(payload, user_id=7))
    payload.quantity = preview["quantity"]
    payload.paper_preview_token = preview["paper_preview_token"]

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=7))
    assert exc.value.status_code == 409
    assert repo.created_orders == 0


def test_paper_preview_ignores_a_forged_client_eur_price(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual", symbol="BTC", budget_max_order_eur=500)
            return bot

        async def get_paper_cash(self, **_fields):
            return 500.0

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "EUR"}

        async def get_portfolio_fx_rates(self):
            return {}

        async def get_valuatable_market_prices(self, _symbols):
            return {"BTC": {"price": 100, "observed_at": datetime.now(timezone.utc), "quote_currency": "EUR"}}

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(
        bot_id=9, symbol="BTC", side="buy", quantity=100,
        price=1, price_currency="EUR", value_eur=100,
        idempotency_key="forged-eur-price",
    )
    result = asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert result["price"] == 100
    assert result["quantity"] == 0.9975
    assert result["gross_eur"] == 100
    assert result["paper_preview_token"]


def test_paper_preview_requires_idempotency_key_before_token():
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=1,
                                   price=100, price_currency="EUR", value_eur=100)
    with pytest.raises(HTTPException) as exc:
        BotService._paper_preview_token(
            user_id=7, payload=payload, quantity=1, price=100, gross_eur=100,
        )
    assert exc.value.status_code == 400


def test_paper_manual_order_rejects_direct_client_currency_marker_without_preview():
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, symbol="BTC")
            return bot

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "USDT"}

    service.repository = Repo()
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.1,
                                   price=100, price_currency="EUR", value_eur=10)
    async def allowed(*_args, **_kwargs):
        return {"allowed": True}
    service._paper_manual_buy_match = allowed
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=7))
    assert exc.value.status_code == 409
    assert service.repository.created_orders == 0


def test_paper_manual_confirmation_is_bound_to_owner_and_previewed_eur_values():
    payload = BotManualOrderSchema(
        bot_id=9, symbol="ETH", side="buy", quantity=0.9975,
        price=100, price_currency="EUR", value_eur=100,
        idempotency_key="paper-test-123",
    )
    payload.paper_preview_token = BotService._paper_preview_token(
        user_id=7, payload=payload, quantity=payload.quantity,
        price=payload.price, gross_eur=100,
    )
    assert BotService._verify_paper_preview(payload, 7) == 100
    with pytest.raises(HTTPException) as other_owner:
        BotService._verify_paper_preview(payload, 8)
    assert other_owner.value.status_code == 409
    payload.price = 125
    with pytest.raises(HTTPException) as changed_price:
        BotService._verify_paper_preview(payload, 7)
    assert changed_price.value.status_code == 409
    payload.price = 100
    payload.value_eur = 1
    with pytest.raises(HTTPException):
        BotService._verify_paper_preview(payload, 7)


def test_manual_order_http_route_rejects_forged_eur_marker_without_preview():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from backend.api import bot_api

    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, symbol="BTC")
            return bot

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    async def no_audit(*_args, **_kwargs):
        return None

    service._paper_manual_buy_match = allowed
    service.record_live_order_block_from_exception = no_audit
    app = FastAPI()
    app.include_router(bot_api.router, prefix="/api")
    app.dependency_overrides[bot_api.get_current_user] = lambda: {"id": 7}
    app.dependency_overrides[bot_api.get_bot_service] = lambda: service
    response = TestClient(app).post("/api/orders/manual", json={
        "bot_id": 9, "symbol": "BTC", "side": "buy", "quantity": 0.1,
        "price": 100, "price_currency": "EUR", "value_eur": 10,
    })
    assert response.status_code == 409
    assert service.repository.created_orders == 0


def test_paper_confirmation_books_previewed_gross_eur_after_fee(monkeypatch):
    from unittest.mock import AsyncMock
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, symbol="ETH", budget_max_order_eur=500,
                       budget_daily_limit_eur=500)
            return bot

        async def get_paper_cash(self, **_fields):
            return 500.0

    service.repository = Repo()
    service.repository.create_bot_execution = AsyncMock(return_value=1)
    service.repository.insert_bot_ledger = AsyncMock()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    monkeypatch.setattr("backend.services.bot_service.sync_snapshot_all_for_user", lambda _user_id: None)
    payload = BotManualOrderSchema(
        bot_id=9, symbol="ETH", side="buy", quantity=0.9975,
        price=100, price_currency="EUR", value_eur=100,
        idempotency_key="paper-gross-test-123",
    )
    payload.paper_preview_token = service._paper_preview_token(
        user_id=7, payload=payload, quantity=payload.quantity, price=100, gross_eur=100,
        source_quote_currency="EUR",
    )
    result = asyncio.run(service.create_manual_order(payload, user_id=7))
    assert result["notional_eur"] == 100
    assert service.repository.created_orders == 1
    ledger = service.repository.insert_bot_ledger.await_args.args
    assert ledger[4] == -100
    assert ledger[5] == 0.9975


def test_replaying_a_paper_preview_does_not_book_a_second_fill(monkeypatch):
    from unittest.mock import AsyncMock
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        async def get_bot_config(self, user_id, bot_id):
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, symbol="ETH", budget_max_order_eur=500,
                       budget_daily_limit_eur=500)
            return bot

        async def get_paper_cash(self, **_fields):
            return 500.0

        async def create_manual_order(self, *args, **kwargs):
            self.created_orders += 1
            return 123, self.created_orders == 1

        async def get_manual_order_by_idempotency_key(self, _user_id, _key):
            return {"id": 123, "bot_id": 9, "symbol": "ETH", "side": "buy", "quantity": 0.9975,
                    "limit_price": 100, "quote_amount_eur": 100, "status": "filled"}

    service.repository = Repo()
    service.repository.create_bot_execution = AsyncMock(return_value=1)
    service.repository.insert_bot_ledger = AsyncMock()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    monkeypatch.setattr("backend.services.bot_service.sync_snapshot_all_for_user", lambda _user_id: None)
    payload = BotManualOrderSchema(
        bot_id=9, symbol="ETH", side="buy", quantity=0.9975,
        price=100, price_currency="EUR", value_eur=100,
        idempotency_key="paper-replay-123",
    )
    payload.paper_preview_token = service._paper_preview_token(
        user_id=7, payload=payload, quantity=payload.quantity, price=100, gross_eur=100,
        source_quote_currency="EUR",
    )
    first = asyncio.run(service.create_manual_order(payload, user_id=7))
    second = asyncio.run(service.create_manual_order(payload, user_id=7))
    assert first["ok"] and not first.get("duplicate")
    assert second["ok"] and second["duplicate"]
    assert service.repository.insert_bot_ledger.await_count == 1
    assert service.repository.create_bot_execution.await_count == 1
    changed = payload.copy(update={"price": 110.0, "value_eur": 110.0})
    changed.paper_preview_token = service._paper_preview_token(
        user_id=7, payload=changed, quantity=changed.quantity, price=110, gross_eur=110,
        source_quote_currency="EUR",
    )
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(changed, user_id=7))
    assert exc.value.status_code == 409
    assert service.repository.insert_bot_ledger.await_count == 1


_DEFAULT_MARKET_SNAPSHOT = object()


class _ManualOrderRepo:
    async def lock_manual_paper_setup(self, user_id, setup_id, symbol, market_id):
        return None

    async def get_asset_quote_currencies(self, symbols):
        return {symbol: "EUR" for symbol in symbols}

    async def get_valuatable_market_prices(self, symbols):
        prices = {"BTC": 50000, "ETH": 100}
        return {symbol: {"price": prices[symbol], "quote_currency": "EUR",
                         "observed_at": datetime.now(timezone.utc)} for symbol in symbols}

    async def get_portfolio_fx_rates(self):
        return {}

    def __init__(
        self,
        decisions=None,
        *,
        live_daily_spend=0,
        portfolio_context=None,
        bot_setup_id=None,
        market_snapshot=_DEFAULT_MARKET_SNAPSHOT,
    ):
        self.created_orders = 0
        self.decisions = decisions if decisions is not None else [
            {
                "id": 1,
                "bot_id": 9,
                "decision_ts": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "created_at": datetime.now(timezone.utc),
            }
        ]
        self.live_daily_spend = live_daily_spend
        self.portfolio_context = portfolio_context if portfolio_context is not None else {
            "global": {
                "total_equity": 1000,
                "current_position_value": 0,
            },
            "bots": [],
        }
        self.bot_setup_id = bot_setup_id
        self.market_snapshot = (
            {"price": 50000, "timestamp": datetime.now(timezone.utc), "quote_currency": "EUR"}
            if market_snapshot is _DEFAULT_MARKET_SNAPSHOT
            else {"quote_currency": "EUR", **market_snapshot} if market_snapshot is not None else None
        )

    async def lock_bot_config(self, user_id, bot_id):
        return None

    async def lock_live_account(self, user_id):
        return None

    async def get_live_pending_order_exposure(self, user_id):
        return []

    async def get_manual_order_by_idempotency_key(self, user_id, idempotency_key):
        return None

    async def get_unresolved_live_orders(self, user_id):
        return []

    async def get_bot_config(self, user_id, bot_id):
        return {
            "id": bot_id,
            "name": "BTC Live Bot",
            "is_live": True,
            "is_active": True,
            "mode": "auto",
            "symbol": "BTC",
            "budget_total_eur": 1000,
            "budget_daily_limit_eur": 100,
            "budget_min_order_eur": 10,
            "budget_max_order_eur": 50,
            "max_asset_exposure_pct": 100,
            "setup_id": self.bot_setup_id,
        }

    async def get_bot_ledger_stats(self, user_id, bot_id, day):
        return {
            "executed_cash": 0,
            "today_spent": 0,
            "today_reserved": 0,
            "net_qty": 0,
        }

    async def create_manual_order(self, *args, **kwargs):
        self.created_orders += 1
        return 1, True

    async def get_bot_decisions_by_date(self, user_id, decision_date):
        return self.decisions

    async def get_live_daily_spend(self, user_id, today):
        return self.live_daily_spend

    async def get_portfolio_intelligence_context(self, user_id):
        return self.portfolio_context

    async def get_market_price_snapshot(self, symbol):
        return self.market_snapshot

    async def get_market_price(self, symbol):
        snapshot = await self.get_market_price_snapshot(symbol)
        return snapshot.get("price") if snapshot else None


def _attach_live_portfolio_context(service, repo):
    async def context(user_id):
        source = repo.portfolio_context
        values = {}
        for item in source.get("bots", []):
            symbol = str(item.get("symbol") or "").upper()
            values[symbol] = values.get(symbol, 0) + float(item.get("position_value") or 0)
        return {
            "total_equity": float(source["global"]["total_equity"]),
            "current_position_value": float(source["global"]["current_position_value"]),
            "asset_values": values,
            "exchange": "bitvavo",
        }
    service._live_exchange_portfolio_context = context
    async def cash(bot, user_id, symbol):
        return float(repo.portfolio_context["global"]["total_equity"])
    service._actual_cash_for_order = cash


class _NoExchangeKeys:
    async def get_active_keys(self, user_id):
        return []


class _MultiAssetPortfolioRepo:
    async def get_bot_portfolios_base(self, user_id):
        return [
            {
                "id": 8,
                "name": "Apple Paper",
                "is_active": True,
                "is_live": False,
                "mode": "paper",
                "risk_profile": "balanced",
                "symbol": "AAPL",
                "budget_total_eur": 500,
                "budget_daily_limit_eur": 100,
                "budget_min_order_eur": 10,
                "budget_max_order_eur": 50,
            },
            {
                "id": 10,
                "name": "Microsoft Paper",
                "is_active": True,
                "is_live": False,
                "mode": "paper",
                "risk_profile": "balanced",
                "symbol": "MSFT",
                "budget_total_eur": 750,
                "budget_daily_limit_eur": 100,
                "budget_min_order_eur": 10,
                "budget_max_order_eur": 50,
            },
        ]

    async def get_bot_ledger_stats(self, user_id, bot_id, today):
        return {
            "net_cash": 0,
            "executed_cash": 0,
            "net_qty": 0,
            "today_spent": 0,
            "today_reserved": 0,
        }

    async def get_valuatable_market_prices(self, symbols):
        now = datetime.now(timezone.utc)
        return {symbol: {"price": {"AAPL": 240.0, "MSFT": 510.0}[symbol], "observed_at": now, "quote_currency": "USD"}
                for symbol in symbols}

    async def get_asset_quote_currencies(self, symbols):
        return {symbol: "USD" for symbol in symbols}

    async def get_portfolio_fx_rates(self):
        return {"USD": {"eur_per_unit": 0.8, "observed_at": datetime.now(timezone.utc)}}


def test_bot_portfolios_use_each_bots_canonical_strategy_symbol():
    service = BotService.__new__(BotService)
    service.repository = _MultiAssetPortfolioRepo()

    result = asyncio.run(service.get_bot_portfolios(user_id=27))

    assert [item["symbol"] for item in result] == ["AAPL", "MSFT"]
    assert [item["stats"]["last_price"] for item in result] == [192.0, 408.0]
    assert all(item["stats"]["price_currency"] == "EUR" for item in result)


def test_bot_portfolio_cards_value_each_saved_pair_from_its_own_quote():
    now = datetime.now(timezone.utc)

    class Repo(_MultiAssetPortfolioRepo):
        async def get_bot_portfolios_base(self, user_id):
            rows = await super().get_bot_portfolios_base(user_id)
            return [{**rows[0], "id": 1, "symbol": "BTC", "market_id": 41,
                     "quote_currency": "EUR"},
                    {**rows[1], "id": 2, "symbol": "BTC", "market_id": 42,
                     "quote_currency": "USDT"}]

        async def get_valuatable_market_prices(self, symbols):
            return {"BTC": {"price": 99999, "quote_currency": "USDT", "observed_at": now}}

        async def get_valuatable_exact_market_prices(self, market_ids):
            assert market_ids == [41, 42]
            return {41: {"symbol": "BTC", "price": 100, "quote_currency": "EUR", "source_observed_at": now},
                    42: {"symbol": "BTC", "price": 100, "quote_currency": "USDT", "source_observed_at": now}}

        async def get_asset_quote_currencies(self, symbols):
            return {"BTC": "USDT"}

        async def get_portfolio_fx_rates(self):
            return {"USDT": {"eur_per_unit": 0.8, "observed_at": now}}

        async def get_bot_ledger_stats(self, user_id, bot_id, today):
            return {"net_cash": -50, "executed_cash": -50, "net_qty": 1,
                    "today_spent": 0, "today_reserved": 0}

    service = BotService.__new__(BotService)
    service.repository = Repo()
    result = asyncio.run(service.get_bot_portfolios(user_id=27))
    assert [bot["stats"]["position_value_eur"] for bot in result] == [100, 80]
    assert [bot["valuation_status"] for bot in result] == ["available", "available"]


def test_closed_paper_bot_keeps_gross_purchases_distinct_from_net_cash():
    class Repo(_MultiAssetPortfolioRepo):
        async def get_bot_portfolios_base(self, user_id):
            rows = await super().get_bot_portfolios_base(user_id)
            rows[0]["paper_cash_eur"] = 999.62
            return rows[:1]

        async def get_bot_ledger_stats(self, user_id, bot_id, today):
            return {
                "net_cash": -0.38, "executed_cash": -0.38,
                "gross_executed_buys_eur": 100,
                "net_qty": 0, "today_spent": 100, "today_reserved": 0,
            }

    service = BotService.__new__(BotService)
    service.repository = Repo()
    stats = asyncio.run(service.get_bot_portfolios(user_id=27))[0]["stats"]
    assert stats["gross_executed_buys_eur"] == 100
    assert stats["net_executed_cash_delta_eur"] == -0.38
    assert stats["position_value_eur"] == 0
    assert stats["paper_cash_eur"] == 999.62


def test_bot_card_does_not_value_an_unverified_legacy_paper_ledger():
    class Repo(_MultiAssetPortfolioRepo):
        async def get_bot_portfolios_base(self, user_id):
            rows = await super().get_bot_portfolios_base(user_id)
            rows[0].update(unverified_ledger=True, paper_cash_eur=300)
            return rows[:1]

        async def get_bot_ledger_stats(self, user_id, bot_id, today):
            return {
                "net_cash": -200, "executed_cash": -200,
                "net_qty": 1, "today_spent": 200, "today_reserved": 0,
            }

    service = BotService.__new__(BotService)
    service.repository = Repo()
    result = asyncio.run(service.get_bot_portfolios(user_id=27))[0]
    assert result["valuation_status"] == "unverified_ledger"
    assert result["stats"]["paper_cash_eur"] is None
    assert result["stats"]["position_value_eur"] is None
    assert result["stats"]["invested_eur"] is None
    assert result["stats"]["remaining_budget_limit_eur"] is None


class _PreflightSession:
    def __init__(self, payload):
        self.payload = payload

    async def execute(self, query, params=None):
        return _FakeMappingResult({"payload": self.payload} if self.payload else None)


def test_bot_payload_validation_normalizes_transactional_fields():
    service = BotService(_FakeSession())
    payload = {
        "name": "  BTC Paper Bot  ",
        "strategy_id": 42,
        "mode": "Semi",
        "is_live": False,
        "risk_profile": "BALANCED",
        "cadence": "DAILY",
        "base_currency": "eur",
        "budget_total_eur": 1000,
        "budget_daily_limit_eur": 100,
        "budget_min_order_eur": 10,
        "budget_max_order_eur": 50,
    }

    import asyncio
    asyncio.run(service.validate_bot_payload(payload, user_id=1))

    assert payload["name"] == "BTC Paper Bot"
    assert payload["symbol"] == "BTC"
    assert payload["mode"] == "semi-auto"
    assert payload["risk_profile"] == "balanced"
    assert payload["cadence"] == "daily"
    assert payload["base_currency"] == "EUR"


def test_bot_payload_uses_owner_scoped_strategy_asset_over_stale_workspace_asset():
    service = BotService(_FakeSession())
    payload = {
        "name": "Apple Paper Bot",
        "strategy_id": 42,
        "symbol": "AAPL",
        "mode": "manual",
        "is_live": False,
    }

    asyncio.run(service.validate_bot_payload(payload, user_id=1))

    # The fake owner-scoped strategy is BTC; a caller supplied workspace value
    # may not redefine the persisted bot graph.
    assert payload["symbol"] == "BTC"


def test_paused_live_bot_can_be_saved_without_keys_or_limits_but_activation_cannot():
    service = BotService(_FakeSession())
    class NoKeys:
        async def get_active_keys(self, user_id):
            assert user_id == 1
            return []
    service.exchange_repo = NoKeys()
    payload = {
        "name": "BTC Live Later", "strategy_id": 42, "mode": "auto",
        "is_live": True, "is_active": False,
    }

    asyncio.run(service.validate_bot_payload(payload, user_id=1))
    assert payload["symbol"] == "BTC"

    payload["is_active"] = True
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.validate_bot_payload(payload, user_id=1))
    assert exc.value.status_code == 400
    assert "budget" in exc.value.detail.lower()

    payload.update({
        "budget_total_eur": 1000, "budget_daily_limit_eur": 100,
        "budget_min_order_eur": 10, "budget_max_order_eur": 50,
    })
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.validate_bot_payload(payload, user_id=1))
    assert exc.value.status_code == 400
    assert "exchange" in exc.value.detail.lower()


def test_paper_startkapitaal_requires_whole_cents():
    service = BotService(_FakeSession())
    payload = {
        "name": "BTC Paper Bot",
        "strategy_id": 42,
        "mode": "manual",
        "is_live": False,
        "paper_initial_cash_eur": 0.001,
    }

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.validate_bot_payload(payload, user_id=1))

    assert exc.value.status_code == 400
    assert "eurocenten" in exc.value.detail


def test_paper_reassessment_reports_whether_a_new_decision_was_saved(monkeypatch):
    from backend.services import bot_service as module

    service = BotService(_FakeSession())
    monkeypatch.setattr(module, "sync_run_trading_bot_execution", lambda *_args: {
        "ok": True, "decisions": [],
    })
    unchanged = asyncio.run(service.run_bot_agent_generate(9, None, user_id=1))
    assert unchanged["ok"] is True
    assert unchanged["generated"] is False
    assert unchanged["decision_ids"] == []

    monkeypatch.setattr(module, "sync_run_trading_bot_execution", lambda *_args: {
        "ok": True, "decisions": [{"decision_id": 42, "action": "hold"}],
    })
    created = asyncio.run(service.run_bot_agent_generate(9, None, user_id=1))
    assert created["generated"] is True
    assert created["decision_ids"] == [42]


def test_paper_reassessment_explains_a_skipped_dca_day(monkeypatch):
    from backend.services import bot_service as module

    service = BotService(_FakeSession())
    monkeypatch.setattr(module, "sync_run_trading_bot_execution", lambda *_args: {
        "ok": True, "decisions": [], "skip_reasons": {9: "not_due"},
    })

    result = asyncio.run(service.run_bot_agent_generate(9, None, user_id=1))
    assert result["generated"] is False
    assert result["skip_reason"] == "not_due"


def test_paper_reassessment_rejects_live_bot_before_worker(monkeypatch):
    from backend.services import bot_service as module

    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            assert (user_id, bot_id) == (1, 9)
            return {"is_live": True, "is_active": True}

    service = BotService(_FakeSession())
    service.repository = Repo()
    monkeypatch.setattr(module, "sync_run_trading_bot_execution", lambda *_args: pytest.fail("worker called"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.run_bot_agent_generate(9, None, user_id=1, paper_only=True))
    assert exc.value.status_code == 409


def test_paper_reassessment_reports_execution_outcome_and_worker_failure(monkeypatch):
    from backend.services import bot_service as module

    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {"is_live": False, "is_active": True}
        async def record_paper_assessment(self, user_id, bot_id, decision_date, outcome, trace_id):
            assert (user_id, bot_id, outcome) == (1, 9, "execution_failed")
            return {"outcome": outcome, "checked_at": datetime.now(timezone.utc)}

    service = BotService(_FakeSession())
    service.repository = Repo()
    monkeypatch.setattr(module, "sync_run_trading_bot_execution", lambda *_args: {
        "ok": True, "decisions": [{"decision_id": 43, "execution_status": "failed: cash"}],
    })
    failed_execution = asyncio.run(service.run_bot_agent_generate(9, None, user_id=1, paper_only=True))
    assert failed_execution["generated"] is True
    assert failed_execution["paper_order_filled"] is False
    assert failed_execution["execution_failed"] is True
    assert failed_execution["paper_assessment"]["outcome"] == "execution_failed"

    monkeypatch.setattr(module, "sync_run_trading_bot_execution", lambda *_args: {"ok": False})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.run_bot_agent_generate(9, None, user_id=1, paper_only=True))
    assert exc.value.status_code == 502


def test_paper_only_worker_does_not_assess_live_bot(monkeypatch):
    from backend.engine import trading_bot_execution as worker

    class Connection:
        def close(self):
            pass

    monkeypatch.setattr(worker, "get_db_connection", Connection)
    monkeypatch.setattr(worker, "_get_active_bots", lambda *_args: [{
        "bot_id": 9, "is_live": True, "is_active": True,
    }])
    result = worker.run_trading_bot_execution(user_id=1, bot_id=9, paper_only=True)
    assert result == {"ok": False, "error": "paper_mode_changed"}


def test_paper_reassessment_uses_server_today_even_with_caller_date(monkeypatch):
    from datetime import date
    from backend.services import bot_service as module

    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {"is_live": False, "is_active": True}
        async def record_paper_assessment(self, user_id, bot_id, decision_date, outcome, trace_id):
            assert (user_id, bot_id, decision_date, outcome) == (1, 9, date.today(), "no_new_decision")
            return {"outcome": outcome, "checked_at": datetime.now(timezone.utc)}

    calls = []

    def worker(user_id, report_date, bot_id, paper_only):
        calls.append((user_id, report_date, bot_id, paper_only))
        return {"ok": True, "decisions": []}

    service = BotService(_FakeSession())
    service.repository = Repo()
    monkeypatch.setattr(module, "sync_run_trading_bot_execution", worker)
    asyncio.run(service.run_bot_agent_generate(9, "2030-01-15", user_id=1, paper_only=True))
    assert calls == [(1, date.today(), 9, True)]


def test_manual_paper_order_rechecks_budget_after_bot_lock(monkeypatch):
    service = BotService(_FakeSession())

    class Repo(_ManualOrderRepo):
        reads = 0

        async def get_bot_config(self, user_id, bot_id):
            self.reads += 1
            bot = await super().get_bot_config(user_id, bot_id)
            bot.update(is_live=False, mode="manual", budget_total_eur=100 if self.reads == 1 else 20)
            return bot

        async def get_paper_cash(self, **_fields):
            return 100

        async def get_asset_quote_currencies(self, _symbols):
            return {"BTC": "EUR"}

    repo = Repo()
    service.repository = repo

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    async def no_live_context(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    monkeypatch.setattr(service, "require_live_manual_order_preflight_context", no_live_context)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001,
                                   price=50000, price_currency="EUR", value_eur=50,
                                   idempotency_key="paper-lock-test")
    payload.paper_preview_token = service._paper_preview_token(
        user_id=1, payload=payload, quantity=payload.quantity,
        price=payload.price, gross_eur=50,
        source_quote_currency="EUR",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 400
    assert "Totaal budget overschreden" in exc.value.detail
    assert repo.reads == 2
    assert repo.created_orders == 0


def test_bot_creation_rejects_duplicate_strategy_bot():
    service = BotService(_FakeSession(duplicate_strategy_bot_id=7))
    payload = {
        "name": "BTC Bot",
        "strategy_id": 42,
        "mode": "manual",
        "is_live": False,
        "risk_profile": "balanced",
        "cadence": "daily",
        "base_currency": "EUR",
    }

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.validate_bot_payload(payload, user_id=1))

    assert exc.value.status_code == 409
    assert "bestaat al bot #7" in exc.value.detail


def test_bot_update_allows_current_bot_strategy_link():
    service = BotService(_FakeSession(duplicate_strategy_bot_id=7))
    payload = {
        "name": "BTC Bot",
        "strategy_id": 42,
        "mode": "manual",
        "is_live": False,
        "risk_profile": "balanced",
        "cadence": "daily",
        "base_currency": "EUR",
    }

    import asyncio
    asyncio.run(service.validate_bot_payload(payload, user_id=1, is_update=True, bot_id=7))

    assert payload["symbol"] == "BTC"


def test_pair_bound_bot_inherits_exact_market_from_owned_strategy():
    class Session(_FakeSession):
        async def execute(self, query, params=None):
            if "from strategies s" in str(query).lower():
                return _FakeResult((42, "BTC", 73, 73))
            return await super().execute(query, params)

    payload = {"name": "BTC/EUR Paper", "strategy_id": 42, "mode": "manual",
               "is_live": False, "budget_total_eur": 100}
    asyncio.run(BotService(Session()).validate_bot_payload(payload, user_id=1))
    assert payload["symbol"] == "BTC"
    assert payload["market_id"] == 73


def test_pair_bound_bot_rejects_strategy_setup_market_disagreement():
    class Session(_FakeSession):
        async def execute(self, query, params=None):
            if "from strategies s" in str(query).lower():
                return _FakeResult((42, "BTC", 73, 74))
            return await super().execute(query, params)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(BotService(Session()).validate_bot_payload(
            {"name": "BTC Paper", "strategy_id": 42}, user_id=1))
    assert exc.value.status_code == 409


def test_bot_contract_exposes_consistent_top_level_ids_and_nested_strategy():
    service = BotService(_FakeSession())
    contract = service._bot_contract({
        "id": 9,
        "name": "BTC Paper Bot",
        "strategy_id": 42,
        "strategy_name": "BTC Strategy",
        "setup_type": "dca",
        "setup_id": 5,
        "setup_name": "BTC Setup",
        "setup_symbol": "BTC",
        "symbol": "BTC",
        "timeframe": "1W",
        "setup_timeframe": "1D",
        "dca_frequency": "monthly",
        "dca_month_day": 5,
        "is_active": True,
        "is_live": False,
        "mode": "manual",
        "cadence": "daily",
        "risk_profile": "balanced",
        "base_currency": "EUR",
        "budget_total_eur": 1000,
        "budget_daily_limit_eur": 100,
        "budget_min_order_eur": 10,
        "budget_max_order_eur": 50,
        "max_asset_exposure_pct": 100,
        "created_at": None,
        "updated_at": None,
    })

    assert contract["bot_id"] == 9
    assert contract["strategy_id"] == 42
    assert contract["verified"]["bot"] is True
    assert contract["bot"]["bot_id"] == 9
    assert contract["bot"]["is_live"] is False
    assert contract["bot"]["strategy"]["timeframe"] == "1W"
    assert contract["bot"]["strategy"]["setup"]["timeframe"] == "1D"
    assert contract["bot"]["strategy"]["setup"]["dca_month_day"] == 5
    assert contract["bot"]["strategy_id"] == 42
    assert contract["bot"]["strategy"]["id"] == 42
    assert contract["budget"]["total_eur"] == 1000


def test_dca_schedule_status_uses_saved_weekday_without_creating_a_decision():
    setup = {"setup_type": "dca", "dca_frequency": "weekly", "dca_day": "5"}
    confirmed_fixed = {"execution_mode": "fixed", "base_amount": 80, "decision_curve": None}
    assert _dca_schedule_status(setup, date(2026, 10, 20), confirmed_fixed) == {
        "as_of_date": "2026-10-20",
        "due_today": False,
        "next_due_date": "2026-10-23",
    }
    assert _dca_schedule_status(setup, date(2026, 10, 23), confirmed_fixed)["due_today"] is True
    assert _dca_schedule_status(setup, date(2026, 10, 20), {
        **confirmed_fixed, "base_amount": Decimal("80.00"),
    })["next_due_date"] == "2026-10-23"
    assert _dca_schedule_status(setup, date(2026, 10, 20), {
        "execution_mode": "custom", "base_amount": 80, "decision_curve": None,
    }) is None
    _, smart = split_confirmed_dca_plan({
        "name": "BTC Smart", "symbol": "BTC", "setup_type": "dca", "timeframe": "1D",
        "dca_frequency": "weekly", "dca_day": "friday", "dca_amount_mode": "score_bands",
        "base_amount": 80, "score_source": "benchmark_score", "low_threshold": 40,
        "high_threshold": 70, "low_score_percent": 50, "mid_score_percent": 100,
        "high_score_percent": 150,
    })
    assert _dca_schedule_status(setup, date(2026, 10, 20), smart)["next_due_date"] == "2026-10-23"
    assert _dca_schedule_status({"setup_type": "trade"}, date(2026, 10, 20), confirmed_fixed) is None


def test_bot_list_keeps_saved_setup_schedule_separate_from_strategy_timeframe():
    class Repo:
        async def get_bot_configs(self, user_id):
            assert user_id == 7
            return [{
                "id": 9, "name": "ETH Paper", "is_active": True, "is_live": False,
                "mode": "manual", "cadence": "daily", "risk_profile": "balanced",
                "strategy_id": 42, "strategy_name": "ETH Strategy", "setup_type": "dca",
                "dca_amount_semantics": None, "execution_mode": "fixed",
                "base_amount": 25, "decision_curve": None,
                "setup_id": 5, "setup_name": "ETH DCA", "symbol": "ETH",
                "timeframe": "1W", "setup_timeframe": "1D",
                "dca_frequency": "monthly", "dca_day": None, "dca_month_day": 5,
                "base_currency": "EUR", "last_run": None, "created_at": None,
                "updated_at": None, "budget_total_eur": 100,
                "paper_initial_cash_eur": 25,
                "budget_daily_limit_eur": 100, "budget_min_order_eur": 1,
                "budget_max_order_eur": 100, "max_asset_exposure_pct": 100,
            }]
        async def latest_paper_assessments(self, user_id):
            assert user_id == 7
            return {9: {"outcome": "not_due", "checked_at": datetime.now(timezone.utc)}}

    service = BotService(_FakeSession())
    service.repository = Repo()
    bot = asyncio.run(service.get_bot_configs(7))[0]

    assert bot["is_live"] is False
    assert bot["strategy"]["timeframe"] == "1W"
    assert bot["strategy"]["setup"]["timeframe"] == "1D"
    assert bot["strategy"]["setup"]["dca_frequency"] == "monthly"
    assert bot["strategy"]["setup"]["dca_month_day"] == 5
    assert bot["paper_initial_cash_eur"] == 25
    assert bot["paper_last_assessment"]["outcome"] == "not_due"
    assert bot["dca_schedule_status"]["next_due_date"]


def test_bot_update_pressure_event_detects_budget_live_and_mode_risk():
    service = BotService(_FakeSession())
    existing = {
        "id": 9,
        "strategy_id": 42,
        "symbol": "BTC",
        "mode": "manual",
        "is_live": False,
        "risk_profile": "balanced",
        "budget_total_eur": 500,
        "budget_daily_limit_eur": 50,
        "budget_max_order_eur": 25,
    }
    merged = {
        **existing,
        "mode": "auto",
        "is_live": True,
        "risk_profile": "aggressive",
        "budget_total_eur": 1000,
        "budget_daily_limit_eur": 100,
    }
    updates = {
        "mode": "auto",
        "is_live": True,
        "risk_profile": "aggressive",
        "budget_total_eur": 1000,
        "budget_daily_limit_eur": 100,
    }

    event = service._bot_update_pressure_event(existing, merged, updates)

    assert event["type"] == "plan_deviation_attempt"
    assert event["severity"] == "high"
    assert any("budget_total_eur verhoogd" in reason for reason in event["reasons"])
    assert any("bot naar live" in reason for reason in event["reasons"])
    assert any("mode verhoogd" in reason for reason in event["reasons"])


def test_setting_positive_caps_from_unlimited_does_not_require_risk_acknowledgement():
    service = BotService(_FakeSession())
    existing = {
        "id": 9, "symbol": "BTC", "is_live": False,
        "budget_total_eur": 0, "budget_daily_limit_eur": 0,
        "budget_max_order_eur": 0,
    }
    updates = {
        "budget_total_eur": 50, "budget_daily_limit_eur": 25,
        "budget_max_order_eur": 25,
    }
    assert service._bot_update_pressure_event(existing, {**existing, **updates}, updates) is None


def test_live_manual_order_requires_idempotency_and_risk_acknowledgement():
    service = BotService(_FakeSession())
    service.repository = _ManualOrderRepo()
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.01, price=50000)

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_ORDER_IDEMPOTENCY_REQUIRED"

    payload.idempotency_key = "manual-live-test-1"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_ORDER_RISK_ACK_REQUIRED"
    assert exc.value.detail["behavioral_event"]["type"] == "execution_pressure"


def test_live_manual_order_replay_does_not_submit_and_open_order_blocks_new_key():
    class Repo(_ManualOrderRepo):
        async def get_manual_order_by_idempotency_key(self, user_id, idempotency_key):
            if idempotency_key != "existing-live-order":
                return None
            return {
                "id": 51, "bot_id": 9, "symbol": "BTC", "side": "buy",
                "quantity": 0.001, "limit_price": 50000, "quote_amount_eur": 50,
                "status": "unknown_exchange_state",
            }

        async def get_unresolved_live_orders(self, user_id):
            return [{"id": 51, "bot_id": 9, "status": "unknown_exchange_state"}]

    service = BotService(_FakeSession())
    repo = Repo()
    service.repository = repo

    async def preflight(*_args):
        return {}

    service.require_live_manual_order_preflight_context = preflight
    payload = BotManualOrderSchema(
        bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000,
        idempotency_key="existing-live-order", risk_acknowledged=True,
    )
    replay = asyncio.run(service.create_manual_order(payload, user_id=1))
    assert replay["duplicate"] is True
    assert replay["order_id"] == 51
    assert replay["status"] == "unknown_exchange_state"
    assert repo.created_orders == 0

    payload.idempotency_key = "new-live-order"
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))
    assert exc.value.status_code == 409
    assert repo.created_orders == 0


def test_live_manual_order_checks_exchange_keys_before_order_insert():
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo()
    service.repository = repo
    service.exchange_repo = _NoExchangeKeys()
    async def _preflight_ok(user_id, bot_id, token):
        return {"token": token, "decision_id": 1}
    service.require_recent_live_preflight = _preflight_ok
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="buy",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-test-2",
        risk_acknowledged=True,
        live_preflight_token="preflight-ok",
    )

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_EXCHANGE_NOT_CONNECTED"
    assert repo.created_orders == 0


def test_live_manual_order_requires_recent_live_preflight_token():
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo()
    service.repository = repo
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="buy",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-test-preflight",
        risk_acknowledged=True,
    )

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_PREFLIGHT_REQUIRED"
    assert repo.created_orders == 0


def test_recent_live_preflight_token_must_be_successful_and_recent():
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "updated_at": now,
        "action": {
            "type": "live_preflight_bot_decision",
            "payload": {"bot_id": 9, "decision_id": 123},
        },
        "result": {
            "bot_id": 9,
            "decision_id": 123,
            "verified": {
                "live_preflight": True,
                "fresh_decision_context": True,
            },
            "freshness": {"status": "fresh"},
        },
    }
    service = BotService(_PreflightSession(payload))

    import asyncio
    result = asyncio.run(service.require_recent_live_preflight(1, 9, "token-123"))

    assert result["token"] == "token-123"
    assert result["decision_id"] == 123
    assert result["verified"]["live_preflight"] is True


def test_live_preflight_token_cannot_be_reused_for_new_decision():
    service = BotService(_FakeSession())
    service.repository = _ManualOrderRepo(decisions=[{
        "id": 2, "bot_id": 9, "decision_ts": datetime.now(timezone.utc),
    }])

    async def old_preflight(_user_id, _bot_id, _token):
        return {"decision_id": 1, "verified": {"live_preflight": True}}

    service.require_recent_live_preflight = old_preflight
    payload = BotManualOrderSchema(
        bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000,
        idempotency_key="stale-decision-token", risk_acknowledged=True,
        live_preflight_token="token-for-decision-1",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_manual_order_preflight_context(
            1, {"is_live": True, "symbol": "BTC"}, payload, 50,
        ))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_PREFLIGHT_DECISION_MISMATCH"


def test_recent_live_preflight_token_rejects_failed_preflight():
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "updated_at": now,
        "action": {"type": "live_preflight_bot_decision", "payload": {"bot_id": 9}},
        "result": {
            "bot_id": 9,
            "verified": {
                "live_preflight": False,
                "fresh_decision_context": False,
            },
            "freshness": {"status": "stale"},
        },
    }
    service = BotService(_PreflightSession(payload))

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_recent_live_preflight(1, 9, "token-123"))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_PREFLIGHT_NOT_APPROVED"


def test_recent_live_preflight_token_rejects_bot_mismatch():
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "updated_at": now,
        "action": {
            "type": "live_preflight_bot_decision",
            "payload": {"bot_id": 8, "decision_id": 123},
        },
        "result": {
            "bot_id": 8,
            "verified": {
                "live_preflight": True,
                "fresh_decision_context": True,
            },
        },
    }
    service = BotService(_PreflightSession(payload))

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_recent_live_preflight(1, 9, "token-123"))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_PREFLIGHT_BOT_MISMATCH"


def test_recent_live_preflight_token_rejects_stale_token():
    old = (datetime.now(timezone.utc) - timedelta(minutes=20)).isoformat()
    payload = {
        "updated_at": old,
        "action": {
            "type": "live_preflight_bot_decision",
            "payload": {"bot_id": 9, "decision_id": 123},
        },
        "result": {
            "bot_id": 9,
            "verified": {
                "live_preflight": True,
                "fresh_decision_context": True,
            },
        },
    }
    service = BotService(_PreflightSession(payload))

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_recent_live_preflight(1, 9, "token-123"))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_PREFLIGHT_STALE"
    assert exc.value.detail["age_minutes"] >= 20


def test_live_order_risk_context_blocks_notional_limit(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_MAX_MANUAL_ORDER_EUR", 25)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo()
    service.repository = repo
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_order_risk_context(1, bot, payload, 50))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_ORDER_NOTIONAL_LIMIT"
    assert exc.value.detail["behavioral_event"]["type"] == "execution_pressure"


def test_live_order_risk_context_blocks_portfolio_daily_limit(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_PORTFOLIO_DAILY_LIMIT_EUR", 100)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(live_daily_spend=80)
    service.repository = repo
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_order_risk_context(1, bot, payload, 50))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_PORTFOLIO_DAILY_LIMIT"


def test_live_order_risk_context_blocks_asset_exposure(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_MAX_ASSET_EXPOSURE_PCT", 70)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(portfolio_context={
        "global": {"total_equity": 1000, "current_position_value": 650},
        "bots": [{"symbol": "BTC", "position_value": 650}],
    })
    service.repository = repo
    _attach_live_portfolio_context(service, repo)
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.002, price=50000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_order_risk_context(1, bot, payload, 100))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_ASSET_EXPOSURE_LIMIT"
    assert exc.value.detail["projected_exposure_pct"] == 75.0


def test_live_buy_blocks_when_exchange_asset_has_no_verified_eur_price(monkeypatch):
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo()
    service.repository = repo
    async def active_keys(_user_id):
        return [SimpleNamespace(exchange_name="bitvavo", api_key="test", api_secret="test", api_passphrase=None)]
    async def client(*_args):
        return object()
    async def balance(_client):
        return {"total": {"EUR": 1000, "BTC": 0.001}}
    async def no_market_price(_symbol):
        raise HTTPException(409, "No verified EUR market price")
    async def no_ticker(*_args):
        raise RuntimeError("No verified EUR ticker")
    service.exchange_repo = SimpleNamespace(get_active_keys=active_keys)
    service.require_fresh_live_market_price = no_market_price
    monkeypatch.setattr("backend.services.bot_service.ExchangeService.get_client", client)
    monkeypatch.setattr("backend.services.bot_service.ExchangeService.fetch_balance", balance)
    monkeypatch.setattr("backend.services.bot_service.ExchangeService.fetch_ticker", no_ticker)
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.002, price=50000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_order_risk_context(1, bot, payload, 100))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_EXPOSURE_PRICE_UNAVAILABLE"


def test_live_order_portfolio_exposure_reports_asset_exposure_when_both_block(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_MAX_PORTFOLIO_EXPOSURE_PCT", 95)
    monkeypatch.setattr("backend.services.bot_service.LIVE_MAX_ASSET_EXPOSURE_PCT", 70)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(portfolio_context={
        "global": {"total_equity": 1000, "current_position_value": 940},
        "bots": [{"symbol": "BTC", "position_value": 690}],
    })
    service.repository = repo
    _attach_live_portfolio_context(service, repo)
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_order_risk_context(1, bot, payload, 50))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_PORTFOLIO_EXPOSURE_LIMIT"
    assert exc.value.detail["projected_exposure_pct"] == 99.0
    assert exc.value.detail["also_blocked_by"][0]["code"] == "LIVE_ASSET_EXPOSURE_LIMIT"
    assert exc.value.detail["also_blocked_by"][0]["projected_exposure_pct"] == 74.0
    assert exc.value.detail["asset_exposure_projection"]["would_block"] is True


def test_live_order_portfolio_exposure_reports_asset_projection_when_asset_does_not_block(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_MAX_PORTFOLIO_EXPOSURE_PCT", 95)
    monkeypatch.setattr("backend.services.bot_service.LIVE_MAX_ASSET_EXPOSURE_PCT", 70)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(portfolio_context={
        "global": {"total_equity": 1000, "current_position_value": 980},
        "bots": [{"symbol": "BTC", "position_value": 980}],
    })
    service.repository = repo
    _attach_live_portfolio_context(service, repo)
    bot = asyncio.run(repo.get_bot_config(1, 9))
    bot["symbol"] = "ETH"
    bot["max_asset_exposure_pct"] = 50
    payload = BotManualOrderSchema(bot_id=9, symbol="ETH", side="buy", quantity=0.001, price=50000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_order_risk_context(1, bot, payload, 50))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_PORTFOLIO_EXPOSURE_LIMIT"
    assert "also_blocked_by" not in exc.value.detail
    projection = exc.value.detail["asset_exposure_projection"]
    assert projection["symbol"] == "ETH"
    assert projection["projected_exposure_pct"] == 5.0
    assert projection["limit_pct"] == 50
    assert projection["would_block"] is False


def test_live_order_preflight_reports_setup_match_without_blocking(monkeypatch):
    class FakeMatchService:
        def __init__(self, session):
            pass

        async def for_asset(self, user_id, symbol):
            assert (user_id, symbol) == (1, "BTC")
            return {"source_status": "available", "matches": [
                {"setup_id": 42, "status": "outside_conditions", "score": 35},
            ]}

    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", FakeMatchService)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(bot_setup_id=42)
    service.repository = repo
    _attach_live_portfolio_context(service, repo)
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000)

    result = asyncio.run(service.require_live_order_risk_context(1, bot, payload, 50))
    assert {"code": "setup_match_information", "ok": True, "setup_id": 42,
            "status": "outside_conditions", "setup_match_score": 35,
            "source_status": "available", "execution_blocked": False} in result["checks"]


def test_live_sell_risk_context_reports_setup_match_without_buy_exposure(monkeypatch):
    class FakeMatchService:
        def __init__(self, session):
            pass

        async def for_asset(self, user_id, symbol):
            assert (user_id, symbol) == (1, "BTC")
            return {"source_status": "available", "matches": [
                {"setup_id": 42, "status": "outside_conditions", "score": 35},
            ]}

    monkeypatch.setattr("backend.services.setup_market_match_service.SetupMarketMatchService", FakeMatchService)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(bot_setup_id=42)
    service.repository = repo
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="sell", quantity=0.001, price=50000)

    result = asyncio.run(service.require_live_order_risk_context(1, bot, payload, 50))

    assert {"code": "setup_match_information", "ok": True, "setup_id": 42,
            "status": "outside_conditions", "setup_match_score": 35,
            "source_status": "available", "execution_blocked": False} in result["checks"]
    assert not any(check["code"] in {"portfolio_exposure", "asset_exposure"} for check in result["checks"])


def test_fresh_live_market_price_context_returns_snapshot():
    service = BotService(_FakeSession())
    market_ts = datetime.now(timezone.utc)
    service.repository = _ManualOrderRepo(market_snapshot={"price": 50123.45, "timestamp": market_ts})

    result = asyncio.run(service.require_fresh_live_market_price("btc"))

    assert result["symbol"] == "BTC"
    assert result["market_price"] == 50123.45
    assert result["age_seconds"] < 5
    assert result["stale_after_seconds"] == 300


def test_live_market_price_context_rejects_non_eur_quote():
    service = BotService(_FakeSession())
    service.repository = _ManualOrderRepo(market_snapshot={
        "price": 50000, "timestamp": datetime.now(timezone.utc), "quote_currency": "USDT",
    })

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_fresh_live_market_price("BTC"))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_MARKET_PRICE_QUOTE_UNVERIFIED"


def test_live_market_price_context_blocks_missing_snapshot():
    service = BotService(_FakeSession())
    service.repository = _ManualOrderRepo(market_snapshot=None)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_fresh_live_market_price("BTC"))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_MARKET_PRICE_MISSING"


def test_live_market_price_context_blocks_stale_snapshot(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_MARKET_PRICE_STALE_AFTER_SECONDS", 300)
    service = BotService(_FakeSession())
    stale_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    service.repository = _ManualOrderRepo(market_snapshot={"price": 50000, "timestamp": stale_ts})

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_fresh_live_market_price("BTC"))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_MARKET_PRICE_STALE"
    assert exc.value.detail["age_seconds"] >= 600
    assert exc.value.detail["stale_after_seconds"] == 300


def test_live_manual_order_blocks_when_market_price_is_stale(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_MARKET_PRICE_STALE_AFTER_SECONDS", 300)
    service = BotService(_FakeSession())
    stale_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    repo = _ManualOrderRepo(market_snapshot={"price": 50000, "timestamp": stale_ts})
    service.repository = repo

    async def _preflight_ok(user_id, bot_id, token):
        return {"token": token, "decision_id": 1}

    service.require_recent_live_preflight = _preflight_ok
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="buy",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-market-stale",
        risk_acknowledged=True,
        live_preflight_token="preflight-ok",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_MARKET_PRICE_STALE"
    assert repo.created_orders == 0


def test_live_manual_order_preflight_is_not_persisted_and_returns_guardrail_context():
    session = _FakeSession()
    service = BotService(session)
    repo = _ManualOrderRepo()
    service.repository = repo
    _attach_live_portfolio_context(service, repo)

    async def _preflight_ok(user_id, bot_id, token):
        return {
            "token": token,
            "decision_id": 1,
            "verified": {"live_preflight": True, "fresh_decision_context": True},
            "freshness": {"status": "fresh"},
        }

    service.require_recent_live_preflight = _preflight_ok
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="buy",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-dry-run",
        risk_acknowledged=True,
        live_preflight_token="preflight-ok",
    )

    result = asyncio.run(service.preflight_manual_order(payload, user_id=1))

    assert result["ok"] is True
    assert result["not_persisted"] is True
    assert result["exchange_order_created"] is False
    assert result["order_id"] is None
    assert result["live_market_price"]["symbol"] == "BTC"
    assert result["live_order_guardrails"]["ok"] is True
    assert result["verified"]["no_exchange_order"] is True
    assert repo.created_orders == 0
    audit_events = [
        item for item in session.executed
        if item["params"].get("type") == "live_manual_order_preflight"
    ]
    assert len(audit_events) == 1
    audit_payload = json.loads(audit_events[0]["params"]["payload"])
    assert audit_payload["result"]["execution_audit"]["not_persisted"] is True
    assert audit_payload["result"]["execution_audit"]["exchange_order_created"] is False


def test_live_manual_preflight_uses_verified_eur_ticker_when_market_data_is_usdt(monkeypatch):
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(market_snapshot={
        "price": 50000, "timestamp": datetime.now(timezone.utc), "quote_currency": "USDT",
    })
    service.repository = repo
    _attach_live_portfolio_context(service, repo)
    async def active_keys(_user_id):
        return [SimpleNamespace(exchange_name="bitvavo", api_key="test", api_secret="test", api_passphrase=None)]
    async def client(*_args):
        return object()
    async def ticker(_client, _symbol):
        return {"symbol": "BTC/EUR", "last": 50000, "bid": 49999, "ask": 50001}
    async def preflight(_user_id, _bot_id, token):
        return {"token": token, "decision_id": 1}
    service.exchange_repo = SimpleNamespace(get_active_keys=active_keys)
    service.require_recent_live_preflight = preflight
    monkeypatch.setattr("backend.services.bot_service.ExchangeService.get_client", client)
    monkeypatch.setattr("backend.services.bot_service.ExchangeService.fetch_ticker", ticker)
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(
        bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000,
        idempotency_key="manual-live-eur-ticker", risk_acknowledged=True,
        live_preflight_token="preflight-ok",
    )

    result = asyncio.run(service.require_live_manual_order_preflight_context(1, bot, payload, 50))

    assert result["live_market_price"]["source"] == "verified_exchange_eur_ticker"
    assert result["live_market_price"]["market_price"] == 50000
    assert repo.created_orders == 0


def test_live_manual_order_block_records_execution_audit():
    session = _FakeSession()
    service = BotService(session)
    service.repository = _ManualOrderRepo()
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="buy",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-blocked",
        risk_acknowledged=True,
        live_preflight_token="preflight-ok",
    )
    exc = HTTPException(409, {
        "code": "LIVE_MARKET_PRICE_STALE",
        "message": "Marktprijs voor BTC is te oud.",
        "age_seconds": 900,
    })

    asyncio.run(service.record_live_order_block_from_exception(
        payload,
        user_id=1,
        exc=exc,
        source="manual_order_preflight",
    ))

    audit_events = [
        item for item in session.executed
        if item["params"].get("type") == "live_manual_order_blocked"
    ]
    assert len(audit_events) == 1
    audit_payload = json.loads(audit_events[0]["params"]["payload"])
    assert audit_payload["result"]["status"] == "blocked"
    assert audit_payload["result"]["execution_audit"]["code"] == "LIVE_MARKET_PRICE_STALE"
    assert audit_payload["result"]["execution_audit"]["notional_eur"] == 50


def test_live_manual_order_block_records_setup_block_ack_when_acknowledged():
    session = _FakeSession()
    service = BotService(session)
    service.repository = _ManualOrderRepo()
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="sell",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-blocked-ack",
        risk_acknowledged=True,
        setup_block_acknowledged=True,
        live_preflight_token="preflight-ok",
    )
    exc = HTTPException(409, {
        "code": "LIVE_MARKET_PRICE_STALE",
        "message": "Marktprijs voor BTC is te oud.",
    })

    asyncio.run(service.record_live_order_block_from_exception(
        payload,
        user_id=1,
        exc=exc,
        source="manual_order_preflight",
    ))

    ack_events = [
        item for item in session.executed
        if item["params"].get("type") == "live_setup_block_acknowledged"
    ]
    assert len(ack_events) == 1
    ack_payload = json.loads(ack_events[0]["params"]["payload"])
    assert ack_payload["result"]["execution_audit"]["setup_block_acknowledged"] is True
    assert ack_payload["result"]["execution_audit"]["code"] == "LIVE_MARKET_PRICE_STALE"


def test_live_manual_order_preflight_reuses_stale_market_price_guardrail(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_MARKET_PRICE_STALE_AFTER_SECONDS", 300)
    service = BotService(_FakeSession())
    stale_ts = datetime.now(timezone.utc) - timedelta(minutes=10)
    repo = _ManualOrderRepo(market_snapshot={"price": 50000, "timestamp": stale_ts})
    service.repository = repo

    async def _preflight_ok(user_id, bot_id, token):
        return {"token": token, "decision_id": 1}

    service.require_recent_live_preflight = _preflight_ok
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="buy",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-dry-run-stale",
        risk_acknowledged=True,
        live_preflight_token="preflight-ok",
    )

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.preflight_manual_order(payload, user_id=1))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_MARKET_PRICE_STALE"
    assert repo.created_orders == 0


def test_live_manual_order_blocks_when_decision_context_is_missing():
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(decisions=[])
    service.repository = repo
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="buy",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-test-3",
        risk_acknowledged=True,
    )

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_EXECUTION_STALE_DATA"
    assert exc.value.detail["freshness"]["status"] == "missing"
    assert repo.created_orders == 0


def test_live_manual_order_blocks_when_decision_context_is_stale():
    service = BotService(_FakeSession())
    stale_ts = datetime.now(timezone.utc) - timedelta(minutes=90)
    repo = _ManualOrderRepo(decisions=[{
        "id": 1,
        "bot_id": 9,
        "decision_ts": stale_ts,
        "updated_at": stale_ts,
        "created_at": stale_ts,
    }])
    service.repository = repo
    payload = BotManualOrderSchema(
        bot_id=9,
        symbol="BTC",
        side="buy",
        quantity=0.001,
        price=50000,
        idempotency_key="manual-live-test-4",
        risk_acknowledged=True,
    )

    import asyncio
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.create_manual_order(payload, user_id=1))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_EXECUTION_STALE_DATA"
    assert exc.value.detail["freshness"]["status"] == "stale"
    assert repo.created_orders == 0
