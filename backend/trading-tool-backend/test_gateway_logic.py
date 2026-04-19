import asyncio
import os
import sys
import logging
import json
from unittest.mock import patch, MagicMock
from sqlalchemy import text

# Setup paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), ".")))

from backend.services.ai_gateway import AiGateway
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.database import async_session_factory

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LOGIC_TEST")

async def run_logic_test():
    logger.info("🧪 Starting Logic Verification (Mock Mode)...")
    
    async with async_session_factory() as db:
        user_repo = UserRepository(db)
        score_repo = ScoreRepository(db)
        gateway = AiGateway(user_repo, score_repo)
        
        user_id = 30 # Henk
        
        # MOCK OpenAI & Embeddings
        # We simuleren dat "Hi" en "Hello" semantisch hetzelfde zijn (beide 1536 dims)
        mock_emb_hi = [0.1] * 1536
        mock_emb_hello = [0.101] * 1536 # Heel dichtbij -> >0.92 similarity
        
        with patch('backend.services.ai_gateway.get_embedding') as mock_get_emb, \
             patch('backend.services.ai_gateway.ask_gpt_text_raw') as mock_ask:
            
            # Setup Mocks
            mock_ask.return_value = {
                "content": "Simulated AI Response",
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "model": "gpt-4o-mini"}
            }

            # 🟢 TEST 1: INITIAL CALL (FULL AI)
            logger.info("\n[1] Initial Call (BTC context)...")
            mock_get_emb.return_value = mock_emb_hi
            await gateway.ask(user_id, "Hi", "Role", purpose="assistant", symbol="BTC/USDT")
            
            # 🟢 TEST 2: EXACT MATCH (Should be instant)
            logger.info("[2] Exact Match Check...")
            await gateway.ask(user_id, "Hi", "Role", purpose="assistant", symbol="BTC/USDT")
            
            # 🟢 TEST 3: CONTEXT LOCK (Same text, different symbol -> Should be Full AI)
            logger.info("[3] Context Lock Check (ETH/USDT)...")
            await gateway.ask(user_id, "Hi", "Role", purpose="assistant", symbol="ETH/USDT")

            # 🟢 TEST 4: SEMANTIC MATCH (Different text 'Hello')
            logger.info("[4] Semantic Match Check ('Hello' vs 'Hi')...")
            mock_get_emb.return_value = mock_emb_hello
            await gateway.ask(user_id, "Hello", "Role", purpose="assistant", symbol="BTC/USDT")

            # Final check logs in DB
            stmt = text("SELECT status, symbol, similarity_score FROM ai_usage_logs ORDER BY timestamp DESC LIMIT 4")
            rows = (await db.execute(stmt)).mappings().all()
            
            logger.info("\n📊 VERIFICATION RESULTS (Last 4 calls):")
            for r in reversed(rows):
                score_str = f" | Sim: {r['similarity_score']}" if r['similarity_score'] else ""
                logger.info(f"Symbol: {r['symbol']} | Mode: {r['status']}{score_str}")

    logger.info("\n✅ Logic Verification Completed.")

if __name__ == "__main__":
    asyncio.run(run_logic_test())
