"""User attestation never turns incomplete exchange evidence into a closed trade."""

import asyncio
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException

from backend.services.finn_exchange_trade_review_service import (
    FinnExchangeTradeReviewService, build_attested_position,
)


START = datetime(2026, 10, 16, tzinfo=timezone.utc)


def fill(index, side, qty, *, quote="EUR", fee="0", fee_currency="EUR", at=None,
         base="BTC", cost=None):
    return {
        "id": index, "source_id": 7, "exchange_order_id": f"order-{index}",
        "base_currency": base, "quote_currency": quote, "side": side,
        "qty": Decimal(str(qty)), "price_quote": Decimal("100"),
        "cost_quote": Decimal(str(cost if cost is not None else Decimal(str(qty)) * 100)),
        "fee_amount": Decimal(str(fee)) if fee is not None else None,
        "fee_currency": fee_currency,
        "traded_at": at or START + timedelta(minutes=index),
    }


def test_buy_add_on_partial_sells_produce_one_closed_position():
    position = build_attested_position([
        fill(1, "buy", "0.4", cost="40"),
        fill(2, "buy", "0.6", cost="70"),
        fill(3, "sell", "0.3", cost="45"),
        fill(4, "sell", "0.7", cost="84"),
    ])
    assert position["entry_qty"] == Decimal("1.0")
    assert position["pnl_eur_before_fees"] == Decimal("19")
    assert position["pnl_status"] == "before_fees_eur"
    assert len(position["fills"]) == 4
    assert position["cash_legs_by_currency"] == [
        {"currency": "EUR", "buy_cost": "110", "sell_proceeds": "129"}]
    assert "ledger_id" not in position["fills"][0]


def test_base_fee_is_part_of_quantity_closure_and_rebates_are_signed():
    position = build_attested_position([
        fill(1, "buy", "1", fee="0.01", fee_currency="BTC"),
        fill(2, "sell", "0.99", fee="0", fee_currency="BTC"),
    ])
    assert position["pnl_status"] == "not_comparable"
    assert position["pnl_eur_before_fees"] is None
    with pytest.raises(ValueError, match="volledig gesloten"):
        build_attested_position([
            fill(1, "buy", "1", fee="-0.01", fee_currency="BTC"),
            fill(2, "sell", "1", fee="0", fee_currency="BTC"),
        ])


@pytest.mark.parametrize("rows", [
    [fill(1, "sell", "1"), fill(2, "buy", "1")],
    [fill(1, "buy", "1"), fill(2, "sell", "1"), fill(3, "buy", "1"), fill(4, "sell", "1")],
    [fill(1, "buy", "1"), fill(2, "sell", "2")],
    [fill(1, "buy", "1"), fill(2, "sell", "0.5")],
    [fill(1, "buy", "1"), fill(2, "sell", "1", base="ETH")],
    [fill(1, "buy", "1", fee=None), fill(2, "sell", "1")],
    [fill(1, "buy", "1", at=START), fill(2, "sell", "1", at=START)],
])
def test_incomplete_or_ambiguous_selection_rejected(rows):
    with pytest.raises(ValueError):
        build_attested_position(rows)


def test_mixed_quote_never_fabricates_eur_outcome():
    position = build_attested_position([
        fill(1, "buy", "1", quote="EUR"),
        fill(2, "sell", "1", quote="USDT", fee_currency="USDT"),
    ])
    assert position["pnl_status"] == "not_comparable"
    assert position["pnl_eur_before_fees"] is None
    assert {leg["currency"] for leg in position["cash_legs_by_currency"]} == {"EUR", "USDT"}


def test_foreign_or_missing_fill_selection_is_not_disclosed(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")

    class Result:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class Session:
        statements = []
        rolled_back = False

        async def execute(self, statement, params):
            self.statements.append((str(statement), params))
            return Result()

        async def rollback(self):
            self.rolled_back = True

    async def exercise():
        session = Session()
        with pytest.raises(HTTPException) as error:
            await FinnExchangeTradeReviewService(session).create(
                11, fill_ids=[80, 81], closure_confirmed=True,
                same_account_confirmed=False, idempotency_key=uuid4())
        assert error.value.status_code == 404
        assert session.rolled_back
        assert all(params["user_id"] == 11 for _, params in session.statements)
        assert "f.user_id=:user_id" in session.statements[-1][0]

    asyncio.run(exercise())


def test_idempotent_replay_returns_same_review_without_new_insert(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")

    class Result:
        def __init__(self, row=None):
            self.row = row

        def fetchone(self):
            return self.row

    class Session:
        calls = []
        committed = False

        async def execute(self, statement, params):
            self.calls.append(str(statement))
            if "SELECT a.review_id" in str(statement):
                from backend.services.finn_exchange_trade_review_service import _canonical_digest
                return Result(SimpleNamespace(
                    review_id=42, request_digest=_canonical_digest([80, 81], False),
                    pnl_status="not_comparable"))
            return Result()

        async def commit(self):
            self.committed = True

    async def exercise():
        session = Session()
        result = await FinnExchangeTradeReviewService(session).create(
            11, fill_ids=[81, 80], closure_confirmed=True,
            same_account_confirmed=False, idempotency_key=uuid4())
        assert result == {"review_id": 42, "created": False,
                          "origin": "exchange_user_attested", "closure_basis": "user_confirmed",
                          "pnl_status": "not_comparable"}
        assert session.committed and len(session.calls) == 2

    asyncio.run(exercise())


def test_idempotency_key_cannot_be_reused_for_different_fillset(monkeypatch):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")

    class Result:
        def fetchone(self):
            return SimpleNamespace(review_id=42, request_digest="different", pnl_status="not_comparable")

    class Session:
        async def execute(self, statement, params):
            return Result() if "SELECT a.review_id" in str(statement) else SimpleNamespace()

        async def rollback(self):
            pass

    async def exercise():
        with pytest.raises(HTTPException) as error:
            await FinnExchangeTradeReviewService(Session()).create(
                11, fill_ids=[80, 81], closure_confirmed=True,
                same_account_confirmed=False, idempotency_key=uuid4())
        assert error.value.status_code == 409

    asyncio.run(exercise())


@pytest.mark.parametrize("sources,confirmed,bot_overlap,expected", [
    ([7, 8], False, False, 422),
    ([7, 8], True, False, None),
    ([7, 7], False, True, 409),
])
def test_cross_epoch_requires_confirmation_and_bot_order_overlap_is_blocked(
    monkeypatch, sources, confirmed, bot_overlap, expected,
):
    monkeypatch.setenv("FINN_TRADE_REVIEW_ROLLOUT", "all")

    class Result:
        def __init__(self, *, one=None, rows=None):
            self.one = one
            self.rows = rows or []

        def fetchone(self):
            return self.one

        def fetchall(self):
            return self.rows

    class Session:
        async def execute(self, statement, params):
            sql = str(statement)
            if "FROM finn_exchange_review_attestations a" in sql:
                return Result()
            if "JOIN bot_orders o" in sql:
                return Result(one=(1,) if bot_overlap else None)
            if "FROM finn_exchange_import_fills f\n" in sql and "f.id=ANY" in sql:
                rows = []
                for index, source_id in enumerate(sources):
                    item = {**fill(80 + index, "buy" if index == 0 else "sell", "1"),
                            "source_id": source_id, "exchange_trade_id": f"trade-{index}",
                            "symbol": "BTC/EUR", "exchange_name": "bitvavo",
                            "identity_kind": "credential_epoch"}
                    rows.append(SimpleNamespace(_mapping=item))
                return Result(rows=rows)
            if "FROM finn_exchange_review_fill_reservations r" in sql:
                return Result()
            if "INSERT INTO finn_trade_reviews" in sql:
                raise AssertionError("This test must stop before any review write")
            return Result()

        async def rollback(self):
            pass

    async def exercise():
        session = Session()
        if expected is not None:
            with pytest.raises(HTTPException) as error:
                await FinnExchangeTradeReviewService(session).create(
                    11, fill_ids=[80, 81], closure_confirmed=True,
                    same_account_confirmed=confirmed, idempotency_key=uuid4())
            assert error.value.status_code == expected
        else:
            with pytest.raises(AssertionError, match="before any review write"):
                await FinnExchangeTradeReviewService(session).create(
                    11, fill_ids=[80, 81], closure_confirmed=True,
                    same_account_confirmed=confirmed, idempotency_key=uuid4())

    asyncio.run(exercise())
