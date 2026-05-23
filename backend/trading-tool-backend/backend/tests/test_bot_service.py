import asyncio
import pytest
from fastapi import HTTPException
from datetime import datetime, timedelta, timezone

from backend.schemas.bot_schema import BotManualOrderSchema
from backend.services.bot_service import BotService


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

    async def execute(self, query, params=None):
        sql = str(query).lower()
        params = params or {}
        if "lower(name)" in sql:
            return _FakeResult(None)
        if "from strategies s" in sql:
            return _FakeResult((params.get("strategy_id"), "BTC"))
        if "from bot_configs" in sql and "strategy_id" in sql:
            row = (self.duplicate_strategy_bot_id,) if self.duplicate_strategy_bot_id else None
            return _FakeResult(row)
        return _FakeResult(None)


class _ManualOrderRepo:
    def __init__(self, decisions=None, *, live_daily_spend=0, portfolio_context=None, bot_setup_id=None):
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


class _NoExchangeKeys:
    async def get_active_keys(self, user_id):
        return []


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
    assert contract["bot"]["strategy_id"] == 42
    assert contract["bot"]["strategy"]["id"] == 42
    assert contract["budget"]["total_eur"] == 1000


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


def test_live_manual_order_checks_exchange_keys_before_order_insert():
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo()
    service.repository = repo
    service.exchange_repo = _NoExchangeKeys()
    async def _preflight_ok(user_id, bot_id, token):
        return {"token": token}
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

    assert exc.value.status_code == 400
    assert "exchange keys" in exc.value.detail
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
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.002, price=50000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_order_risk_context(1, bot, payload, 100))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_ASSET_EXPOSURE_LIMIT"
    assert exc.value.detail["projected_exposure_pct"] == 75.0


def test_live_order_portfolio_exposure_reports_asset_exposure_when_both_block(monkeypatch):
    monkeypatch.setattr("backend.services.bot_service.LIVE_MAX_PORTFOLIO_EXPOSURE_PCT", 95)
    monkeypatch.setattr("backend.services.bot_service.LIVE_MAX_ASSET_EXPOSURE_PCT", 70)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(portfolio_context={
        "global": {"total_equity": 1000, "current_position_value": 940},
        "bots": [{"symbol": "BTC", "position_value": 690}],
    })
    service.repository = repo
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


def test_live_order_risk_context_requires_ack_for_blocked_setup(monkeypatch):
    class FakeScoreRepository:
        def __init__(self, session):
            pass

        async def fetch_active_setups(self, user_id):
            return [{"id": 42, "is_active": False, "score": 0}]

    monkeypatch.setattr("backend.infrastructure.repositories.score_repository.ScoreRepository", FakeScoreRepository)
    service = BotService(_FakeSession())
    repo = _ManualOrderRepo(bot_setup_id=42)
    service.repository = repo
    bot = asyncio.run(repo.get_bot_config(1, 9))
    payload = BotManualOrderSchema(bot_id=9, symbol="BTC", side="buy", quantity=0.001, price=50000)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.require_live_order_risk_context(1, bot, payload, 50))

    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "LIVE_SETUP_BLOCK_ACK_REQUIRED"

    payload.setup_block_acknowledged = True
    result = asyncio.run(service.require_live_order_risk_context(1, bot, payload, 50))
    assert any(check["code"] == "blocked_setup_ack" for check in result["checks"])


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
