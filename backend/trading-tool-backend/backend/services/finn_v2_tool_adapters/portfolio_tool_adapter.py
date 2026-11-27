from __future__ import annotations

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.services.portfolio_overview_service import project_portfolio
from backend.services.live_portfolio_allocation_service import read_allocations, read_live_account
from backend.services.finn_v2_tool_adapters.display_source_moment import amsterdam_source_moment
from backend.infrastructure.repositories.paper_reserve_repository import PaperReserveRepository
from backend.services.portfolio_fx_service import price_in_eur
from sqlalchemy import text


class PortfolioToolAdapter:
    def __init__(self, session):
        self.session = session
        self.repository = BotRepository(session)

    async def execute(self, *, user_id: int, asset: str | None = None, environment: str | None = None, **_kwargs):
        payload = await self.repository.get_portfolio_intelligence_context(user_id)
        if environment != "live" and getattr(self, "session", None) is not None:
            reserve = PaperReserveRepository(self.session)
            payload["paper_reserve_cash_eur"] = float(await reserve.cash(user_id))
            positions = await self.session.execute(text("""
                SELECT market_id, asset_symbol, quote_currency, quantity, invested_eur
                FROM paper_discretionary_positions
                WHERE user_id=:user_id AND quantity > 0
                ORDER BY market_id
            """), {"user_id": user_id})
            source_rows = [dict(row._mapping) for row in positions.fetchall()]
            prices = await self.repository.get_valuatable_exact_market_prices(
                [row["market_id"] for row in source_rows]
            )
            fx_rates = await self.repository.get_portfolio_fx_rates() if source_rows else {}
            payload["manual_positions"] = []
            for row in source_rows:
                market = prices.get(int(row["market_id"])) or {}
                quote = str(row["quote_currency"]).upper()
                matching = (
                    str(market.get("symbol") or "").upper() == str(row["asset_symbol"]).upper()
                    and str(market.get("quote_currency") or "").upper() == quote
                )
                euro_price, price_at, _, _ = price_in_eur(
                    price=market.get("price") if matching else None,
                    price_at=market.get("source_observed_at") if matching else None,
                    quote_currency=quote, fx=fx_rates.get(quote),
                )
                payload["manual_positions"].append({
                    "market_id": int(row["market_id"]),
                    "symbol": str(row["asset_symbol"]).upper(),
                    "quote_currency": quote,
                    "pair": f"{str(row['asset_symbol']).upper()}/{quote}",
                    "quantity": float(row["quantity"]),
                    "invested_eur": float(row["invested_eur"]),
                    "position_value_eur": float(row["quantity"]) * euro_price if euro_price else None,
                    "valuation_available": euro_price is not None,
                    "price_as_of": price_at,
                })
        requested_asset = str(asset or "").strip().upper() or None
        if environment == "live":
            account = await read_live_account(self.session, user_id)
            payload["live_account"] = account
            payload["live_allocations"] = (
                await read_allocations(self.session, user_id, account["exchange_name"])
                if account else {}
            )
        data = project_portfolio(payload, asset=asset, environment=environment)
        summary = {
            "title": "portfolio",
            "total_equity": data.global_.total_equity,
            "bot_count": len(data.bots),
            "requested_asset": requested_asset,
            "read_at_amsterdam": amsterdam_source_moment(data.read_at),
            "valuation_as_of_amsterdam": amsterdam_source_moment(data.valuation_as_of),
        }
        return {
            "data": data,
            "summary": summary,
            "as_of": data.valuation_as_of,
            "source": "bot_portfolios",
            "schema_name": "PortfolioData",
            "entity_type": "portfolio",
            "asset": requested_asset,
        }
