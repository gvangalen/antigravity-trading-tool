import logging
from celery import shared_task
from backend.infrastructure.database import SessionLocal
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.score_service import ScoreService
from backend.services.asset_catalog_service import AssetCatalogService

from backend.utils.technical_interpreter import fetch_technical_value
import asyncio

logger = logging.getLogger(__name__)

@shared_task(name="backend.celery_task.asset_initialization.initialize_asset_data")
def initialize_asset_data(user_id: int, symbol: str):
    """
    Background task to warm up data for a new asset.
    """
    loop = asyncio.get_event_loop()
    if loop.is_closed():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    return loop.run_until_complete(_async_initialize(user_id, symbol))

async def _async_initialize(user_id: int, symbol: str):
    logger.info(f"🚀 Initializing asset data for {symbol} (User: {user_id})")
    
    async with SessionLocal() as db:
        try:
            # 1. Sync Market History (7 days)
            # This is already async safe usually
            from backend.services.market_data_service import MarketDataService
            market_service = MarketDataService(db)
            await market_service.sync_symbol_7day_data(symbol, overwrite=False)
            
            # 2. Fetch Technical Indicators for this symbol
            tech_repo = TechnicalDataRepository(db)
            score_repo = ScoreRepository(db)
            score_service = ScoreService(score_repo)
            asset_scope = await AssetCatalogService(db).get_asset(symbol)
            
            user_configs = await tech_repo.get_user_configs(
                user_id,
                symbol=symbol,
                asset_class=asset_scope.get("asset_class"),
            )
            if not user_configs:
                # A configuration for BTC is not a safe default for another
                # asset. Product setup owns creating explicit user selections.
                logger.info("No canonical indicator configuration for user=%s symbol=%s", user_id, symbol)

            # 3. Trigger a fresh scan for this symbol via ScoreService logic
            # The get_daily_scores method has the "Runtime Engine" built-in
            await score_service.get_daily_scores(
                user_id,
                symbol=symbol,
                refresh_if_incomplete=True,
            )
            
            logger.info(f"✅ Asset {symbol} initialized successfully for user {user_id}")
            return {"status": "success", "symbol": symbol}
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize asset {symbol}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
