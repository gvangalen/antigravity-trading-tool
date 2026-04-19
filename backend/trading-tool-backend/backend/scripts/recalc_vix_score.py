import asyncio
import logging
from backend.celery_task.store_daily_scores_task import build_daily_scores_for_user

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("recalc")

async def main():
    user_id = 30
    logger.info(f"🧮 Recalculating scores for user {user_id} after VIX move...")
    try:
        await asyncio.to_thread(build_daily_scores_for_user, user_id)
        logger.info("✅ Scoring complete.")
    except Exception as e:
        logger.error(f"❌ Scoring failed: {e}")

if __name__ == "__main__":
    asyncio.run(main())
