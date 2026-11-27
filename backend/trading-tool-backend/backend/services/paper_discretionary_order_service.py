"""Preview and execute a one-off Paper buy from the owner's free reserve."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP

from fastapi import HTTPException
from sqlalchemy import text

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.paper_reserve_repository import PaperReserveRepository
from backend.services.portfolio_fx_service import trade_quote_context
from backend.services.trading_market_service import TradingMarketService, MarketUnavailable
from backend.utils.auth_utils import create_token, decode_token


CENT = Decimal("0.01")
FEE_RATE = Decimal("0.0025")
PREVIEW_TTL = timedelta(minutes=5)
MAX_PRICE_MOVE = Decimal("0.005")


class PaperDiscretionaryOrderService:
    def __init__(self, session):
        self.session = session
        self.bots = BotRepository(session)
        self.reserve = PaperReserveRepository(session)

    @staticmethod
    def _amount(value: object) -> Decimal:
        try:
            amount = Decimal(str(value))
        except (TypeError, ValueError, InvalidOperation) as exc:
            raise HTTPException(422, "Geef een positief bedrag in de koersvaluta op.") from exc
        if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
            raise HTTPException(422, "Geef een positief bedrag in hele centen op.")
        return amount

    async def _quote(self, asset: str, quote_currency: str) -> dict:
        asset = str(asset or "").strip().upper()
        quote_currency = str(quote_currency or "").strip().upper()
        if quote_currency not in {"EUR", "USDT"}:
            raise HTTPException(422, "Kies een exact EUR- of USDT-handelspaar.")
        # Reject unknown/non-crypto symbols locally before the market resolver
        # can perform an outbound venue lookup for an untrusted preview input.
        catalog = await self.session.execute(text("""
            SELECT 1 FROM asset_catalog
            WHERE symbol=:asset AND asset_class='crypto' AND is_active=TRUE
            LIMIT 1
        """), {"asset": asset})
        if catalog.first() is None:
            raise HTTPException(422, "Kies een actief crypto-asset uit de catalogus.")
        try:
            market = await TradingMarketService(self.session).resolve(asset, quote_currency)
        except MarketUnavailable as exc:
            raise HTTPException(409, str(exc)) from exc
        row = (await self.bots.get_valuatable_exact_market_prices([market.id])).get(market.id)
        if (not row or str(row.get("symbol") or "").upper() != asset
                or str(row.get("quote_currency") or "").upper() != quote_currency):
            raise HTTPException(409, "Geen actuele koers voor dit exacte handelspaar.")
        fx = (await self.bots.get_portfolio_fx_rates()).get(quote_currency)
        checked = trade_quote_context(
            price=row.get("price"), price_at=row.get("source_observed_at"),
            row_quote=quote_currency, catalog_quote=quote_currency,
            usd_fx=None, quote_fx=fx, require_usd=False,
        )
        if checked.get("reason"):
            raise HTTPException(409, {
                "code": "PAPER_TRADE_QUOTE_UNAVAILABLE",
                "reason": checked["reason"],
                "message": "De koers of EUR-omrekening is niet vers genoeg voor een Paper-order.",
            })
        return {"market_id": market.id, "asset": asset, "quote_currency": quote_currency,
                **checked}

    async def preview(
        self, *, user_id: int, asset: str, quote_currency: str,
        amount_quote: object, idempotency_key: str,
    ) -> dict:
        amount = self._amount(amount_quote)
        if not 8 <= len(str(idempotency_key or "")) <= 128:
            raise HTTPException(422, "Een unieke orderreferentie is vereist.")
        quote = await self._quote(asset, quote_currency)
        gross_eur = (amount * Decimal(str(quote["market_fx_eur_per_unit"]))).quantize(CENT, rounding=ROUND_HALF_UP)
        fee_eur = (gross_eur * FEE_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
        quantity = ((gross_eur - fee_eur) / Decimal(str(quote["market_price_eur"]))).quantize(
            Decimal("0.000000000001"), rounding=ROUND_DOWN,
        )
        if gross_eur <= 0 or quantity <= 0:
            raise HTTPException(422, "Het bedrag is te klein voor een Paper-order.")
        cash = await self.reserve.cash(user_id)
        allowed = cash >= gross_eur
        expires_at = datetime.now(timezone.utc) + PREVIEW_TTL
        token = create_token({
            "user_id": user_id, "market_id": quote["market_id"],
            "asset": quote["asset"], "quote_currency": quote["quote_currency"],
            "amount_quote": str(amount), "gross_eur": str(gross_eur),
            "fee_eur": str(fee_eur), "quantity": str(quantity),
            "price_quote": str(quote["market_price"]),
            "price_eur": str(quote["market_price_eur"]),
            "price_observed_at": quote["market_price_at"].isoformat(),
            "fx_observed_at": quote["market_fx_as_of"].isoformat() if quote["market_fx_as_of"] else None,
            "idempotency_key": idempotency_key,
        }, PREVIEW_TTL, "paper_discretionary_preview") if allowed else None
        return {
            "ok": allowed, "blocked": not allowed,
            "reason": None if allowed else "paper_reserve_insufficient_cash",
            "message": None if allowed else "De vrije Paper-reserve is te laag. Boek eerst bestaande Paper-kas over.",
            "market_id": quote["market_id"], "pair": f"{quote['asset']}/{quote['quote_currency']}",
            "side": "buy", "amount_quote": str(amount), "gross_eur": str(gross_eur),
            "fee_eur": str(fee_eur), "quantity": str(quantity),
            "price_quote": str(quote["market_price"]),
            "price_eur": str(quote["market_price_eur"]),
            "price_observed_at": quote["market_price_at"].isoformat(),
            "fx_observed_at": quote["market_fx_as_of"].isoformat() if quote["market_fx_as_of"] else None,
            "reserve_cash_eur": str(cash), "preview_token": token,
            "expires_at": expires_at.isoformat() if allowed else None,
            "idempotency_key": idempotency_key,
            "requires_explicit_confirmation": True,
            "not_persisted": True, "exchange_order_created": False,
        }

    async def execute(
        self, *, user_id: int, asset: str, quote_currency: str,
        amount_quote: object, idempotency_key: str, preview_token: str,
    ) -> dict:
        amount = self._amount(amount_quote)
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id, 0)"), {"user_id": user_id})
        prior = await self.session.execute(text("""
            SELECT id, market_id, asset_symbol, quote_currency, notional_quote,
                   gross_eur, quantity, status
            FROM paper_discretionary_orders
            WHERE user_id=:user_id AND idempotency_key=:idempotency_key
        """), {"user_id": user_id, "idempotency_key": idempotency_key})
        existing = prior.first()
        if existing:
            if (existing[2] != asset.upper() or existing[3] != quote_currency.upper()
                    or Decimal(str(existing[4])) != amount):
                raise HTTPException(409, "Deze orderreferentie hoort bij een andere Paper-order.")
            return {"ok": True, "duplicate": True, "order_id": int(existing[0]),
                    "status": existing[7], "gross_eur": str(existing[5]),
                    "quantity": str(existing[6]), "exchange_order_created": False}
        try:
            claims = decode_token(preview_token or "")
            valid = (
                claims.get("type") == "paper_discretionary_preview"
                and claims.get("user_id") == user_id
                and claims.get("asset") == asset.upper()
                and claims.get("quote_currency") == quote_currency.upper()
                and claims.get("amount_quote") == str(amount)
                and claims.get("idempotency_key") == idempotency_key
            )
        except (TypeError, ValueError):
            valid = False
            claims = {}
        if not valid:
            raise HTTPException(409, "De Paper-preview is ongeldig of verlopen. Ververs de kaart.")
        try:
            previous_price = Decimal(str(claims["price_eur"]))
            gross_eur = Decimal(str(claims["gross_eur"]))
            fee_eur = Decimal(str(claims["fee_eur"]))
            quantity = Decimal(str(claims["quantity"]))
            if (not all(value.is_finite() and value > 0 for value in
                        (previous_price, gross_eur, quantity))
                    or not fee_eur.is_finite() or fee_eur < 0
                    or not claims.get("price_quote") or not claims.get("price_observed_at")):
                raise ValueError("invalid signed preview")
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise HTTPException(409, "De Paper-preview is ongeldig. Ververs de kaart.") from None
        quote = await self._quote(asset, quote_currency)
        if quote["market_id"] != claims.get("market_id"):
            raise HTTPException(409, "Het handelspaar is veranderd. Ververs de Paper-preview.")
        current_price = Decimal(str(quote["market_price_eur"]))
        if abs(current_price - previous_price) > previous_price * MAX_PRICE_MOVE:
            raise HTTPException(409, "De Paper-koers is veranderd. Ververs de preview.")
        current_gross = (amount * Decimal(str(quote["market_fx_eur_per_unit"]))).quantize(CENT, rounding=ROUND_HALF_UP)
        if abs(current_gross - gross_eur) > gross_eur * MAX_PRICE_MOVE:
            raise HTTPException(409, "De EUR-omrekening is veranderd. Ververs de preview.")
        # A market buy fills at the quote checked at confirmation, not at the
        # earlier preview price. Keep the quoted notional fixed and derive the
        # actual fee and quantity from this fresh quote.
        gross_eur = current_gross
        fee_eur = (gross_eur * FEE_RATE).quantize(CENT, rounding=ROUND_HALF_UP)
        quantity = ((gross_eur - fee_eur) / current_price).quantize(
            Decimal("0.000000000001"), rounding=ROUND_DOWN,
        )
        if gross_eur <= 0 or quantity <= 0:
            raise HTTPException(409, "De actuele Paper-koers is niet bruikbaar. Ververs de preview.")
        cash = await self.reserve.cash(user_id, lock=True)
        if cash < gross_eur:
            raise HTTPException(409, "De vrije Paper-reserve is te laag. Ververs de preview.")
        debited = await self.session.execute(text("""
            UPDATE paper_reserve_accounts
            SET cash_eur=cash_eur-CAST(:gross_eur AS NUMERIC), updated_at=NOW()
            WHERE user_id=:user_id AND cash_eur >= CAST(:gross_eur AS NUMERIC)
            RETURNING cash_eur
        """), {"user_id": user_id, "gross_eur": str(gross_eur)})
        if debited.first() is None:
            raise HTTPException(409, "De vrije Paper-reserve is veranderd. Ververs de preview.")
        row = await self.session.execute(text("""
            INSERT INTO paper_discretionary_orders (
                user_id, market_id, asset_symbol, quote_currency, side,
                notional_quote, gross_eur, fee_eur, quantity, price_quote,
                price_eur, price_observed_at, fx_observed_at, idempotency_key
            ) VALUES (
                :user_id, :market_id, :asset, :quote_currency, 'buy',
                CAST(:amount_quote AS NUMERIC), CAST(:gross_eur AS NUMERIC),
                CAST(:fee_eur AS NUMERIC), CAST(:quantity AS NUMERIC),
                CAST(:price_quote AS NUMERIC), CAST(:price_eur AS NUMERIC),
                :price_observed_at, :fx_observed_at, :idempotency_key
            ) RETURNING id
        """), {"user_id": user_id, "market_id": quote["market_id"], "asset": asset.upper(),
                 "quote_currency": quote_currency.upper(), "amount_quote": str(amount),
                 "gross_eur": str(gross_eur), "fee_eur": str(fee_eur),
                 "quantity": str(quantity), "price_quote": str(quote["market_price"]),
                 "price_eur": str(current_price),
                 "price_observed_at": quote["market_price_at"],
                 "fx_observed_at": quote["market_fx_as_of"],
                 "idempotency_key": idempotency_key})
        order_id = int(row.scalar_one())
        await self.session.execute(text("""
            INSERT INTO paper_discretionary_positions (
                user_id, market_id, asset_symbol, quote_currency,
                quantity, invested_eur, updated_at
            ) VALUES (:user_id, :market_id, :asset, :quote_currency,
                      CAST(:quantity AS NUMERIC), CAST(:gross_eur AS NUMERIC), NOW())
            ON CONFLICT (user_id, market_id) DO UPDATE SET
                quantity=paper_discretionary_positions.quantity+EXCLUDED.quantity,
                invested_eur=paper_discretionary_positions.invested_eur+EXCLUDED.invested_eur,
                updated_at=NOW()
        """), {"user_id": user_id, "market_id": quote["market_id"],
                 "asset": asset.upper(), "quote_currency": quote_currency.upper(),
                 "quantity": str(quantity), "gross_eur": str(gross_eur)})
        await self.session.commit()
        return {"ok": True, "duplicate": False, "order_id": order_id,
                "status": "filled", "pair": f"{asset.upper()}/{quote_currency.upper()}",
                "gross_eur": str(gross_eur), "quantity": str(quantity),
                "exchange_order_created": False}
