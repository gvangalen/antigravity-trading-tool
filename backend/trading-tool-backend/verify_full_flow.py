import asyncio
import logging
import sys
import os

# Set up logging to see Gateway movements
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY_FLOW")

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.ai_gateway import AiGateway

async def run_verification():
    logger.info("🎬 Starting Phase 3 Full-Flow Verification (LIVE)...")
    
    async with async_session_factory() as session:
        user_repo = UserRepository(session)
        score_repo = ScoreRepository(session)
        gateway = AiGateway(user_repo, score_repo)

        user_id = 30 # Henk
        symbol = "BTC/USDT"
        timeframe = "1H"
        purpose = "assistant"

        # TEST 1: Full AI Request
        prompt_1 = "Why is risk management important in trading?"
        logger.info(f"\n[1] Making REAL AI Request: '{prompt_1}'")
        res_1 = await gateway.ask(
            user_id=user_id, prompt=prompt_1, 
            system_role="You are a trading expert.", 
            purpose=purpose, symbol=symbol, timeframe=timeframe
        )
        logger.info(f"✅ Response 1 received (Length: {len(str(res_1))})")

        # TEST 2: Exact Match
        logger.info(f"\n[2] Making EXACT Match Request (same query)...")
        res_2 = await gateway.ask(
            user_id=user_id, prompt=prompt_1, 
            system_role="You are a trading expert.", 
            purpose=purpose, symbol=symbol, timeframe=timeframe
        )

        # TEST 3: Semantic Match
        prompt_3 = "Tell me why managing risk is crucial for traders?"
        logger.info(f"\n[3] Making SEMANTIC Match Request: '{prompt_3}'")
        res_3 = await gateway.ask(
            user_id=user_id, prompt=prompt_3, 
            system_role="You are a trading expert.", 
            purpose=purpose, symbol=symbol, timeframe=timeframe
        )

        # TEST 4: Context Lock (Check if ETH/USDT also hits the BTC cache)
        logger.info(f"\n[4] Checking Context Lock (ETH/USDT context)...")
        res_4 = await gateway.ask(
            user_id=user_id, prompt=prompt_1, 
            system_role="You are a trading expert.", 
            purpose=purpose, symbol="ETH/USDT", timeframe=timeframe
        )

        logger.info("\n🏁 Verification Flow Completed.")

if __name__ == "__main__":
    # Ensure PYTHONPATH includes current dir
    sys.path.append(os.getcwd())
    asyncio.run(run_verification())
