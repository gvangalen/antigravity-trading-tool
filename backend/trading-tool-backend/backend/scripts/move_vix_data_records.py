import asyncio
import logging
from sqlalchemy import text
from backend.infrastructure.database import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("move_vix_records")

async def migrate_data():
    async with async_session_factory() as s:
        logger.info("Moving VIX data records from macro_data to technical_indicators...")
        
        # Mapping:
        # macro_data.name -> technical_indicators.indicator
        # macro_data.value -> technical_indicators.value
        # macro_data.score -> technical_indicators.score
        # macro_data.trend -> technical_indicators.advies
        # macro_data.interpretation -> technical_indicators.uitleg
        # macro_data.timestamp -> technical_indicators.timestamp
        # macro_data.user_id -> technical_indicators.user_id
        
        mover_query = """
        INSERT INTO technical_indicators (indicator, value, score, advies, uitleg, timestamp, user_id)
        SELECT name, value, score, trend, interpretation, timestamp, user_id
        FROM macro_data
        WHERE name = 'vix';
        """
        
        delete_query = "DELETE FROM macro_data WHERE name = 'vix';"
        
        try:
            await s.execute(text(mover_query))
            await s.execute(text(delete_query))
            logger.info("✅ Data records moved.")
        except Exception as e:
            logger.error(f"❌ Failed to move records: {e}")
            await s.rollback()
            return

        await s.commit()
        print("🚀 VIX data records successfully migrated to technical_indicators!")

if __name__ == "__main__":
    asyncio.run(migrate_data())
