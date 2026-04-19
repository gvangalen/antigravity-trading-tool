import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
import sys
import json

# Add backend to path
sys.path.append(os.getcwd())

from backend.services.ai_assistant_service import AiAssistantService
from backend.services.ai_gateway import AiGateway
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.database import ASYNC_DATABASE_URL

async def test_scenario(service, user_id, page, symbol):
    print(f"\n--- SCENARIO: Page={page}, Symbol={symbol} ---")
    context = {"page_type": page, "symbol": symbol, "timeframe": "Wekelijks"}
    insight = await service.get_assistant_insight(user_id, context)
    print(f"GREETING: {insight.get('greeting')}")
    print(f"BOT CONCLUSIE: {insight.get('bot_insight', {}).get('conclusion')}")
    print(f"MARKT CONCLUSIE: {insight.get('market_insight', {}).get('conclusion')}")
    return insight

async def verify_full_context():
    print("🚀 Running Pro-Personalization Validation (Dashboard vs Bots)...")
    
    # Load ENV
    from dotenv import load_dotenv
    load_dotenv(".env")
    
    engine = create_async_engine(ASYNC_DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
        # FORCE CLEAR CACHE & UNLOCK QUOTA
        from sqlalchemy import text
        print("🧹 Clearing AI cache and UNLOCKING quota for User 30...")
        await db.execute(text("DELETE FROM ai_response_cache WHERE category = 'assistant'"))
        await db.execute(text("UPDATE users SET ai_requests_limit_day = 500, ai_requests_used_day = 0 WHERE id = 30"))
        await db.commit()
        
        user_repo = UserRepository(db)
        score_repo = ScoreRepository(db)
        setup_repo = SetupRepository(db)
        report_repo = ReportRepository(db)
        bot_repo = BotRepository(db)
        market_data_repo = MarketDataRepository(db)
        strategy_repo = StrategyRepository(db)
        ai_gateway = AiGateway(user_repo, score_repo)
        
        service = AiAssistantService(
            score_repo, setup_repo, report_repo, bot_repo, user_repo, 
            market_data_repo, strategy_repo, ai_gateway
        )
        
        user_id = 30 # Henk
        
        # Test 1: Dashboard Context (BTC)
        res1 = await test_scenario(service, user_id, "Dashboard", "BTC")
        print(f"FULL RESPONSE 1: {json.dumps(res1, indent=2)}")
        
        # Test 2: Bots Page Context (ETH)
        res2 = await test_scenario(service, user_id, "Bots", "ETH")
        print(f"FULL RESPONSE 2: {json.dumps(res2, indent=2)}")
        
        # Validation
        print("\n--- FINAL VERDICT ---")
        if "Henk" in res1['greeting'] and "Dashboard" in res1['greeting']:
             print("✅ Greeting Personalisatie (Name/Page) OK.")
        else:
             print("❌ Greeting Personalisatie FAILED.")
             
        if "Bots" in res2['greeting'] and "ETH" in res2['greeting']:
             print("✅ Context Awareness (Switching Page/Asset) OK.")
        else:
             print("❌ Context Awareness FAILED.")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_full_context())
