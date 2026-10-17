"""User-attested, fully closed round trips built from exact imported fills.

The attestation is a user claim about the selected position boundary. Provider
fills remain evidence of execution only; account-wide flatness and complete
cost basis are never inferred from incomplete exchange history.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from backend.services.finn_trade_review_rollout import require_trade_review_access

CONFIRMATION_VERSION = 1
CLOSURE_CONFIRMATION_TEXT = (
    "Ik bevestig dat deze geselecteerde uitvoeringen samen één trade vormen en volledig "
    "zijn afgesloten. De exchange-historie bewijst mogelijk niet de volledige accountpositie."
)
SAME_ACCOUNT_CONFIRMATION_TEXT = (
    "Ik bevestig dat deze uitvoeringen uit verschillende sleutelperiodes van dezelfde "
    "Bitvavo-account komen."
)


def _amount(value) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Invalid imported fill amount") from None
    if not result.is_finite():
        raise ValueError("Invalid imported fill amount")
    return result


def _canonical_digest(fill_ids: list[int], same_account_confirmed: bool) -> str:
    payload = {"version": 1, "fill_ids": sorted(fill_ids), "closure_confirmed": True,
               "same_account_confirmed": same_account_confirmed}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build_attested_position(fills: list[dict]) -> dict:
    """Validate one long spot round trip and derive quote cash legs only."""
    if not 2 <= len(fills) <= 500:
        raise ValueError("Selecteer twee tot vijfhonderd uitvoeringen")
    ordered = sorted(fills, key=lambda item: (item["traded_at"], int(item["id"])))
    if len({str(item["base_currency"]) for item in ordered}) != 1:
        raise ValueError("Uitvoeringen moeten hetzelfde basisasset hebben")
    if ordered[0]["side"] != "buy" or ordered[-1]["side"] != "sell":
        raise ValueError("Een gesloten trade begint met koop en eindigt met verkoop")
    # Provider timestamps may only have millisecond precision. Opposite sides
    # at the same instant have no provable execution order.
    sides_at: dict[datetime, set[str]] = defaultdict(set)
    for item in ordered:
        sides_at[item["traded_at"]].add(str(item["side"]))
    if any(len(sides) > 1 for sides in sides_at.values()):
        raise ValueError("Koop en verkoop met dezelfde tijd zijn niet eenduidig geordend")

    base = str(ordered[0]["base_currency"])
    running = Decimal(0)
    bought = Decimal(0)
    sold = Decimal(0)
    cash: dict[str, dict[str, Decimal]] = defaultdict(lambda: {
        "buy_cost": Decimal(0), "sell_proceeds": Decimal(0),
    })
    evidence = []
    for index, item in enumerate(ordered):
        side = str(item["side"])
        if side not in {"buy", "sell"}:
            raise ValueError("Ongeldige uitvoeringsrichting")
        qty, price, cost = _amount(item["qty"]), _amount(item["price_quote"]), _amount(item["cost_quote"])
        if qty <= 0 or price <= 0 or cost <= 0:
            raise ValueError("Ongeldige uitvoeringswaarde")
        fee_currency = item.get("fee_currency")
        fee_raw = item.get("fee_amount")
        if fee_currency is None or fee_raw is None:
            raise ValueError("Fee en feevaluta moeten voor alle geselecteerde uitvoeringen bekend zijn")
        fee = _amount(fee_raw)
        base_fee = fee if fee_currency == base else Decimal(0)
        running += (qty if side == "buy" else -qty) - base_fee
        if running < 0:
            raise ValueError("Geselecteerde uitvoeringen vragen meer basisasset dan gekocht")
        if running == 0 and index != len(ordered) - 1:
            raise ValueError("Selectie bevat meerdere afgeronde trades")
        if side == "buy":
            bought += qty
            cash[str(item["quote_currency"])]["buy_cost"] += cost
        else:
            sold += qty
            cash[str(item["quote_currency"])]["sell_proceeds"] += cost
        evidence.append({
            "exchange_fill_id": int(item["id"]), "source_id": int(item["source_id"]),
            "exchange_order_id": str(item["exchange_order_id"]),
            "side": side, "qty": str(qty), "price_quote": str(price),
            "cost_quote": str(cost), "quote_currency": str(item["quote_currency"]),
            "fee_amount": str(fee), "fee_currency": str(fee_currency),
            "at": item["traded_at"].isoformat(),
        })
    if running != 0 or bought <= 0 or sold <= 0:
        raise ValueError("De geselecteerde positie is niet volledig gesloten")

    cash_legs = [{"currency": currency, "buy_cost": str(legs["buy_cost"]),
                  "sell_proceeds": str(legs["sell_proceeds"])}
                 for currency, legs in sorted(cash.items())]
    only_eur = (len(cash) == 1 and "EUR" in cash
                and all(item["fee_currency"] == "EUR" for item in ordered))
    if only_eur:
        entry_value = cash["EUR"]["buy_cost"]
        exit_value = cash["EUR"]["sell_proceeds"]
        eur = {"entry_value_eur": entry_value, "exit_value_eur": exit_value,
               "entry_price_eur": entry_value / bought,
               "exit_price_eur": exit_value / sold,
               "pnl_eur_before_fees": exit_value - entry_value,
               "pnl_status": "before_fees_eur"}
    else:
        eur = {"entry_value_eur": None, "exit_value_eur": None,
               "entry_price_eur": None, "exit_price_eur": None,
               "pnl_eur_before_fees": None, "pnl_status": "not_comparable"}
    return {"base_currency": base, "entry_at": ordered[0]["traded_at"],
            "exit_at": ordered[-1]["traded_at"], "entry_qty": bought,
            "cash_legs_by_currency": cash_legs, "fills": evidence, **eur}


class FinnExchangeTradeReviewService:
    def __init__(self, session):
        self.session = session

    async def create(self, user_id: int, *, fill_ids: list[int], closure_confirmed: bool,
                     same_account_confirmed: bool, idempotency_key: UUID) -> dict:
        require_trade_review_access(user_id)
        if not closure_confirmed:
            raise HTTPException(422, "Bevestig eerst dat de volledige trade gesloten is")
        if (not 2 <= len(fill_ids) <= 500 or len(set(fill_ids)) != len(fill_ids)
                or any(type(value) is not int or value <= 0 for value in fill_ids)):
            raise HTTPException(422, "Selecteer twee tot vijfhonderd unieke uitvoeringen")
        digest = _canonical_digest(fill_ids, same_account_confirmed)
        try:
            await self.session.execute(text("SELECT pg_advisory_xact_lock(:user_id, 741074)"),
                                       {"user_id": user_id})
            replay = await self.session.execute(text("""
                SELECT a.review_id, a.request_digest, r.pnl_status
                FROM finn_exchange_review_attestations a
                JOIN finn_trade_reviews r ON r.id=a.review_id AND r.user_id=a.user_id
                WHERE a.user_id=:user_id AND a.idempotency_key=:idempotency_key
            """), {"user_id": user_id, "idempotency_key": str(idempotency_key)})
            existing = replay.fetchone()
            if existing is not None:
                if existing.request_digest != digest:
                    raise HTTPException(409, "Idempotentiesleutel hoort bij een andere selectie")
                await self.session.commit()
                return {"review_id": int(existing.review_id), "created": False,
                        "origin": "exchange_user_attested", "closure_basis": "user_confirmed",
                        "pnl_status": existing.pnl_status}

            result = await self.session.execute(text("""
                SELECT f.id, f.source_id, f.exchange_trade_id, f.exchange_order_id,
                       f.symbol, f.base_currency, f.quote_currency, f.side, f.qty,
                       f.price_quote, f.cost_quote, f.fee_amount, f.fee_currency,
                       f.traded_at, s.exchange_name, s.identity_kind
                FROM finn_exchange_import_fills f
                JOIN finn_exchange_import_sources s
                  ON s.id=f.source_id AND s.user_id=f.user_id
                WHERE f.user_id=:user_id AND f.id=ANY(CAST(:fill_ids AS BIGINT[]))
                ORDER BY f.traded_at, f.id
            """), {"user_id": user_id, "fill_ids": fill_ids})
            fills = [dict(row._mapping) for row in result.fetchall()]
            if len(fills) != len(fill_ids):
                raise HTTPException(404, "Geselecteerde uitvoeringen niet gevonden")
            exchanges = {str(item["exchange_name"]) for item in fills}
            if len(exchanges) != 1:
                raise HTTPException(422, "Uitvoeringen moeten van één exchange komen")
            exchange_name = exchanges.pop()
            source_ids = sorted({int(item["source_id"]) for item in fills})
            if len(source_ids) == 1 and same_account_confirmed:
                raise HTTPException(422, "Bevestiging van sleutelwisseling is hier niet van toepassing")
            if len(source_ids) > 1 and not (
                exchange_name == "bitvavo" and same_account_confirmed
                and all(item["identity_kind"] == "credential_epoch" for item in fills)
            ):
                raise HTTPException(422, "Bevestig dezelfde Bitvavo-account na sleutelwisseling")
            identity_basis = (
                "credential_epoch_user_confirmed" if len(source_ids) > 1 else
                "provider_uid" if fills[0]["identity_kind"] == "provider_uid" else
                "single_credential_epoch"
            )
            if len({str(item["base_currency"]) for item in fills}) != 1:
                raise HTTPException(422, "Uitvoeringen moeten hetzelfde basisasset hebben")
            if len({(item["symbol"], item["exchange_trade_id"]) for item in fills}) != len(fills):
                raise HTTPException(422, "Dezelfde beursuitvoering is meerdere keren geselecteerd")

            # A bot order may already be projected from the Tradamind ledger.
            # No account binding exists for historical bot orders, so reject
            # exact order-ID overlaps conservatively rather than double count.
            bot_overlap = await self.session.execute(text("""
                SELECT 1 FROM finn_exchange_import_fills f
                JOIN finn_exchange_import_sources s ON s.id=f.source_id AND s.user_id=f.user_id
                JOIN bot_orders o ON o.user_id=f.user_id
                  AND LOWER(o.exchange_name)=s.exchange_name
                  AND (
                    UPPER(REPLACE(o.exchange_symbol, '-', '/'))=f.symbol OR
                    UPPER(REPLACE(REPLACE(o.exchange_symbol, '-', ''), '/', ''))=
                      UPPER(REPLACE(f.symbol, '/', ''))
                  )
                  AND o.exchange_order_id=f.exchange_order_id
                WHERE f.user_id=:user_id AND f.id=ANY(CAST(:fill_ids AS BIGINT[]))
                LIMIT 1
            """), {"user_id": user_id, "fill_ids": fill_ids})
            if bot_overlap.fetchone() is not None:
                raise HTTPException(409, "Een uitvoering hoort mogelijk bij een bestaande Tradamind-order")
            prior_overlap = await self.session.execute(text("""
                SELECT 1 FROM finn_exchange_review_fill_reservations r
                JOIN finn_exchange_import_fills prior
                  ON prior.id=r.exchange_fill_id AND prior.user_id=r.user_id
                JOIN finn_exchange_import_sources s
                  ON s.id=prior.source_id AND s.user_id=prior.user_id
                WHERE r.user_id=:user_id AND s.exchange_name=:exchange_name
                  AND (prior.symbol, prior.exchange_trade_id) IN (
                    SELECT selected.symbol, selected.exchange_trade_id
                    FROM finn_exchange_import_fills selected
                    WHERE selected.user_id=:user_id
                      AND selected.id=ANY(CAST(:fill_ids AS BIGINT[])))
                LIMIT 1
            """), {"user_id": user_id, "exchange_name": exchange_name,
                   "fill_ids": fill_ids})
            if prior_overlap.fetchone() is not None:
                raise HTTPException(409, "Een beursuitvoering is al aan een trade gekoppeld")
            try:
                position = build_attested_position(fills)
            except ValueError as exc:
                raise HTTPException(422, str(exc)) from None
            inserted = await self.session.execute(text("""
                INSERT INTO finn_trade_reviews (
                    user_id, bot_id, symbol, execution_environment, execution_sources,
                    opening_ledger_id, closing_ledger_id, entry_at, exit_at, entry_qty,
                    entry_value_eur, exit_value_eur, entry_price_eur, exit_price_eur,
                    pnl_eur_before_fees, plan_snapshot, fills, origin, closure_basis,
                    base_currency, pnl_status, cash_legs_by_currency, exchange_name,
                    attested_at, attestation_source_ids, candles_status, candles_reason
                ) VALUES (
                    :user_id, NULL, :symbol, 'live', '["direct_exchange"]'::jsonb,
                    NULL, NULL, :entry_at, :exit_at, :entry_qty,
                    :entry_value_eur, :exit_value_eur, :entry_price_eur, :exit_price_eur,
                    :pnl_eur_before_fees, NULL, CAST(:fills AS JSONB),
                    'exchange_user_attested', 'user_confirmed', :base_currency,
                    :pnl_status, CAST(:cash_legs AS JSONB), :exchange_name,
                    NOW(), CAST(:source_ids AS JSONB), 'unavailable',
                    'Uitvoeringsgrafiek voor externe beursfills nog niet verifieerbaar'
                ) RETURNING id
            """), {"user_id": user_id, "symbol": position["base_currency"],
                   "exchange_name": exchange_name, "source_ids": json.dumps(source_ids),
                   "fills": json.dumps(position["fills"]),
                   "cash_legs": json.dumps(position["cash_legs_by_currency"]),
                   **{key: position[key] for key in (
                       "entry_at", "exit_at", "entry_qty", "entry_value_eur", "exit_value_eur",
                       "entry_price_eur", "exit_price_eur", "pnl_eur_before_fees",
                       "base_currency", "pnl_status")}})
            review_id = int(inserted.scalar_one())
            for fill_id in fill_ids:
                await self.session.execute(text("""
                    INSERT INTO finn_exchange_review_fill_reservations
                        (user_id, exchange_fill_id, review_id)
                    VALUES (:user_id, :fill_id, :review_id)
                """), {"user_id": user_id, "fill_id": fill_id, "review_id": review_id})
            await self.session.execute(text("""
                INSERT INTO finn_exchange_review_attestations
                    (user_id, idempotency_key, request_digest, review_id,
                     same_account_confirmed, closure_confirmed, confirmation_version,
                     confirmation_method, identity_basis, closure_confirmation_text,
                     same_account_confirmation_text)
                VALUES (:user_id, :idempotency_key, :digest, :review_id,
                        :same_account_confirmed, TRUE, :confirmation_version,
                        'authenticated_api_attestation', :identity_basis, :closure_confirmation_text,
                        :same_account_confirmation_text)
            """), {"user_id": user_id, "idempotency_key": str(idempotency_key),
                   "digest": digest, "review_id": review_id,
                   "same_account_confirmed": same_account_confirmed,
                   "confirmation_version": CONFIRMATION_VERSION,
                   "identity_basis": identity_basis,
                   "closure_confirmation_text": CLOSURE_CONFIRMATION_TEXT,
                   "same_account_confirmation_text": (
                       SAME_ACCOUNT_CONFIRMATION_TEXT if len(source_ids) > 1 else None)})
            await self.session.commit()
            return {"review_id": review_id, "created": True,
                    "origin": "exchange_user_attested", "closure_basis": "user_confirmed",
                    "pnl_status": position["pnl_status"]}
        except IntegrityError:
            await self.session.rollback()
            raise HTTPException(409, "Geselecteerde uitvoeringen zijn al aan een trade gekoppeld") from None
        except Exception:
            await self.session.rollback()
            raise
