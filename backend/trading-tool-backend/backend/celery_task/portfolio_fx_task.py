"""Refresh dated EUR conversion rates without involving a user or bot."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from celery import shared_task

from backend.infrastructure.repositories.portfolio_fx_repository import store_portfolio_fx_rates
from backend.schemas.market_provider_schema import AssetRecord
from backend.services.portfolio_fx_service import inverted_eur_quote
from backend.services.providers.binance_market_data_adapter import BinanceMarketDataAdapter
from backend.services.providers.twelve_data_macro_provider import TwelveDataMacroProvider

logger = logging.getLogger(__name__)


def _readings() -> list[tuple[str, str, str, float | None, datetime | None]]:
    readings = []
    try:
        reading = TwelveDataMacroProvider().fetch_intraday_quote_reading("EUR/USD")
        if reading:
            readings.append(("USD", "twelve_data", "EUR/USD", reading["value"], reading["observed_at"]))
    except Exception:
        logger.warning("Portfolio USD/EUR quote refresh failed", exc_info=True)
    try:
        asset = AssetRecord(
            symbol="EUR", display_name="Euro", asset_class="forex", provider="binance",
            provider_symbol="EURUSDT", quote_currency="USDT",
        )
        snapshot = asyncio.run(BinanceMarketDataAdapter().fetch_latest_snapshot(asset))
        readings.append(("USDT", "binance", "EURUSDT", snapshot.price, snapshot.observed_at))
    except Exception:
        logger.warning("Portfolio USDT/EUR quote refresh failed", exc_info=True)
    return readings


@shared_task(name="backend.celery_task.portfolio_fx_task.refresh_portfolio_fx_rates")
def refresh_portfolio_fx_rates() -> dict[str, int]:
    valid = []
    now = datetime.now(timezone.utc)
    for quote, provider, pair, source_price, observed_at in _readings():
        factor = inverted_eur_quote(source_price, observed_at, now=now)
        if factor is not None:
            valid.append((quote, factor, provider, pair, source_price, observed_at))
    if not valid:
        return {"stored": 0}
    store_portfolio_fx_rates(valid)
    return {"stored": len(valid)}
