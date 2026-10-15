"""Read-only Live broker valuation and explicit cash attribution.

Allocations describe which bot an owner wants to associate with *free* EUR
cash. They do not reserve exchange funds or change order execution limits.
"""

from __future__ import annotations

import asyncio
import hashlib
import math
import time
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import text

from backend.infrastructure.repositories.exchange_repository import ExchangeRepository
from backend.services.exchange_service import ExchangeService
from backend.utils.rate_limit import InMemoryRateLimiter


_BALANCE_MAX_AGE_SECONDS = 300
_ACCOUNT_CACHE_SECONDS = 30
_MAX_ASSETS = 40
_account_cache: dict[tuple, tuple[float, dict | None]] = {}
_read_limiter = InMemoryRateLimiter(requests_limit=4, window_seconds=60)


def _amount(value) -> float:
    if value is None or isinstance(value, bool):
        raise ValueError("Missing broker amount")
    amount = float(value)
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("Invalid broker amount")
    return amount


async def read_live_account(session, user_id: int) -> dict | None:
    """Fetch one account exactly once. An incomplete balance is not a total."""
    keys = await ExchangeRepository(session).get_active_keys(user_id)
    if len(keys) != 1:
        return None
    key = keys[0]
    cache_key = (user_id, key.id, hashlib.sha256(key.api_key.encode()).hexdigest())
    cached = _account_cache.get(cache_key)
    if cached and time.monotonic() - cached[0] < _ACCOUNT_CACHE_SECONDS:
        cached_account = cached[1]
        if cached_account is None or (
            datetime.now(timezone.utc) - cached_account["as_of"]
        ).total_seconds() <= _BALANCE_MAX_AGE_SECONDS:
            return cached_account
    try:
        _read_limiter.check_rate_limit(f"live_portfolio:{user_id}", limit=4)
    except HTTPException:
        return None

    async def fetch() -> dict | None:
        deadline = time.monotonic() + 19
        client = await ExchangeService.get_client(
            key.exchange_name, key.api_key, key.api_secret, key.api_passphrase
        )
        try:
            balance = await asyncio.wait_for(client.fetch_balance(), timeout=10)
            fetched_at = datetime.now(timezone.utc)
            if not isinstance(balance, dict) or not isinstance(balance.get("total"), dict) or not isinstance(balance.get("free"), dict):
                return None
            balance_timestamp = balance.get("timestamp")
            if balance_timestamp is None and balance.get("datetime"):
                balance_timestamp = datetime.fromisoformat(str(balance["datetime"]).replace("Z", "+00:00")).timestamp() * 1000
            # Bitvavo's CCXT balance structure has timestamp=None. A direct
            # authenticated fetch is still an observed snapshot, but its time
            # basis must be disclosed rather than invented as provider time.
            source_at = (datetime.fromtimestamp(float(balance_timestamp) / 1000, tz=timezone.utc)
                         if balance_timestamp is not None else fetched_at)
            age = (fetched_at - source_at).total_seconds()
            if not math.isfinite(age) or age < -60 or age > _BALANCE_MAX_AGE_SECONDS:
                return None
            totals = {str(code).upper(): _amount(value) for code, value in balance["total"].items()}
            free = {str(code).upper(): _amount(value) for code, value in balance["free"].items()}
            # An omitted EUR field is not evidence of zero cash. A partially
            # returned broker balance must not become an available valuation.
            if "EUR" not in totals or "EUR" not in free:
                return None
            total_eur = totals["EUR"]
            free_eur = free["EUR"]
            if free_eur > total_eur + 0.005:
                return None
            positions = {symbol: qty for symbol, qty in totals.items() if symbol != "EUR" and qty > 0}
            if len(positions) > _MAX_ASSETS:
                return None
            pairs = [f"{symbol}/EUR" for symbol in positions]
            tickers = {}
            if pairs and getattr(client, "has", {}).get("fetchTickers"):
                try:
                    tickers = await asyncio.wait_for(
                        client.fetch_tickers(pairs),
                        timeout=min(5, max(0.1, deadline - time.monotonic() - 0.5)),
                    )
                except Exception:
                    tickers = {}
            prices: dict[str, float] = {}
            source_times = [source_at]
            for symbol in positions:
                ticker = tickers.get(f"{symbol}/EUR")
                if ticker is None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0.5:
                        break
                    try:
                        ticker = await asyncio.wait_for(
                            client.fetch_ticker(f"{symbol}/EUR"),
                            timeout=min(2, remaining - 0.5),
                        )
                    except Exception:
                        continue
                try:
                    if not isinstance(ticker, dict) or ticker.get("timestamp") is None:
                        continue
                    prices[symbol] = ExchangeService.verified_eur_ticker_price(ticker, symbol)
                    source_times.append(datetime.fromtimestamp(float(ticker["timestamp"]) / 1000, tz=timezone.utc))
                except (TypeError, ValueError):
                    continue
            return {
                "exchange_name": key.exchange_name,
                "cash_eur": free_eur,
                "total_eur": total_eur,
                "positions": positions,
                "prices_eur": prices,
                "position_value_eur": (
                    sum(qty * prices[symbol] for symbol, qty in positions.items())
                    if len(prices) == len(positions) else None
                ),
                "as_of": min(source_times),
                "balance_time_basis": "provider" if balance_timestamp is not None else "retrieval",
            }
        finally:
            await client.close()
    try:
        account = await asyncio.wait_for(fetch(), timeout=20)
    except Exception:
        account = None
    if len(_account_cache) > 512:
        _account_cache.clear()
    _account_cache[cache_key] = (time.monotonic(), account)
    return account


async def read_allocations(session, user_id: int, exchange_name: str) -> dict[int, float]:
    result = await session.execute(text("""
        SELECT a.bot_id, a.amount_eur
        FROM live_portfolio_cash_allocations a
        JOIN bot_configs b ON b.id=a.bot_id AND b.user_id=a.user_id AND b.is_live=TRUE
        WHERE a.user_id=:user_id AND a.exchange_name=:exchange_name
    """), {"user_id": user_id, "exchange_name": exchange_name})
    return {int(row.bot_id): float(row.amount_eur) for row in result}


async def replace_allocations(session, user_id: int, account: dict, requested: list[dict]) -> dict[int, float]:
    """Atomically replace the owner's display attribution for one account."""
    exchange_name = account["exchange_name"]
    values: dict[int, Decimal] = {}
    for item in requested:
        bot_id = int(item["bot_id"])
        amount = Decimal(str(item["amount_eur"]))
        if bot_id in values or not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise HTTPException(422, "Ongeldige of dubbele bottoewijzing")
        values[bot_id] = amount
    if sum(values.values(), Decimal(0)) > Decimal(str(account["cash_eur"])):
        raise HTTPException(409, "Toegewezen bedrag is hoger dan vrije EUR-cash bij de broker")

    await session.execute(text("SELECT pg_advisory_xact_lock(:user_id, 31)"), {"user_id": user_id})
    if values:
        result = await session.execute(text("""
            SELECT id FROM bot_configs WHERE user_id=:user_id AND is_live=TRUE AND id=ANY(:bot_ids)
        """), {"user_id": user_id, "bot_ids": list(values)})
        if {int(row.id) for row in result} != set(values):
            raise HTTPException(404, "Live-bot niet gevonden")
    await session.execute(text("""
        DELETE FROM live_portfolio_cash_allocations WHERE user_id=:user_id
    """), {"user_id": user_id})
    for bot_id, amount in values.items():
        await session.execute(text("""
            INSERT INTO live_portfolio_cash_allocations
              (user_id, bot_id, exchange_name, amount_eur)
            VALUES (:user_id, :bot_id, :exchange_name, :amount_eur)
        """), {"user_id": user_id, "bot_id": bot_id,
               "exchange_name": exchange_name, "amount_eur": amount})
    await session.commit()
    return {bot_id: float(value) for bot_id, value in values.items()}
