import asyncio
import sys
import os

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.ai_gateway import AiGateway

async def verify():
    print("🧪 Verifying Symbol Logging Fix...")
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        score_repo = ScoreRepository(session)
        gateway = AiGateway(user_repo, score_repo)

        for asset in ["BTC/USDT", "ETH/USDT", "SOL/USDT"]:
            print(f" > Calling for {asset}...")
            await gateway.ask(30, f"Tell me one thing about {asset}", "Expert", symbol=asset)
    
    print("✅ Verification calls completed.")

if __name__ == "__main__":
    sys.path.append(os.getcwd())
    asyncio.run(verify())
