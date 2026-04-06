import asyncio
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import Indicator
from sqlalchemy import update

async def main():
    async with async_session_factory() as s:
        # Enable the requested indicators
        targets = ['dxy', 'interest_rate', 'inflation_rate', 'sp500', 'vix']
        await s.execute(
            update(Indicator)
            .where(Indicator.name.in_(targets))
            .values(active=True)
        )
        await s.commit()
        print(f"✅ Indicators enabled: {targets}")

if __name__ == "__main__":
    asyncio.run(main())
