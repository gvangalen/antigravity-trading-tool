"""Owner-scoped virtual cash reserve shared by discretionary Paper trades."""

from __future__ import annotations

import json
from decimal import Decimal

from sqlalchemy import text


class PaperReserveRepository:
    def __init__(self, session):
        self.session = session

    async def cash(self, user_id: int, *, lock: bool = False) -> Decimal:
        if lock:
            await self.session.execute(text("""
                INSERT INTO paper_reserve_accounts (user_id, cash_eur)
                VALUES (:user_id, 0) ON CONFLICT (user_id) DO NOTHING
            """), {"user_id": user_id})
        result = await self.session.execute(text(
            "SELECT cash_eur FROM paper_reserve_accounts WHERE user_id=:user_id"
            + (" FOR UPDATE" if lock else "")
        ), {"user_id": user_id})
        row = result.first()
        return Decimal(str(row[0])) if row else Decimal("0")

    async def transfer(
        self, *, user_id: int, bot_id: int, direction: str,
        amount_eur: Decimal, idempotency_key: str,
    ) -> dict:
        """Move existing Paper cash once. Caller owns commit and rollback."""
        if direction not in {"bot_to_reserve", "reserve_to_bot"}:
            raise ValueError("paper_reserve_direction_invalid")
        if (not amount_eur.is_finite() or amount_eur <= 0
                or amount_eur != amount_eur.quantize(Decimal("0.01"))):
            raise ValueError("paper_reserve_amount_invalid")
        if len(idempotency_key) < 8 or len(idempotency_key) > 128:
            raise ValueError("paper_reserve_key_invalid")
        params = {"user_id": user_id, "bot_id": bot_id, "direction": direction,
                  "amount_eur": str(amount_eur), "idempotency_key": idempotency_key}
        # The account-level lock is also used by Paper order execution. All
        # reserve mutations serialize before touching bot and account rows.
        await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id, 0)"), params)
        existing = await self.session.execute(text("""
            SELECT id, bot_id, direction, amount_eur FROM paper_reserve_transfers
            WHERE user_id=:user_id AND idempotency_key=:idempotency_key
        """), params)
        prior = existing.first()
        if prior:
            if (int(prior[1]) != bot_id or prior[2] != direction
                    or Decimal(str(prior[3])) != amount_eur):
                raise ValueError("paper_reserve_key_reused")
            return {"transfer_id": int(prior[0]), "replayed": True}

        bot_row = await self.session.execute(text("""
            SELECT b.id, COALESCE(NULLIF(UPPER(b.symbol), ''),
                         NULLIF(UPPER(s.symbol), ''),
                         NULLIF(UPPER(s.data->>'symbol'), ''),
                         NULLIF(UPPER(st.symbol), '')) AS symbol
            FROM bot_configs b
            LEFT JOIN strategies s ON s.id=b.strategy_id AND s.user_id=b.user_id
            LEFT JOIN setups st ON st.id=s.setup_id AND st.user_id=s.user_id
            WHERE b.user_id=:user_id AND b.id=:bot_id AND b.is_live=FALSE
            FOR UPDATE OF b
        """), params)
        bot = bot_row.first()
        if not bot or not bot[1]:
            raise ValueError("paper_reserve_bot_invalid")
        symbol = str(bot[1]).upper()
        unverified = await self.session.execute(text("""
            SELECT 1 WHERE EXISTS (
                SELECT 1 FROM portfolio_unverified_paper_bots
                WHERE user_id=:user_id AND bot_id=:bot_id
            ) OR EXISTS (
                SELECT 1 FROM bot_ledger
                WHERE user_id=:user_id AND bot_id=:bot_id
                  AND entry_type='execute' AND valuation_version < 2
            )
        """), params)
        if unverified.first():
            raise ValueError("paper_reserve_bot_unverified")

        await self.cash(user_id, lock=True)
        if direction == "bot_to_reserve":
            debited = await self.session.execute(text("""
                UPDATE bot_portfolios
                SET cash_eur=cash_eur-CAST(:amount_eur AS NUMERIC), updated_at=NOW()
                WHERE user_id=:user_id AND bot_id=:bot_id AND symbol=:symbol
                  AND cash_eur >= CAST(:amount_eur AS NUMERIC)
                RETURNING cash_eur
            """), {**params, "symbol": symbol})
            if debited.first() is None:
                raise ValueError("paper_reserve_insufficient_bot_cash")
            await self.session.execute(text("""
                UPDATE paper_reserve_accounts
                SET cash_eur=cash_eur+CAST(:amount_eur AS NUMERIC), updated_at=NOW()
                WHERE user_id=:user_id
            """), params)
            bot_delta = -amount_eur
        else:
            debited = await self.session.execute(text("""
                UPDATE paper_reserve_accounts
                SET cash_eur=cash_eur-CAST(:amount_eur AS NUMERIC), updated_at=NOW()
                WHERE user_id=:user_id AND cash_eur >= CAST(:amount_eur AS NUMERIC)
                RETURNING cash_eur
            """), params)
            if debited.first() is None:
                raise ValueError("paper_reserve_insufficient_cash")
            await self.session.execute(text("""
                INSERT INTO bot_portfolios
                    (user_id, bot_id, symbol, cash_eur, position_qty,
                     invested_eur, avg_entry, realized_pnl_eur, updated_at)
                VALUES (:user_id, :bot_id, :symbol, CAST(:amount_eur AS NUMERIC),
                        0, 0, 0, 0, NOW())
                ON CONFLICT (bot_id, symbol) DO UPDATE SET
                    cash_eur=bot_portfolios.cash_eur+EXCLUDED.cash_eur,
                    updated_at=NOW()
            """), {**params, "symbol": symbol})
            bot_delta = amount_eur

        row = await self.session.execute(text("""
            INSERT INTO paper_reserve_transfers
                (user_id, bot_id, direction, amount_eur, idempotency_key)
            VALUES (:user_id, :bot_id, :direction,
                    CAST(:amount_eur AS NUMERIC), :idempotency_key)
            RETURNING id
        """), params)
        transfer_id = int(row.scalar_one())
        await self.session.execute(text("""
            INSERT INTO bot_ledger
                (user_id, bot_id, entry_type, symbol, cash_delta_eur,
                 qty_delta, note, meta, ts)
            VALUES (:user_id, :bot_id, 'paper_cash_transfer', :symbol,
                    CAST(:cash_delta_eur AS NUMERIC), 0,
                    'Overboeking naar of van vrije Paper-reserve', CAST(:meta AS JSONB), NOW())
        """), {**params, "symbol": symbol, "cash_delta_eur": str(bot_delta),
                "meta": json.dumps({"reserve_transfer_id": transfer_id,
                                    "direction": direction, "currency": "EUR"})})
        return {"transfer_id": transfer_id, "replayed": False}
