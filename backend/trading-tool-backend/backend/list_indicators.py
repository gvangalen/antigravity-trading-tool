import asyncio
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import Indicator
from sqlalchemy import select

async def main():
    async with async_session_factory() as s:
        res = await s.execute(select(Indicator))
        inds = res.scalars().all()
        for i in inds:
            print(f"{i.name} ({i.category})")

if __name__ == "__main__":
    asyncio.run(main())
