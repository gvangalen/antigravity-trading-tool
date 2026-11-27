from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from types import SimpleNamespace

import pytest

from backend.services.paper_order_conversation_service import PaperOrderConversationService
from backend.services.paper_discretionary_order_service import PaperDiscretionaryOrderService
from backend.services.finn_v2_run_service import FinnV2RunService
from backend.services.trading_market_service import TradingMarketService


def test_one_off_paper_buy_retains_pair_and_amount_between_turns(monkeypatch):
    captured = []

    async def preview(self, **kwargs):
        captured.append(kwargs)
        return {
            "ok": True, "pair": "BTC/USDT", "amount_quote": kwargs["amount_quote"],
            "preview_token": "signed-preview", "idempotency_key": kwargs["idempotency_key"],
        }

    monkeypatch.setattr(PaperDiscretionaryOrderService, "preview", preview)

    async def flow():
        first = await PaperOrderConversationService.advance(
            message="Een eenmalige handmatige koop voor BTC met de huidige prijs.",
            prior=None, session=None, user_id=7, run_id="first-run",
        )
        assert first.draft == {"status": "collecting", "asset": "BTC"}
        assert "BTC/EUR" in first.text and "BTC/USDT" in first.text
        second = await PaperOrderConversationService.advance(
            message="usdt", prior=first.draft, session=None, user_id=7, run_id="second-run",
        )
        assert second.draft["asset"] == "BTC"
        assert second.draft["quote_currency"] == "USDT"
        assert "Hoeveel USDT" in second.text
        assert not PaperOrderConversationService.applies(
            "Moet ik nu BTC kopen?", second.draft,
        )
        third = await PaperOrderConversationService.advance(
            message="1000 usdt", prior=second.draft, session=None, user_id=7, run_id="third-run",
        )
        assert third.preview["ok"] is True
        assert third.draft["amount_quote"] == "1000"
        assert third.draft["status"] == "preview_ready"
        assert captured == [{
            "user_id": 7, "asset": "BTC", "quote_currency": "USDT",
            "amount_quote": "1000", "idempotency_key": "paper-order-third-run",
        }]
        assert not PaperOrderConversationService.applies(
            "Wat is de status van mijn ETH-bot?", third.draft,
        )
        assert PaperOrderConversationService.applies("Wijzig naar 500 USDT", third.draft)

    asyncio.run(flow())


@pytest.mark.parametrize(("text", "expected"), [
    ("1000 USDT", "1000"),
    ("1.234,56 USDT", "1234.56"),
    ("1,234.56 USDT", "1234.56"),
    ("1.000.000 USDT", "1000000"),
    ("1,000 USDT", "1000"),
    ("1.000,00 USDT", "1000.00"),
    ("1.23.4 USDT", None),
    ("1000,0000 USDT", None),
    ("1 000 USDT", None),
    ("1 234,56 USDT", None),
    ("1\u00a0234,56 USDT", None),
    ("1\u202f234,56 USDT", None),
    ("1'234,56 USDT", None),
    ("1’234,56 USDT", None),
])
def test_paper_amount_parser_never_takes_a_formatted_suffix(text, expected):
    assert PaperOrderConversationService._amount(text, "USDT") == expected


def test_ambiguous_amount_clears_previous_preview_and_asks_again(monkeypatch):
    preview = AsyncMock()
    monkeypatch.setattr(PaperDiscretionaryOrderService, "preview", preview)
    prior = {
        "status": "preview_ready", "asset": "BTC", "quote_currency": "USDT",
        "amount_quote": "1000", "preview_token": "old-token",
        "idempotency_key": "paper-order-old-run",
    }
    result = asyncio.run(PaperOrderConversationService.advance(
        message="Wijzig naar 1 234,56 USDT", prior=prior,
        session=None, user_id=7, run_id="new-run",
    ))
    assert result.preview is None
    assert result.draft.get("amount_quote") is None
    assert result.draft["status"] == "collecting"
    assert "preview_token" not in result.draft
    assert "idempotency_key" not in result.draft
    assert "Hoeveel USDT" in result.text
    preview.assert_not_called()


def test_paper_preview_needs_owned_free_reserve(monkeypatch):
    service = PaperDiscretionaryOrderService(session=None)
    observed = datetime.now(timezone.utc)
    service._quote = AsyncMock(return_value={
        "market_id": 3, "asset": "BTC", "quote_currency": "USDT",
        "market_fx_eur_per_unit": 0.9, "market_price_eur": 54000.0,
        "market_price": 60000.0, "market_price_at": observed,
        "market_fx_as_of": observed,
    })
    service.reserve.cash = AsyncMock(return_value=Decimal("800"))
    blocked = asyncio.run(service.preview(
        user_id=7, asset="BTC", quote_currency="USDT",
        amount_quote="1000", idempotency_key="preview-key-123",
    ))
    assert blocked["gross_eur"] == "900.00"
    assert blocked["fee_eur"] == "2.25"
    assert blocked["ok"] is False
    assert blocked["preview_token"] is None
    assert blocked["exchange_order_created"] is False

    service.reserve.cash = AsyncMock(return_value=Decimal("900"))
    allowed = asyncio.run(service.preview(
        user_id=7, asset="BTC", quote_currency="USDT",
        amount_quote="1000", idempotency_key="preview-key-123",
    ))
    assert allowed["ok"] is True
    assert allowed["requires_explicit_confirmation"] is True
    assert isinstance(allowed["preview_token"], str)


def test_unknown_asset_is_rejected_before_outbound_market_lookup(monkeypatch):
    class Missing:
        def first(self):
            return None

    session = SimpleNamespace(execute=AsyncMock(return_value=Missing()))
    market_lookup = AsyncMock()
    monkeypatch.setattr(TradingMarketService, "resolve", market_lookup)
    service = PaperDiscretionaryOrderService(session)
    with pytest.raises(Exception) as raised:
        asyncio.run(service._quote("UNKNOWNCOIN", "USDT"))
    assert raised.value.status_code == 422
    market_lookup.assert_not_called()


def test_confirmed_paper_fill_uses_fresh_price_and_replays_once():
    observed = datetime.now(timezone.utc)
    first_quote = {
        "market_id": 3, "asset": "BTC", "quote_currency": "USDT",
        "market_fx_eur_per_unit": 0.9, "market_price_eur": 54000.0,
        "market_price": 60000.0, "market_price_at": observed,
        "market_fx_as_of": observed,
    }
    fill_quote = {**first_quote, "market_price_eur": 54054.0,
                  "market_price": 60060.0}

    class Result:
        def __init__(self, row=None, scalar=None):
            self.row = row
            self.scalar = scalar

        def first(self):
            return self.row

        def scalar_one(self):
            return self.scalar

    class Session:
        def __init__(self):
            self.order = None
            self.position_writes = 0
            self.commits = 0

        async def execute(self, sql, params):
            statement = str(sql)
            if "SELECT id, market_id, asset_symbol" in statement:
                if self.order:
                    return Result(row=(42, 3, "BTC", "USDT", Decimal("1000"),
                                       Decimal(self.order["gross_eur"]),
                                       Decimal(self.order["quantity"]), "filled"))
                return Result()
            if "UPDATE paper_reserve_accounts" in statement:
                return Result(row=(Decimal("1100"),))
            if "INSERT INTO paper_discretionary_orders" in statement:
                self.order = params
                return Result(scalar=42)
            if "INSERT INTO paper_discretionary_positions" in statement:
                self.position_writes += 1
            return Result()

        async def commit(self):
            self.commits += 1

    session = Session()
    service = PaperDiscretionaryOrderService(session)
    service._quote = AsyncMock(side_effect=[first_quote, fill_quote])
    service.reserve.cash = AsyncMock(return_value=Decimal("2000"))

    async def flow():
        preview = await service.preview(
            user_id=7, asset="BTC", quote_currency="USDT", amount_quote="1000",
            idempotency_key="confirmed-key-123",
        )
        result = await service.execute(
            user_id=7, asset="BTC", quote_currency="USDT", amount_quote="1000",
            idempotency_key="confirmed-key-123", preview_token=preview["preview_token"],
        )
        assert result["ok"] is True and result["duplicate"] is False
        assert session.order["price_quote"] == "60060.0"
        assert session.order["price_eur"] == "54054.0"
        assert Decimal(session.order["quantity"]) < Decimal(preview["quantity"])
        assert session.position_writes == 1 and session.commits == 1
        replay = await service.execute(
            user_id=7, asset="BTC", quote_currency="USDT", amount_quote="1000",
            idempotency_key="confirmed-key-123", preview_token=preview["preview_token"],
        )
        assert replay["duplicate"] is True and replay["order_id"] == 42
        assert session.position_writes == 1 and session.commits == 1

    asyncio.run(flow())


def test_terminal_polling_envelope_carries_paper_card_only_for_completed_owner_run():
    service = object.__new__(FinnV2RunService)
    response = {
        "mode": "READ", "content": "Controleer de Paper-preview.",
        "response_source": "v2_runtime", "verifier_status": "not_run",
        "evidence": [], "uncertainty": [], "proposal_id": None,
        "confirmation_required": False,
    }
    preview = {"pair": "BTC/USDT", "preview_token": "signed", "ok": True}
    service.runtime_contracts = SimpleNamespace(get_for_run=AsyncMock(return_value=SimpleNamespace(
        terminal_projection_json={"response": response, "conversation_id": "conversation-owner"},
    )))

    def run(status):
        now = datetime.now(timezone.utc)
        return SimpleNamespace(
            id="run-123", conversation_id="conversation-owner", status=status,
            interaction_mode="READ", visibility="visible", policy_json=None,
            response_json={**response, "paper_order_preview": preview},
            created_at=now, updated_at=now, completed_at=now,
            error_code=None, error_message=None, retryable=False,
        )

    completed = asyncio.run(service.envelope_from_run(run("completed")))
    assert completed.runtime_trace["paper_order_preview"] == preview
    assert completed.response.content == response["content"]
    unavailable = asyncio.run(service.envelope_from_run(run("unavailable")))
    assert "paper_order_preview" not in unavailable.runtime_trace


@pytest.mark.parametrize("amount", ["0", "-1", "1.001", "nan", "inf"])
def test_paper_preview_rejects_invalid_amount_before_quote(amount):
    service = PaperDiscretionaryOrderService(session=None)
    service._quote = AsyncMock()
    with pytest.raises(Exception):
        asyncio.run(service.preview(
            user_id=7, asset="BTC", quote_currency="USDT",
            amount_quote=amount, idempotency_key="preview-key-123",
        ))
    service._quote.assert_not_called()
