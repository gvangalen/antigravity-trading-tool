import asyncio
import logging
from backend.infrastructure.database import async_session_factory
from backend.services.macro_data_service import MacroDataService
from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("populate_cockpit")

async def populate():
    user_id = 30
    async with async_session_factory() as session:
        macro_service = MacroDataService(session)

        # 11 Macro Indicators for the Cockpit
        macro_indicators = [
            ("fear_greed_index", 45.0),
            ("btc_dominance", 52.5),
            ("dxy", 104.2),
            ("sp500", 5210.0),
            ("vix", 14.8),
            ("oil_price", 82.5),
            ("gold_price", 2350.0),
            ("us10y", 4.35),
            ("us02y", 4.75),
            ("interest_rate", 5.25),
            ("inflation_rate", 3.1),
            ("google_trends", 65.0),
            ("etf_bitcoin_inflow", 150.0)
        ]
        
        for name, val in macro_indicators:
            try:
                await macro_service.add_macro_indicator(user_id, name, val)
                logger.info(f"✅ Populated macro: {name}={val}")
            except Exception as e:
                logger.warning(f"⚠️ Could not populate {name}: {e}")

        # Trigger Scoring
        logger.info(f"🧮 Recalculating scores for user {user_id}...")
        try:
            await asyncio.to_thread(build_daily_scores_for_user, user_id)
            logger.info(f"✅ Scoring synchronized.")
        except Exception as e:
            logger.error(f"❌ Scoring sync failed: {e}")

if __name__ == "__main__":
    asyncio.run(populate())
