import logging
from celery import shared_task
from backend.infrastructure.database import SessionLocal
from backend.infrastructure.repositories.technical_data_repository import TechnicalDataRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.score_service import ScoreService
from backend.utils.market_data_utils import sync_market_data_7d
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
            from backend.utils.market_data_utils import sync_market_data_7d
            await sync_market_data_7d(symbol, overwrite=False)
            
            # 2. Fetch Technical Indicators for this symbol
            tech_repo = TechnicalDataRepository(db)
            score_repo = ScoreRepository(db)
            score_service = ScoreService(score_repo)
            
            user_configs = await tech_repo.get_user_configs(user_id)
            if not user_configs:
                # Fallback: copy BTC indicators if user has no custom config
                btc_data = await tech_repo.get_latest_data_fallback(user_id, symbol="BTC")
                for d in btc_data:
                    await tech_repo.ensure_user_config(user_id, d.indicator)
                await db.commit()
                user_configs = await tech_repo.get_user_configs(user_id)

            # 3. Trigger a fresh scan for this symbol via ScoreService logic
            # The get_daily_scores method has the "Runtime Engine" built-in
            await score_service.get_daily_scores(user_id, symbol=symbol)
            
            logger.info(f"✅ Asset {symbol} initialized successfully for user {user_id}")
            return {"status": "success", "symbol": symbol}
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize asset {symbol}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}
