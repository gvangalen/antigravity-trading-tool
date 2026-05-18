import os
import logging
from typing import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv()

# Omzetten van de conventionele connectiestring naar asyncpg structuur
db_host = os.getenv("DB_HOST", "127.0.0.1")
db_name = os.getenv("DB_NAME", "market_dashboard")
db_user = os.getenv("DB_USER") or os.getenv("PGUSER") or "postgres"
db_pass = os.getenv("DB_PASS") or os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD") or "postgres"
db_port = os.getenv("DB_PORT", "5432")

ASYNC_DATABASE_URL = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

# Initialiseer de Asynchrone Engine
engine = create_async_engine(
    ASYNC_DATABASE_URL, 
    echo=False,  # Set op True in de toekomst om de rauwe SQL queries te debuggen
    future=True,
    pool_size=10,       # Maximaal aantal verbindingen in de pool gelijktijdig
    max_overflow=20     # Extra verbindingen toegestaan bovenop de pool_size 
)

# Maak een factory aan voor asynchrone sessies
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# Declarative base voor alle SQLAlchemy ORM modellen
Base = declarative_base()

# --- Synchronous Connection for Celery & Utils ---
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

SYNC_DATABASE_URL = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"
sync_engine = create_engine(SYNC_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

async def validate_database_connection() -> None:
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        message = (
            "Database configuratie ongeldig of database niet bereikbaar. "
            f"Controleer DB_HOST={db_host}, DB_PORT={db_port}, DB_NAME={db_name}, DB_USER={db_user}. "
            "Register/login en Finn actions worden niet gestart met een kapotte DB-config."
        )
        logging.error("❌ %s Originele fout: %s", message, exc, exc_info=True)
        raise RuntimeError(message) from exc

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency. Levert per API-request een unieke, 
    gestroomlijnde asynchrone database connectie op. Verbinding wordt
    automatisch opgeruimd na afronden van het verzoek.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logging.error(f"❌ Async DB Error in session: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()
