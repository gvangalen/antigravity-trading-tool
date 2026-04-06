import asyncio
import traceback
from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.score_service import ScoreService

async def debug():
    async with async_session_factory() as session:
        repo = ScoreRepository(session)
        service = ScoreService(repo)
        try:
            print("--- TRIGGERING DAILY SCORES (User 30) ---")
            res = await service.get_daily_scores(30)
            print("SUCCESS:")
            print(res.json())
        except Exception:
            print("FAILURE ERROR:")
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(debug())
