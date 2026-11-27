"""Bounded background refresh for owner-linked, watch-only BTC accounts."""

import asyncio
import os

from celery import shared_task
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from backend.infrastructure.database import ASYNC_DATABASE_URL
from backend.services.btc_watch_wallet_service import BtcWatchWalletService


async def _refresh_due() -> dict[str, int]:
    engine = create_async_engine(ASYNC_DATABASE_URL, poolclass=NullPool)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    refreshed = failed = 0
    try:
        async with factory() as session:
            rows = await session.execute(text("""
                SELECT id, user_id FROM btc_watch_wallets
                WHERE last_attempt_at IS NULL
                   OR last_attempt_at < NOW() - INTERVAL '45 minutes'
                ORDER BY last_attempt_at NULLS FIRST, id
                LIMIT 10
            """))
            due = [(int(row[0]), int(row[1])) for row in rows.fetchall()]
        # Compact deployment budgets four DB connections for this worker.
        # Leave one free while these sessions await the outbound provider.
        limiter = asyncio.Semaphore(3)

        async def refresh_one(wallet_id: int, user_id: int) -> bool:
            async with limiter:
                async with factory() as session:
                    try:
                        await BtcWatchWalletService(session).refresh(user_id, wallet_id)
                        return True
                    except Exception:
                        await session.rollback()
                        return False

        outcomes = await asyncio.gather(*(refresh_one(wallet_id, user_id) for wallet_id, user_id in due))
        refreshed = sum(outcomes)
        failed = len(outcomes) - refreshed
        async with factory() as session:
            remaining = await session.execute(text("""
                SELECT COUNT(*) FROM btc_watch_wallets
                WHERE last_attempt_at IS NULL
                   OR last_attempt_at < NOW() - INTERVAL '45 minutes'
            """))
            backlog = int(remaining.scalar_one())
        return {"refreshed": refreshed, "failed": failed, "backlog": backlog}
    finally:
        await engine.dispose()


@shared_task(name="backend.celery_task.btc_watch_wallet_task.refresh_btc_watch_wallets")
def refresh_btc_watch_wallets() -> dict[str, int]:
    if not os.getenv("ALCHEMY_BITCOIN_API_KEY", "").strip():
        return {"refreshed": 0, "failed": 0, "unconfigured": 1}
    return asyncio.run(_refresh_due())
