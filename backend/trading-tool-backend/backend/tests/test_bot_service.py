import asyncio
import json
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone

from backend.schemas.bot_schema import BotConfigCreateSchema, BotConfigUpdateSchema, BotManualOrderSchema
from backend.services.bot_service import BotService


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
            return _FakeResult((params.get("strategy_id"), "BTC"))
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

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    async def no_live_context(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    monkeypatch.setattr(service, "require_live_manual_order_preflight_context", no_live_context)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.0002, price=50000)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.preflight_manual_order(payload, user_id=7))
    assert exc.value.status_code == 400
    assert "cash" in str(exc.value.detail).lower()


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

    service.repository = Repo()

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.0002, price=50000)
    result = asyncio.run(service.preview_manual_order(payload, user_id=7))
    assert result["guardrails"]["allowed"] is False
    assert result["guardrails"]["blocked_by"] == "insufficient_paper_cash"


_DEFAULT_MARKET_SNAPSHOT = object()


class _ManualOrderRepo:
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
            {"price": 50000, "timestamp": datetime.now(timezone.utc)}
            if market_snapshot is _DEFAULT_MARKET_SNAPSHOT
            else market_snapshot
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

    async def get_market_price(self, symbol):
        return {"AAPL": 240.0, "MSFT": 510.0}.get(symbol)


def test_bot_portfolios_use_each_bots_canonical_strategy_symbol():
    service = BotService.__new__(BotService)
    service.repository = _MultiAssetPortfolioRepo()

    result = asyncio.run(service.get_bot_portfolios(user_id=27))

    assert [item["symbol"] for item in result] == ["AAPL", "MSFT"]
    assert [item["stats"]["last_price"] for item in result] == [240.0, 510.0]


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
    monkeypatch.setattr(module, "sync_run_trading_bot_agent", lambda *_args: {
        "ok": True, "decisions": [],
    })
    unchanged = asyncio.run(service.run_bot_agent_generate(9, None, user_id=1))
    assert unchanged["ok"] is True
    assert unchanged["generated"] is False
    assert unchanged["decision_ids"] == []

    monkeypatch.setattr(module, "sync_run_trading_bot_agent", lambda *_args: {
        "ok": True, "decisions": [{"decision_id": 42, "action": "hold"}],
    })
    created = asyncio.run(service.run_bot_agent_generate(9, None, user_id=1))
    assert created["generated"] is True
    assert created["decision_ids"] == [42]


def test_paper_reassessment_rejects_live_bot_before_worker(monkeypatch):
    from backend.services import bot_service as module

    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            assert (user_id, bot_id) == (1, 9)
            return {"is_live": True, "is_active": True}

    service = BotService(_FakeSession())
    service.repository = Repo()
    monkeypatch.setattr(module, "sync_run_trading_bot_agent", lambda *_args: pytest.fail("worker called"))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.run_bot_agent_generate(9, None, user_id=1, paper_only=True))
    assert exc.value.status_code == 409


def test_paper_reassessment_reports_execution_outcome_and_worker_failure(monkeypatch):
    from backend.services import bot_service as module

    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {"is_live": False, "is_active": True}

    service = BotService(_FakeSession())
    service.repository = Repo()
    monkeypatch.setattr(module, "sync_run_trading_bot_agent", lambda *_args: {
        "ok": True, "decisions": [{"decision_id": 43, "execution_status": "failed: cash"}],
    })
    failed_execution = asyncio.run(service.run_bot_agent_generate(9, None, user_id=1, paper_only=True))
    assert failed_execution["generated"] is True
    assert failed_execution["paper_order_filled"] is False
    assert failed_execution["execution_failed"] is True

    monkeypatch.setattr(module, "sync_run_trading_bot_agent", lambda *_args: {"ok": False})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.run_bot_agent_generate(9, None, user_id=1, paper_only=True))
    assert exc.value.status_code == 502


def test_paper_only_worker_does_not_assess_live_bot(monkeypatch):
    from backend.ai_agents import trading_bot_agent as worker

    class Connection:
        def close(self):
            pass

    monkeypatch.setattr(worker, "get_db_connection", Connection)
    monkeypatch.setattr(worker, "_get_active_bots", lambda *_args: [{
        "bot_id": 9, "is_live": True, "is_active": True,
    }])
    result = worker.run_trading_bot_agent(user_id=1, bot_id=9, paper_only=True)
    assert result == {"ok": False, "error": "paper_mode_changed"}


def test_paper_reassessment_uses_server_today_even_with_caller_date(monkeypatch):
    from datetime import date
    from backend.services import bot_service as module

    class Repo:
        async def get_bot_config(self, user_id, bot_id):
            return {"is_live": False, "is_active": True}

    calls = []

    def worker(user_id, report_date, bot_id, paper_only):
        calls.append((user_id, report_date, bot_id, paper_only))
        return {"ok": True, "decisions": []}

    service = BotService(_FakeSession())
    service.repository = Repo()
    monkeypatch.setattr(module, "sync_run_trading_bot_agent", worker)
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

    repo = Repo()
    service.repository = repo

    async def allowed(*_args, **_kwargs):
        return {"allowed": True}

    async def no_live_context(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(service, "_paper_manual_buy_match", allowed)
    monkeypatch.setattr(service, "require_live_manual_order_preflight_context", no_live_context)
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000)

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


def test_bot_list_keeps_saved_setup_schedule_separate_from_strategy_timeframe():
    class Repo:
        async def get_bot_configs(self, user_id):
            assert user_id == 7
            return [{
                "id": 9, "name": "ETH Paper", "is_active": True, "is_live": False,
                "mode": "manual", "cadence": "daily", "risk_profile": "balanced",
                "strategy_id": 42, "strategy_name": "ETH Strategy", "setup_type": "dca",
                "setup_id": 5, "setup_name": "ETH DCA", "symbol": "ETH",
                "timeframe": "1W", "setup_timeframe": "1D",
                "dca_frequency": "monthly", "dca_day": None, "dca_month_day": 5,
                "base_currency": "EUR", "last_run": None, "created_at": None,
                "updated_at": None, "budget_total_eur": 100,
                "paper_initial_cash_eur": 25,
                "budget_daily_limit_eur": 100, "budget_min_order_eur": 1,
                "budget_max_order_eur": 100, "max_asset_exposure_pct": 100,
            }]

    service = BotService(_FakeSession())
    service.repository = Repo()
    bot = asyncio.run(service.get_bot_configs(7))[0]

    assert bot["is_live"] is False
    assert bot["strategy"]["timeframe"] == "1W"
    assert bot["strategy"]["setup"]["timeframe"] == "1D"
    assert bot["strategy"]["setup"]["dca_frequency"] == "monthly"
    assert bot["strategy"]["setup"]["dca_month_day"] == 5
    assert bot["paper_initial_cash_eur"] == 25


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
