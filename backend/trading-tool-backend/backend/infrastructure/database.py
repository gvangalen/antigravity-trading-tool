import os
import logging
from pathlib import Path
from typing import AsyncGenerator

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env", override=False)

# Omzetten van de conventionele connectiestring naar asyncpg structuur
db_host = os.getenv("DB_HOST", "127.0.0.1")
db_name = os.getenv("DB_NAME", "market_dashboard")
db_user = os.getenv("DB_USER") or os.getenv("PGUSER") or "postgres"
db_pass = os.getenv("DB_PASS") or os.getenv("DB_PASSWORD") or os.getenv("PGPASSWORD") or "postgres"
db_port = os.getenv("DB_PORT", "5432")

ASYNC_DATABASE_URL = f"postgresql+asyncpg://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

def _async_engine_options(build_service: str | None) -> dict:
    options = {"echo": False, "future": True}
    if build_service == "celery-worker-finn-interactive":
        # The single-concurrency worker refreshes this small pool at each task
        # boundary. Its short lifecycle sessions can then reuse one known-good
        # connection instead of opening a new TLS connection for every phase.
        options.update(
            pool_size=2,
            max_overflow=0,
            pool_pre_ping=True,
            pool_recycle=60,
            pool_timeout=3,
            connect_args={"timeout": 3},
        )
        return options
    options.update(
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
        pool_recycle=60,
        pool_timeout=3,
    )
    return options


# Initialiseer de Asynchrone Engine
engine = create_async_engine(
    ASYNC_DATABASE_URL,
    **_async_engine_options(os.getenv("TRADAMIND_BUILD_SERVICE")),
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
        except HTTPException as e:
            await session.rollback()
            if e.status_code >= 500:
                logging.error(f"❌ Async DB Error in session: {e}", exc_info=True)
            else:
                logging.info("↩️ API request stopped with expected HTTP %s: %s", e.status_code, e.detail)
            raise
        except Exception as e:
            logging.error(f"❌ Async DB Error in session: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()
