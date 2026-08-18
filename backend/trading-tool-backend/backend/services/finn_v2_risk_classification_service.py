from __future__ import annotations

from typing import Optional


class FinnV2RiskClassificationService:
    def classify_requested_operation(self, *, message: str, requested_operation: Optional[str] = None) -> Optional[str]:
        if requested_operation:
            return requested_operation
        normalized = str(message or "").casefold()
        if "watchlist" in normalized or "volglijst" in normalized:
            if any(token in normalized for token in ("verwijder", "haal", "remove")):
                return "watchlist_remove"
            if any(token in normalized for token in ("voeg", "add", "zet")):
                return "watchlist_add"
        if "bot" in normalized and ("live" in normalized or "zet" in normalized and "actief" in normalized):
            return "activate_live_bot"
        if "bot" in normalized and "paper" in normalized:
            return "activate_paper_bot"
        if "rebalance" in normalized or "herbalance" in normalized:
            return "portfolio_rebalance"
        if "order" in normalized or "koop" in normalized or "verkoop" in normalized or "buy " in normalized or "sell " in normalized:
            return "manual_order"
        if "indicator" in normalized or "dxy" in normalized:
            return "update_indicator_configuration"
        if "setup" in normalized:
            if any(token in normalized for token in ("maak", "create", "new", "nieuw")):
                return "create_setup"
            return "update_setup"
        if "strategie" in normalized or "strategy" in normalized:
            return "update_strategy"
        if "trade plan" in normalized or ("plan" in normalized and ("save" in normalized or "opslaan" in normalized or "bewaar" in normalized)):
            return "save_trade_plan"
        return None
