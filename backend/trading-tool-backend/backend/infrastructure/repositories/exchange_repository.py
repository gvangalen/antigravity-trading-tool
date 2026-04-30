from typing import List, Optional
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from backend.infrastructure.models import ExchangeKey

class ExchangeRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def save_exchange_key(self, user_id: int, exchange_name: str, api_key: str, api_secret: str, api_passphrase: str = None):
        # Check if already exists for this exchange
        stmt = select(ExchangeKey).where(ExchangeKey.user_id == user_id, ExchangeKey.exchange_name == exchange_name)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            existing.api_key = api_key
            existing.api_secret = api_secret
            existing.api_passphrase = api_passphrase
            existing.is_active = True
            return existing.id
        else:
            new_key = ExchangeKey(
                user_id=user_id,
                exchange_name=exchange_name,
                api_key=api_key,
                api_secret=api_secret,
                api_passphrase=api_passphrase
            )
            self.db.add(new_key)
            await self.db.flush()
            return new_key.id

    async def get_active_keys(self, user_id: int) -> List[ExchangeKey]:
        stmt = select(ExchangeKey).where(ExchangeKey.user_id == user_id, ExchangeKey.is_active == True)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def delete_exchange_key(self, user_id: int, exchange_name: str):
        stmt = delete(ExchangeKey).where(ExchangeKey.user_id == user_id, ExchangeKey.exchange_name == exchange_name)
        await self.db.execute(stmt)
