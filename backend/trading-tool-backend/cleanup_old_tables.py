import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import logging
from backend.utils.db import get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def drop_legacy_tables():
    conn = get_db_connection()
    if not conn:
        logger.error("Kon niet verbinden met de database.")
        return
    
    tables = [
        "technical_indicator_scores",
        "market_indicator_scores",
        "macro_indicator_scores"
    ]
    
    try:
        with conn.cursor() as cur:
            for table in tables:
                logger.info(f"Dropping table {table}...")
                cur.execute(f"DROP TABLE IF EXISTS {table} CASCADE;")
                logger.info(f"✅ Table {table} dropped.")
        conn.commit()
        logger.info("🎉 Database opgeschoond!")
    except Exception as e:
        logger.error(f"Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    drop_legacy_tables()
