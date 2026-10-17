import asyncio
import runpy
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.schemas.finn_bybit_derivative_schema import BybitDerivativeReviewCreate
from backend.services.finn_bybit_derivative_review_service import FinnBybitDerivativeReviewService
from backend.services.finn_bybit_derivative_import_service import FinnBybitDerivativeImportService


def test_derivative_confirmation_schema_is_strict():
    body = {"source_id": 7, "category": "inverse", "symbol": "BTCUSD",
            "position_idx": 2, "episode_key": "a" * 64,
            "closure_confirmed": True, "idempotency_key": uuid4()}
    assert BybitDerivativeReviewCreate(**body).position_idx == 2
    for change in ({"position_idx": True}, {"closure_confirmed": "true"},
                   {"category": "spot"}, {"episode_key": "wrong"}):
        with pytest.raises(ValidationError):
            BybitDerivativeReviewCreate(**{**body, **change})


def test_foreign_derivative_source_is_404_before_evidence_read(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")

    class Result:
        def fetchone(self):
            return None

    class Session:
        calls = []

        async def execute(self, statement, params):
            self.calls.append((str(statement), params))
            return Result()

    async def exercise():
        session = Session()
        with pytest.raises(HTTPException) as error:
            await FinnBybitDerivativeReviewService(session).candidates(2, 6, "linear")
        assert error.value.status_code == 404
        assert len(session.calls) == 1
        sql, params = session.calls[0]
        assert "c.user_id=:user_id AND c.source_id=:source_id" in sql
        assert params == {"user_id": 2, "source_id": 6, "category": "linear"}

    asyncio.run(exercise())


def test_foreign_derivative_streams_are_404_before_grouped_read(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")

    class Result:
        def fetchone(self):
            return None

    class Session:
        calls = []

        async def execute(self, statement, params):
            self.calls.append((str(statement), params))
            return Result()

    async def exercise():
        session = Session()
        with pytest.raises(HTTPException) as error:
            await FinnBybitDerivativeImportService(session).streams(2, 6, "linear")
        assert error.value.status_code == 404
        assert len(session.calls) == 1
        assert "user_id=:user_id AND source_id=:source_id" in session.calls[0][0]

    asyncio.run(exercise())


def test_order_lookup_rotates_past_sixteen_missing_orders():
    class Row:
        def __init__(self, order_id):
            self.category = "linear"
            self.order_id = order_id
            self.symbol = "BTCUSDT"

    class Result:
        def __init__(self, rows=None, value=None):
            self.rows = rows or []
            self.value = value

        def fetchall(self):
            return self.rows

        def scalar_one_or_none(self):
            return self.value

    class Session:
        def __init__(self):
            self.attempted = {}
            self.tick = 0
            self.pending = {f"order-{n:02d}" for n in range(20)}
            self.resolved = set()

        async def execute(self, statement, params):
            sql = str(statement)
            if "SELECT category,order_id,symbol,MIN(order_lookup_at)" in sql:
                assert "oldest_lookup NULLS FIRST" in sql
                ids = sorted(self.pending,
                             key=lambda name: (self.attempted.get(name, -1), name))
                return Result([Row(name) for name in ids[:params["limit"]]])
            if "SET order_lookup_at=NOW()" in sql:
                self.tick += 1
                self.attempted[params["order_id"]] = self.tick
            elif "INSERT INTO finn_bybit_derivative_orders" in sql:
                return Result(value=params["order_id"])
            elif "SET position_idx=:position_idx" in sql:
                self.pending.remove(params["order_id"])
                self.resolved.add(params["order_id"])
            else:
                raise AssertionError(sql)
            return Result()

    class Client:
        async def privateGetV5OrderHistory(self, params):
            order = params["orderId"]
            matches = ([{"orderId": order, "symbol": "BTCUSDT", "positionIdx": 2,
                         "side": "Sell", "reduceOnly": False, "orderStatus": "Filled"}]
                       if order == "order-19" else [])
            return {"retCode": 0, "result": {"category": params["category"], "list": matches}}

    async def exercise():
        session = Session()
        service = FinnBybitDerivativeImportService(session)
        assert await service._resolve_orders(1, 6, Client()) == 0
        assert set(session.attempted) == {f"order-{n:02d}" for n in range(16)}
        assert await service._resolve_orders(1, 6, Client()) == 1
        assert set(session.attempted) == {f"order-{n:02d}" for n in range(20)}
        assert session.resolved == {"order-19"}

    asyncio.run(exercise())


def test_episode_window_reports_older_evidence_even_without_candidates(monkeypatch):
    import backend.services.finn_bybit_derivative_review_service as module

    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")
    monkeypatch.setattr(module, "MAX_STREAM_EXECUTIONS", 2)
    monkeypatch.setattr(module, "MAX_EVIDENCE_WINDOW", 4)
    instant = datetime(2026, 10, 16, tzinfo=timezone.utc)

    class EvidenceRow:
        def __init__(self, number):
            self._mapping = {"id": number, "traded_at": instant,
                             "evidence_status": "material_event_unmodeled",
                             "symbol": "BTCUSDT"}

    class Result:
        def __init__(self, rows):
            self.rows = rows

        def fetchone(self):
            return self.rows[0] if self.rows else None

        def fetchall(self):
            return self.rows

    class Session:
        async def execute(self, statement, params):
            sql = str(statement)
            if "FROM finn_bybit_derivative_cursors c" in sql:
                return Result([object()])
            if "FROM finn_bybit_derivative_executions" in sql:
                assert "(traded_at,id)<" in sql
                assert params["row_limit"] == 5
                return Result([EvidenceRow(n) for n in (5, 4, 3, 2, 1)])
            return Result([])

    async def exercise():
        response = await FinnBybitDerivativeReviewService(Session()).candidates(1, 6, "linear")
        assert response["items"] == [] and response["status"] == "older_evidence_available"
        assert response["has_older_evidence"] is True
        assert response["next_evidence_before"] == {"before_at": instant, "before_id": 4}

    asyncio.run(exercise())


def test_derivative_migration_separates_spot_and_reserves_slices():
    path = Path(__file__).parents[1] / "scripts/migrations/2026_10_21_finn_bybit_derivative_evidence.py"
    sql = runpy.run_path(str(path))["SQL"]
    assert "finn_bybit_derivative_executions" in sql
    assert "origin='bybit_derivative_user_attested'" in sql
    assert "pnl_eur_before_fees IS NULL" in sql
    assert "PRIMARY KEY (user_id,execution_id,review_id,role)" in sql
    assert "REFERENCES finn_bybit_derivative_executions(user_id,id) ON DELETE RESTRICT" in sql
    assert "bot_ledger" not in sql and "bot_portfolios" not in sql
