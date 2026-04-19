import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import os
import sys

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

async def verify_coach_mode():
    print("🚀 Verifying AI Coach Mode V1...")
    
    # Load ENV
    from dotenv import load_dotenv
    load_dotenv(".env")
    
    # Database Setup
    from backend.infrastructure.database import ASYNC_DATABASE_URL
    engine = create_async_engine(ASYNC_DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as db:
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
        
        # Test 1: Keyword Classification
        test_queries = [
            "Waarom koopt mijn bot niet?",
            "Optimaliseer mijn strategie",
            "Ben ik een goede trader of maak ik fouten?",
            "Coach me even"
        ]
        
        print("\n--- Testing Intent Classification ---")
        for q in test_queries:
            intent = service._classify_intent(q)
            print(f"Query: '{q}' -> Intent: {intent}")
            if intent != "coach":
                print(f"❌ FAILED: Expected 'coach' for '{q}'")
        
        # Test 2: Full Response (Real OpenAI Call)
        print("\n--- Testing Real Coach Response (User 30) ---")
        query = "Waarom koopt mijn bot niet bij BTC?"
        print(f"Sending query: {query}")
        
        try:
            response = await service.get_chat_response(user_id, query)
            print("\nAI COACH RESPONSE:")
            print("====================================")
            print(response)
            print("====================================")
            
            if "CONCLUSIE" in response or "ACTIE" in response:
                print("✅ SUCCESS: Correct V1 format detected.")
            else:
                print("⚠️ WARNING: V1 format labels NOT found. Check if coach prompt was used.")
                
        except Exception as e:
            print(f"❌ ERROR calling AI: {e}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_coach_mode())
