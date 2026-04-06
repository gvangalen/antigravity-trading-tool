import asyncio
import os
from sqlalchemy import select
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import User, Indicator

async def research():
    async with async_session_factory() as session:
        # 1. Check User 30
        res = await session.execute(select(User).where(User.id == 30))
        user = res.scalars().first()
        print(f"USER 30: {user.id if user else 'NOT FOUND'} (Email: {user.email if user else 'N/A'})")

        # 2. Global Indicators
        res = await session.execute(select(Indicator))
        indicators = res.scalars().all()
        print(f"GLOBAL INDICATORS: {[(i.name, i.category) for i in indicators]}")

if __name__ == "__main__":
    asyncio.run(research())
