import asyncio
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.models import Indicator, DailyScore
from sqlalchemy import select

async def main():
    async with async_session_factory() as s:
        # 1. Check all indicators
        res = await s.execute(select(Indicator))
        inds = res.scalars().all()
        print("--- INDICATORS ---")
        for i in inds:
            print(f"Name: {i.name}, Category: {i.category}, Active: {i.active}")

        # 2. Check DailyScore for 30
        res = await s.execute(select(DailyScore).where(DailyScore.user_id == 30).order_by(DailyScore.report_date.desc()).limit(1))
        score = res.scalars().first()
        print("\n--- DAILY SCORE (ID 30) ---")
        if score:
            print(f"Date: {score.report_date}")
            print(f"Macro: {score.macro_score}")
            print(f"Tech: {score.technical_score}")
            print(f"Market: {score.market_score}")
            print(f"Setup: {score.setup_score}")
        else:
            print("No score found for user 30")

if __name__ == "__main__":
    asyncio.run(main())
