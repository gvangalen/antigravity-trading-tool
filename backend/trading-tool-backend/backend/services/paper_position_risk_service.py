"""Read-only, owner-scoped Paper position risk from verified portfolio values."""

from datetime import datetime, timedelta, timezone
from math import isfinite

from sqlalchemy import text

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.services.portfolio_fx_service import (
    TRADE_MAX_FX_AGE, TRADE_MAX_PRICE_AGE, TRADE_MAX_SOURCE_SKEW,
)
from backend.services.portfolio_overview_service import project_portfolio


def _recent(moment: datetime | None, *, now: datetime, max_age: timedelta) -> bool:
    if moment is None:
        return False
    observed = moment.replace(tzinfo=timezone.utc) if moment.tzinfo is None else moment.astimezone(timezone.utc)
    return timedelta(0) <= now - observed <= max_age


def _aligned(price_at: datetime | None, fx_at: datetime | None) -> bool:
    if price_at is None or fx_at is None:
        return False
    price = price_at.replace(tzinfo=timezone.utc) if price_at.tzinfo is None else price_at.astimezone(timezone.utc)
    fx = fx_at.replace(tzinfo=timezone.utc) if fx_at.tzinfo is None else fx_at.astimezone(timezone.utc)
    return abs(price - fx) <= TRADE_MAX_SOURCE_SKEW


class PaperPositionRiskService:
    def __init__(self, session):
        self.session = session

    async def evaluate(self, user_id: int) -> dict[int, dict]:
        started_at = datetime.now(timezone.utc)
        rows = await self.session.execute(text("""
            SELECT b.id, b.max_asset_exposure_pct, b.market_id,
                   m.quote_currency
            FROM bot_configs b LEFT JOIN trading_markets m ON m.id=b.market_id
            WHERE b.user_id=:user_id AND b.is_live=FALSE
        """), {"user_id": user_id})
        limits = {int(row["id"]): row for row in rows.mappings().all()}
        payload = await BotRepository(self.session).get_portfolio_intelligence_context(user_id)
        portfolio = project_portfolio(payload, environment="paper")
        now = datetime.now(timezone.utc)
        assessments = {}
        for bot in portfolio.bots:
            if bot.bot_id not in limits:
                continue
            row = limits[bot.bot_id]
            try:
                limit = float(row["max_asset_exposure_pct"])
            except (TypeError, ValueError):
                limit = None
            limit = limit if limit is not None and isfinite(limit) and 0 <= limit < 100 else None
            pair = (f"{bot.symbol}/{row['quote_currency']}"
                    if row["market_id"] is not None and row["quote_currency"] else bot.symbol)
            valid_valuation = (
                bot.valuation_available and bot.position_qty is not None
                and bot.position_qty > 0 and bot.equity is not None and bot.equity > 0
                and bot.position_value_eur is not None and bot.position_value_eur >= 0
                and bot.cash_eur is not None and bot.cash_eur >= 0
                and all(isfinite(value) for value in (
                    bot.position_qty, bot.equity, bot.position_value_eur, bot.cash_eur))
                and _recent(bot.source_price_as_of, now=now, max_age=TRADE_MAX_PRICE_AGE)
                and (bot.price_quote_currency == "EUR" or (
                    _recent(bot.fx_as_of, now=now, max_age=TRADE_MAX_FX_AGE)
                    and _aligned(bot.source_price_as_of, bot.fx_as_of)))
            )
            exposure = (round(100 * bot.position_value_eur / bot.equity, 2)
                        if valid_valuation else None)
            if exposure is not None and not isfinite(exposure):
                exposure = None
            status = (
                "no_limit" if limit is None else
                "flat" if bot.position_qty is not None and bot.position_qty <= 0 else
                "unavailable" if exposure is None else
                "above_saved_limit" if exposure > limit else "within_limit"
            )
            assessments[bot.bot_id] = {
                "status": status, "bot_id": bot.bot_id, "bot_name": bot.name,
                "symbol": bot.symbol, "market_id": row["market_id"],
                "trading_pair": pair, "exposure_pct": exposure,
                "limit_pct": limit, "position_value_eur": bot.position_value_eur,
                "bot_equity_eur": bot.equity,
                "quote_source_observed_at": bot.source_price_as_of,
                "fx_source_observed_at": bot.fx_as_of,
                "valuation_as_of": bot.price_as_of,
                "evaluated_at": started_at,
            }
        return assessments
