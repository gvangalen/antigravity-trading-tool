"""Read one verified trading pair without borrowing base-asset score evidence."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from backend.infrastructure.models import (
    MarketDataIndicator, TechnicalDataIndicator, TradingMarket,
)
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.services.setup_market_match_service import SetupMarketMatchService
from backend.services.workspace_data_service import (
    STALE_AFTER_SECONDS, WorkspaceDataService, _freshness, _market_row,
    _technical_row,
)


class ExactMarketWorkspaceService:
    def __init__(self, session):
        self.session = session

    async def get(self, user_id: int, symbol: str, quote_currency: str) -> dict | None:
        symbol = str(symbol or "").strip().upper()
        quote_currency = str(quote_currency or "").strip().upper()
        result = await self.session.execute(select(TradingMarket).where(
            TradingMarket.asset_symbol == symbol,
            TradingMarket.quote_currency == quote_currency,
            TradingMarket.venue == "BINANCE",
            TradingMarket.is_active.is_(True),
        ).limit(1))
        market = result.scalars().first()
        if market is None:
            return None

        latest = await MarketDataRepository(self.session).get_latest_exact_market_snapshot(int(market.id))
        # A bad provider row must never relabel another quote as this pair.
        if latest is not None and str(latest.quote_currency or "").upper() != quote_currency:
            latest = None
        assessment = await SetupMarketMatchService(self.session).for_asset(
            user_id, symbol, market_id=int(market.id),
        )
        market_result = await self.session.execute(select(MarketDataIndicator).where(
            MarketDataIndicator.user_id == user_id,
            MarketDataIndicator.market_id == market.id,
        ).order_by(MarketDataIndicator.source_observed_at.desc(), MarketDataIndicator.id.desc()))
        technical_result = await self.session.execute(select(TechnicalDataIndicator).where(
            TechnicalDataIndicator.user_id == user_id,
            TechnicalDataIndicator.market_id == market.id,
        ).order_by(TechnicalDataIndicator.source_observed_at.desc(), TechnicalDataIndicator.id.desc()))
        market_rows = self._latest_rows(market_result.scalars().all(), "name", _market_row)
        technical_rows = self._latest_rows(technical_result.scalars().all(), "indicator", _technical_row)
        workspace = WorkspaceDataService(self.session)
        macro_rows = await workspace._macro_rows(user_id, symbol, "day", asset_class="crypto")
        score_values = assessment["reported_scores"]
        categories = {}
        for category, rows, source in (
            ("market", market_rows, "market_data_indicators"),
            ("macro", macro_rows, "macro_data"),
            ("technical", technical_rows, "technical_indicators"),
        ):
            payload = workspace._category_payload(
                rows, "day", STALE_AFTER_SECONDS["day"], source, symbol=symbol,
            )
            score = score_values.get(f"{category}_score")
            payload["score"].update({
                "score": score,
                "status": "available" if score is not None else "insufficient_data",
                "basis": "verified_exact_market_indicator_evidence",
                "reason": None if score is not None else assessment["component_source_status"].get(f"{category}_score"),
            })
            categories[category] = payload

        return {
            "symbol": symbol,
            "market_id": int(market.id),
            "pair": f"{symbol}/{quote_currency}",
            "asset": {"symbol": symbol, "asset_class": "crypto",
                      "tradingview_symbol": market.tradingview_symbol},
            "quote": {
                "price": float(latest.price) if latest and latest.price is not None else None,
                "change_24h": float(latest.change_24h) if latest and latest.change_24h is not None else None,
                "volume": float(latest.volume) if latest and latest.volume is not None else None,
                "quote_currency": quote_currency,
                "price_provider": latest.price_provider if latest else None,
                **_freshness(latest.source_observed_at if latest else None,
                             STALE_AFTER_SECONDS["quote"], "exact_market_data"),
            },
            "categories": categories,
            "combined": {
                "score": assessment["benchmark_score"],
                "weights": assessment["benchmark_weights"],
                "basis": "verified_exact_market_score_2_0",
                "status": "available" if assessment["benchmark_score"] is not None else "insufficient_data",
                "source_status": assessment["source_status"],
            },
            "setup_matches": assessment["matches"],
            "score_source_observed_at": assessment["component_source_observed_at"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "ai_calls": 0,
        }

    @staticmethod
    def _latest_rows(readings, name_field: str, serializer) -> list[dict]:
        by_name = {}
        for reading in readings:
            name = str(getattr(reading, name_field, "") or "").lower()
            if name and name not in by_name:
                by_name[name] = serializer(reading)
        return list(by_name.values())
