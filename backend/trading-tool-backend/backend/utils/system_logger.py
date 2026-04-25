import logging
import json
import asyncio
from typing import Optional, Any, Dict
from datetime import datetime
from sqlalchemy import insert
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import SystemLog

# Standaard Python logger configureren
logger = logging.getLogger("system_logger")
logger.setLevel(logging.INFO)

class SystemLogger:
    """
    Centrale logger die zowel naar de console print als naar de database schrijft.
    Werkt asynchroon om de API-performance niet te hinderen.
    """

    @staticmethod
    async def _save_to_db(
        level: str,
        message: str,
        source: str,
        endpoint: Optional[str] = None,
        user_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        try:
            async with async_session_factory() as session:
                stmt = insert(SystemLog).values(
                    level=level,
                    message=message,
                    source=source,
                    endpoint=endpoint,
                    user_id=user_id,
                    metadata_json=metadata,
                    created_at=datetime.utcnow()
                )
                await session.execute(stmt)
                await session.commit()
        except Exception as e:
            # Als de DB logging faalt, printen we het naar de console om te voorkomen dat fouten onzichtbaar blijven
            logger.error(f"⚠️ Failed to save log to database: {e}")

    @classmethod
    def log_info(cls, message: str, source: str, endpoint: Optional[str] = None, user_id: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None):
        logger.info(f"ℹ️ [{source}] {message}")
        asyncio.create_task(cls._save_to_db("info", message, source, endpoint, user_id, metadata))

    @classmethod
    def log_warning(cls, message: str, source: str, endpoint: Optional[str] = None, user_id: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None):
        logger.warning(f"⚠️ [{source}] {message}")
        asyncio.create_task(cls._save_to_db("warning", message, source, endpoint, user_id, metadata))

    @classmethod
    def log_error(cls, message: str, source: str, endpoint: Optional[str] = None, user_id: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None):
        logger.error(f"❌ [{source}] {message}")
        asyncio.create_task(cls._save_to_db("error", message, source, endpoint, user_id, metadata))

    @classmethod
    def log_critical(cls, message: str, source: str, endpoint: Optional[str] = None, user_id: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None):
        logger.critical(f"🚨 [{source}] {message}")
        asyncio.create_task(cls._save_to_db("critical", message, source, endpoint, user_id, metadata))

# Gemakkelijke export voor direct gebruik
sys_logger = SystemLogger
