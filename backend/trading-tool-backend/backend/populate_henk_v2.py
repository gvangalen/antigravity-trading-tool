import asyncio
import logging
from backend.infrastructure.database import async_session_factory
from backend.services.macro_data_service import MacroDataService
from backend.services.technical_data_service import TechnicalDataService
from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("populate_henk")

async def populate():
    user_id = 30
    async with async_session_factory() as session:
        macro_service = MacroDataService(session)
        tech_service = TechnicalDataService(session)

        # 1. Macro Indicators
        macro_indicators = [
            ("fear_greed_index", 42.0),
            ("inflation_rate", 3.2),
            ("interest_rate", 5.25),
            ("dxy", 104.5)
        ]
        for name, val in macro_indicators:
            try:
                await macro_service.add_macro_indicator(user_id, name, val)
                logger.info(f"✅ Added macro: {name}={val}")
            except Exception as e:
                logger.warning(f"⚠️ Could not add macro {name}: {e}")

        # 2. Technical Indicators
        tech_indicators = ["rsi", "ma_200"]
        for name in tech_indicators:
            try:
                await tech_service.add_technical_indicator(name, user_id)
                logger.info(f"✅ Added tech: {name}")
            except Exception as e:
                logger.warning(f"⚠️ Could not add tech {name}: {e}")

        # 3. Scoring (Synchronous call to internal specialized function)
        logger.info(f"🧮 Triggering scores for user {user_id}...")
        try:
            # We run this in a thread if it's blocking, but here it's a sync function using a separate connection
            await asyncio.to_thread(build_daily_scores_for_user, user_id)
            logger.info(f"✅ Scoring completed for user {user_id}")
        except Exception as e:
            logger.error(f"❌ Scoring failed: {e}")

if __name__ == "__main__":
    asyncio.run(populate())
