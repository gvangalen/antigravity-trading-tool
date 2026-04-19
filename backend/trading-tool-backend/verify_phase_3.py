import asyncio
import os
import sys
import logging
from sqlalchemy import text

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from backend.services.ai_gateway import AiGateway
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.database import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VERIFY_PHASE_3")

async def run_test():
    logger.info("🧪 Starting Phase 3 Verification...")
    
    async with async_session_factory() as db:
        user_repo = UserRepository(db)
        score_repo = ScoreRepository(db)
        gateway = AiGateway(user_repo, score_repo)
        
        user_id = 30 # Henk
        
        # Test 1: FULL AI CALL
        logger.info("\n[TEST 1] Initial call (Full AI)...")
        prompt1 = "What are the core benefits of using a trading bot for discipline?"
        res1 = await gateway.ask(user_id, prompt1, "You are a trading mentor", purpose="assistant", symbol="GLOBAL")
        
        # Check logs
        stmt = text("SELECT status, similarity_score FROM ai_usage_logs ORDER BY timestamp DESC LIMIT 1")
        row = (await db.execute(stmt)).mappings().first()
        logger.info(f"Result: {row['status']} | Similarity: {row['similarity_score']}")

        # Test 2: EXACT MATCH
        logger.info("\n[TEST 2] Exact Match (Same prompt)...")
        res2 = await gateway.ask(user_id, prompt1, "You are a trading mentor", purpose="assistant", symbol="GLOBAL")
        row = (await db.execute(stmt)).mappings().first()
        logger.info(f"Result: {row['status']} | Similarity: {row['similarity_score']}")

        # Test 3: SEMANTIC MATCH
        logger.info("\n[TEST 3] Semantic Match (Similar prompt)...")
        prompt2 = "Explain the advantages of automated trading for staying disciplined."
        res3 = await gateway.ask(user_id, prompt2, "You are a trading mentor", purpose="assistant", symbol="GLOBAL")
        row = (await db.execute(stmt)).mappings().first()
        logger.info(f"Result: {row['status']} | Similarity: {row['similarity_score']}")

        # Test 4: CONTEXT MISMATCH (Symbol)
        logger.info("\n[TEST 4] Context Separation (Same question, different symbol)...")
        # Voor de assistant is 'GLOBAL' de default, maar laten we een technische analyse doen
        prompt3 = "Analyze the current trend."
        logger.info("First for BTC...")
        await gateway.ask(user_id, prompt3, "Analyst", purpose="technical", symbol="BTC/USDT")
        
        logger.info("Now for ETH with same question (Should be Full AI)...")
        await gateway.ask(user_id, prompt3, "Analyst", purpose="technical", symbol="ETH/USDT")
        
        row = (await db.execute(stmt)).mappings().first()
        logger.info(f"Result: {row['status']} (Expected: full_ai)")

    logger.info("\n✅ Verification Completed.")

if __name__ == "__main__":
    asyncio.run(run_test())
