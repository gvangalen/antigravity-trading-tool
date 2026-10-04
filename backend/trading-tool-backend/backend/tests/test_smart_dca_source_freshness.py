from datetime import datetime, timedelta, timezone
import asyncio
from unittest.mock import AsyncMock, Mock

from backend.utils.scoring_utils import score_source_is_fresh


def test_unknown_provider_candle_has_no_verified_source_timestamp():
    from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository

    session = Mock()
    session.flush = AsyncMock()
    repository = TechnicalDataRepository(session)
    row = asyncio.run(repository.add_indicator(
        "rsi", 50, 50, "", "", user_id=7, symbol="BTC", observed_at=None,
    ))
    assert row.timestamp is not None
    assert row.source_observed_at is None
    assert not score_source_is_fresh("technical", "rsi", row.source_observed_at, symbol="BTC")


def test_score_source_age_matches_release_cadence_and_asset_market():
    now = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)
    assert not score_source_is_fresh("technical", "rsi", now - timedelta(days=2), symbol="BTC", now=now)
    assert score_source_is_fresh("technical", "rsi", now - timedelta(days=2), symbol="AAPL", now=now)
    assert score_source_is_fresh("macro", "inflation_rate", now - timedelta(days=30), now=now)
    assert not score_source_is_fresh("macro", "inflation_rate", now - timedelta(days=90), now=now)
    assert not score_source_is_fresh("market", "fear_greed_index", None, now=now)


def test_legacy_receipt_timestamp_does_not_substitute_for_source_observation(monkeypatch):
    from backend.utils import scoring_utils

    class Cursor:
        def execute(self, sql, params):
            assert "source_observed_at" in sql

        def fetchall(self):
            # Legacy row has a recent timestamp, but the new source field is NULL.
            return [("fear_greed_index", 50, None)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(scoring_utils, "get_db_connection", lambda: Connection())
    assert scoring_utils.generate_scores_db("market", user_id=7, symbol="BTC")["scores"] == {}


def test_user_score_sync_retains_global_source_timestamp(monkeypatch):
    from backend.celery_task import user_scoring_sync_task as sync

    observed_at = datetime(2026, 9, 1, 12)
    statements = []

    class Cursor:
        def execute(self, sql, params=None):
            statements.append((sql, params))

        def fetchall(self):
            return [("fear_greed_index", 50, observed_at)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

    monkeypatch.setattr(sync, "score_indicator", lambda **_: {
        "score": 50, "trend": "flat", "interpretation": "", "action": "hold",
    })
    sync.sync_category_for_user(Connection(), 7, "market", "global_market_indicators", "market_data_indicators")
    assert statements[-1][1][-1] == observed_at
    assert "timestamp = EXCLUDED.timestamp" in statements[-1][0]


def test_daily_score_builder_refuses_old_indicator_even_if_it_has_a_value(monkeypatch):
    from backend.utils import scoring_utils

    old = datetime.now(timezone.utc) - timedelta(days=12)

    class Cursor:
        def execute(self, sql, params):
            pass

        def fetchall(self):
            return [("fear_greed_index", 50, old)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

        def close(self):
            pass

    monkeypatch.setattr(scoring_utils, "get_db_connection", lambda: Connection())
    monkeypatch.setattr(scoring_utils, "score_indicator", lambda **_: (_ for _ in ()).throw(
        AssertionError("stale source must not be scored")))
    result = scoring_utils.generate_scores_db("market", user_id=7, symbol="BTC")
    assert result["scores"] == {}


def test_legacy_exchange_indicator_keeps_its_candle_time(monkeypatch):
    from backend.utils.technical_interpreter import fetch_technical_value

    rows = [[1790985600000, "0", "0", "0", "100", "25"]]

    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return rows

    class Client:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

        async def get(self, _url):
            return Response()

    monkeypatch.setattr("backend.utils.technical_interpreter.httpx.AsyncClient", Client)
    result = asyncio.run(fetch_technical_value(
        "close", link="https://api.binance.com/api/v3/klines?symbol=BTCUSDT", symbol="BTC",
    ))
    assert result["value"] == 100.0
    assert result["observed_at"] is not None


def test_smart_dca_execution_rejects_freshly_stamped_score_with_old_component():
    from backend.ai_agents.trading_bot_agent import _get_daily_scores
    from backend.domain.finn_dca_plan_contract import benchmark_score, EQUAL_BENCHMARK_WEIGHTS

    old = datetime.now(timezone.utc) - timedelta(days=10)

    class Cursor:
        def execute(self, sql, params):
            self.sql = sql

        def fetchone(self):
            return (60, 60, 60, 60)

        def fetchall(self):
            return [("fear_greed_index", old)]

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    class Connection:
        def cursor(self):
            return Cursor()

    result = _get_daily_scores(Connection(), 7, datetime.now(timezone.utc).date(), "BTC")
    assert all(result["_source_available"][component] is False for component in (
        "market_score", "macro_score", "technical_score",
    ))
    assert benchmark_score({"market_score": result["market"], "macro_score": result["macro"],
                            "technical_score": result["technical"]},
                           EQUAL_BENCHMARK_WEIGHTS, result["_source_available"]) is None
