import psycopg2
import os
import logging
from typing import Any
from dotenv import load_dotenv  # ✅ Zorg dat .env automatisch geladen wordt
from psycopg2.extras import Json

# ✅ .env-bestand laden (alleen nodig als dit bestand los wordt aangeroepen)
load_dotenv()

# ✅ Logging instellen
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

LEGACY_SYNC_DB_BOUNDARY = True


def jsonb_param(value: Any) -> Json:
    """Return a psycopg2 JSON adapter without leaking psycopg2 into callers."""
    return Json(value)

def get_db_connection():
    """Maakt een verbinding met de PostgreSQL database op basis van omgevingsvariabelen."""
    db_config = {
        "host": os.getenv("DB_HOST", "127.0.0.1"),  # ✅ fallback = localhost
        "database": os.getenv("DB_NAME", "market_dashboard"),
        "user": os.getenv("DB_USER") or os.getenv("PGUSER") or "postgres",
        "password": os.getenv("DB_PASS") or os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD") or "postgres",
        "port": int(os.getenv("DB_PORT", 5432)),
    }

    try:
        conn = psycopg2.connect(**db_config)
        logging.info(f"✅ Verbonden met database {db_config['database']} op {db_config['host']}:{db_config['port']}")
        return conn
    except psycopg2.Error as e:
        logging.error(f"❌ Databasefout: {e}")
        return None
