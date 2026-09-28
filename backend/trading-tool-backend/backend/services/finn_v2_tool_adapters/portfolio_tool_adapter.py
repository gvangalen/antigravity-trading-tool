from __future__ import annotations

from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.schemas.finn_v2_evidence_schema import PortfolioBotData, PortfolioData, PortfolioGlobalData


class PortfolioToolAdapter:
    def __init__(self, session):
        self.repository = BotRepository(session)

    async def execute(self, *, user_id: int, asset: str | None = None, **_kwargs):
        payload = await self.repository.get_portfolio_intelligence_context(user_id)
        requested_asset = str(asset or "").strip().upper() or None
        source_bots = list(payload.get("bots", []))
        if requested_asset is not None:
            source_bots = [
                row for row in source_bots
                if str(row.get("symbol") or "").strip().upper() == requested_asset
            ]
        compact_bots = [
            PortfolioBotData(
                bot_id=row.get("bot_id"),
                name=row.get("name"),
                symbol=row.get("symbol"),
                equity=(row.get("equity") if row.get("portfolio_initialized", True)
                        and row.get("price_available", True) else None),
                is_active=row.get("is_active"),
                is_live=row.get("is_live"),
            )
            for row in source_bots
        ]
        global_payload = self._global_for_bots(source_bots)
        summary = {
            "title": "portfolio",
            "total_equity": global_payload.get("total_equity"),
            "bot_count": len(compact_bots),
            "requested_asset": requested_asset,
        }
        return {
            "data": PortfolioData.parse_obj(
                {
                    "global": PortfolioGlobalData(**global_payload).dict(),
                    "bots": [row.dict() for row in compact_bots],
                    "covered_scopes": ["paper_bot_portfolio_valuation", "budget", "exposure"],
                    "excluded_scopes": ["trade_transaction_history", "tax_records", "tax_calculations"],
                }
            ),
            "summary": summary,
            "as_of": None,
            "source": "bot_portfolios",
            "schema_name": "PortfolioData",
            "entity_type": "portfolio",
            "asset": requested_asset,
        }

    @staticmethod
    def _global_for_bots(rows: list[dict]) -> dict:
        """Project the existing owner-scoped ledger for an optional asset.

        The repository remains the sole valuation source. A filter only
        reduces its already loaded bot rows and derives the same aggregate
        fields, so an asset-scoped read cannot disclose another position.
        """
        total_budget_limit = sum(float(row.get("budget_total") or 0) for row in rows)
        portfolio_complete = bool(rows) and all(
            row.get("portfolio_initialized", True) for row in rows
        )
        valuation_complete = portfolio_complete and all(
            row.get("price_available", True) for row in rows
        )
        cash_balance = sum(float(row.get("cash") or 0) for row in rows) if portfolio_complete else None
        invested_value = sum(float(row.get("invested") or 0) for row in rows) if portfolio_complete else None
        realized_pnl = sum(float(row.get("realized_pnl") or 0) for row in rows) if portfolio_complete else None
        current_position_value = (
            sum(float(row.get("position_value") or 0) for row in rows)
            if valuation_complete else None
        )
        total_equity = (
            cash_balance + current_position_value
            if cash_balance is not None and current_position_value is not None else None
        )
        allocation_values: dict[str, float] = {}
        for row in rows if valuation_complete else []:
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol:
                allocation_values[symbol] = allocation_values.get(symbol, 0.0) + float(row.get("position_value") or 0)
        allocations = {} if total_equity is None or total_equity <= 0 else {
            "Cash": round((cash_balance / total_equity) * 100, 2),
            **{
                symbol: round((value / total_equity) * 100, 2)
                for symbol, value in allocation_values.items()
            },
        }
        return {
            "currency": "EUR",
            "total_equity": total_equity,
            "cash_balance": cash_balance,
            "invested_value": invested_value,
            "current_position_value": current_position_value,
            "realized_pnl": realized_pnl,
            "unrealized_pnl": (
                current_position_value - invested_value
                if current_position_value is not None and invested_value is not None else None
            ),
            "total_budget_limit": total_budget_limit,
            "allocations_pct": allocations,
        }
