from backend.infrastructure.repositories.sidebar_repository import SidebarRepository
from backend.schemas.sidebar_schema import ActiveTradeResponse, BotStatusResponse

class SidebarService:
    def __init__(self, repository: SidebarRepository):
        self.repository = repository
        
    async def get_active_trades(self) -> list[ActiveTradeResponse]:
        # TODO: Replace with real DB query via repository
        return [
            ActiveTradeResponse(id=1, symbol="BTC/USDT", status="Open"),
            ActiveTradeResponse(id=2, symbol="SOL/USDT", status="In Progress"),
        ]

    async def get_ai_bot_status(self) -> BotStatusResponse:
        # TODO: Replace with real DB query via repository
        return BotStatusResponse(
            state="Actief",
            strategy="Breakout & Volume Surge",
            updated="2025-06-23 10:30"
        )
