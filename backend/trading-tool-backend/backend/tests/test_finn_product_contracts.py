import asyncio

from backend.schemas.bot_schema import BotConfigCreateSchema
from backend.schemas.trading_schema import SetupCreateSchema, StrategyCreateSchema
from backend.services.bot_service import BotService
from backend.services.setup_service import SetupService
from backend.services.strategy_service import StrategyService


BTC_SETUP_PAYLOAD = {
    "name": "BTC Swing Daily 4H",
    "symbol": "BTC",
    "setup_type": "trade",
    "timeframe": "4H",
    "description": "Swing setup met daily trend en 4H entry.",
    "trend": "bullish",
}

AAPL_SETUP_PAYLOAD = {
    "name": "AAPL Investor Daily",
    "symbol": "AAPL",
    "setup_type": "trade",
    "timeframe": "1D",
    "description": "Investor setup met daily context.",
    "trend": "bullish",
}

BTC_STRATEGY_PAYLOAD = {
    "setup_id": 278,
    "execution_mode": "fixed",
    "base_amount": 1500,
    "name": "BTC Swing Plan",
    "entry": 62000,
    "stop_loss": 59800,
    "targets": [64000, 66000],
}

AAPL_STRATEGY_PAYLOAD = {
    "setup_id": 412,
    "execution_mode": "fixed",
    "base_amount": 2000,
    "name": "AAPL Investor Plan",
    "entry": 210,
    "stop_loss": 202,
    "targets": [218, 224],
}

BTC_BOT_PAYLOAD = {
    "name": "BTC Paper Bot",
    "strategy_id": 991,
    "mode": "manual",
    "is_live": False,
    "risk_profile": "balanced",
    "budget_total_eur": 1000,
    "budget_daily_limit_eur": 100,
    "budget_min_order_eur": 10,
    "budget_max_order_eur": 50,
    "max_asset_exposure_pct": 100,
    "cadence": "daily",
    "base_currency": "EUR",
}

AAPL_BOT_PAYLOAD = {
    "name": "AAPL Paper Bot",
    "strategy_id": 992,
    "mode": "manual",
    "is_live": False,
    "risk_profile": "conservative",
    "budget_total_eur": 2000,
    "budget_daily_limit_eur": 150,
    "budget_min_order_eur": 25,
    "budget_max_order_eur": 100,
    "max_asset_exposure_pct": 60,
    "cadence": "weekly",
    "base_currency": "USD",
}


class _BotSession:
    def __init__(self):
        self.executed = []

    async def execute(self, query, params=None):
        sql = str(query).lower()
        params = params or {}
        self.executed.append({"sql": sql, "params": params})

        class _Result:
            def __init__(self, row):
                self._row = row

            def fetchone(self):
                return self._row

        if "lower(name)" in sql:
            return _Result(None)
        if "from strategies s" in sql:
            strategy_id = params.get("strategy_id")
            symbol = "BTC" if strategy_id == 991 else "AAPL"
            return _Result((strategy_id, symbol))
        if "from bot_configs" in sql and "strategy_id" in sql:
            return _Result(None)
        return _Result(None)


def test_setup_contract_accepts_canonical_btc_and_aapl_payloads():
    service = SetupService(None)

    btc = dict(BTC_SETUP_PAYLOAD)
    aapl = dict(AAPL_SETUP_PAYLOAD)

    service.validate_setup_payload(btc)
    service.validate_setup_payload(aapl)

    assert SetupCreateSchema(**btc).symbol == "BTC"
    assert SetupCreateSchema(**aapl).symbol == "AAPL"


def test_strategy_contract_accepts_canonical_btc_and_aapl_trade_payloads():
    service = StrategyService(db_session=None)

    service._validate_trade_strategy(dict(BTC_STRATEGY_PAYLOAD))
    service._validate_trade_strategy(dict(AAPL_STRATEGY_PAYLOAD))

    assert StrategyCreateSchema(
        setup_id=BTC_STRATEGY_PAYLOAD["setup_id"],
        execution_mode=BTC_STRATEGY_PAYLOAD["execution_mode"],
        base_amount=BTC_STRATEGY_PAYLOAD["base_amount"],
        name=BTC_STRATEGY_PAYLOAD["name"],
    ).setup_id == 278


def test_bot_contract_accepts_canonical_btc_and_aapl_paper_payloads():
    service = BotService(_BotSession())

    btc = BotConfigCreateSchema(**BTC_BOT_PAYLOAD).dict()
    aapl = BotConfigCreateSchema(**AAPL_BOT_PAYLOAD).dict()

    asyncio.run(service.validate_bot_payload(btc, user_id=7))
    asyncio.run(service.validate_bot_payload(aapl, user_id=8))

    assert btc["symbol"] == "BTC"
    assert aapl["symbol"] == "AAPL"
    assert btc["is_live"] is False
    assert aapl["is_live"] is False
