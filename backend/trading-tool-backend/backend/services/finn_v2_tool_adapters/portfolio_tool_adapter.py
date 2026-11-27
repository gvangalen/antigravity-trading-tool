from __future__ import annotations

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.services.portfolio_overview_service import project_portfolio
from backend.services.live_portfolio_allocation_service import read_allocations, read_live_account
from backend.services.finn_v2_tool_adapters.display_source_moment import amsterdam_source_moment
from backend.infrastructure.repositories.paper_reserve_repository import PaperReserveRepository
from backend.services.portfolio_fx_service import price_in_eur
from backend.services.btc_watch_wallet_service import BtcWatchWalletService
from backend.schemas.finn_v2_evidence_schema import PortfolioWatchWalletData
from datetime import datetime, timedelta, timezone
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
        # Watch-only Bitcoin is a separate real holding. It is never merged
        # into virtual Paper equity, broker cash, or any bot budget.
        if getattr(self, "session", None) is not None and requested_asset in (None, "BTC"):
            watch_rows = await BtcWatchWalletService(self.session).list(user_id)
            prices = await self.repository.get_valuatable_market_prices(["BTC"]) if watch_rows else {}
            market = prices.get("BTC") or {}
            quote = str(market.get("quote_currency") or "").upper()
            fx = (await self.repository.get_portfolio_fx_rates()).get(quote) if quote in {"USD", "USDT"} else None
            eur_price, price_at, _, _ = price_in_eur(
                price=market.get("price"), price_at=market.get("observed_at"),
                quote_currency=quote, fx=fx,
            )
            now = datetime.now(timezone.utc)
            for row in watch_rows:
                observed = row.get("fetched_at")
                if observed and observed.tzinfo is None:
                    observed = observed.replace(tzinfo=timezone.utc)
                stale = observed is None or now - observed > timedelta(hours=24)
                row["stale"] = stale
                row["valuation_available"] = bool(
                    row["sync_status"] == "available" and not stale
                    and row["quantity_btc"] is not None and eur_price is not None
                )
                row["position_value_eur"] = (
                    float(row["quantity_btc"]) * eur_price if row["valuation_available"] else None
                )
                row["price_as_of"] = price_at if row["valuation_available"] else None
            data.watch_wallets = [PortfolioWatchWalletData.parse_obj(row) for row in watch_rows]
            if watch_rows:
                data.covered_scopes.append("watch_only_btc_self_custody")
        summary = {
            "title": "portfolio",
            "total_equity": data.global_.total_equity,
            "bot_count": len(data.bots),
            "requested_asset": requested_asset,
            "read_at_amsterdam": amsterdam_source_moment(data.read_at),
            "valuation_as_of_amsterdam": amsterdam_source_moment(data.valuation_as_of),
            "watch_wallet_count": len(data.watch_wallets),
        }
        wallet_observations = [wallet.fetched_at for wallet in data.watch_wallets
                               if wallet.sync_status == "available" and wallet.fetched_at]
        evidence_as_of = data.valuation_as_of or (min(wallet_observations) if wallet_observations else None)
        wallet_only = bool(data.watch_wallets) and not data.bots and not data.manual_positions
        wallet_freshness = (
            "fresh" if all(wallet.sync_status == "available" and not wallet.stale
                           for wallet in data.watch_wallets) else "stale"
        ) if wallet_only and data.valuation_as_of is None else None
        return {
            "data": data,
            "summary": summary,
            "as_of": evidence_as_of,
            **({"freshness_status": wallet_freshness} if wallet_freshness is not None else {}),
            "source": "portfolio_plus_watch_only_btc" if data.watch_wallets else "bot_portfolios",
            "schema_name": "PortfolioData",
            "entity_type": "portfolio",
            "asset": requested_asset,
        }
