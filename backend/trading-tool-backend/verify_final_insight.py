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
from backend.infrastructure.database import ASYNC_DATABASE_URL

async def verify_final_insight():
    print("🚀 Verifying Combined AI Insight V1.2 (Action-Oriented)...")
    
    # Load ENV
    from dotenv import load_dotenv
    load_dotenv(".env")
    
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
        context = {"page_type": "Dashboard", "symbol": "BTC", "timeframe": "Wekelijks"}
        
        print(f"\nTriggering Combined Insight for User {user_id}...")
        try:
            insight = await service.get_assistant_insight(user_id, context)
            
            print("\nRAW AI RESPONSE:")
            import json
            print(json.dumps(insight, indent=2))
            
            # Validation
            has_greeting = "greeting" in insight
            has_bot = "bot_insight" in insight
            has_market = "market_insight" in insight
            
            print("\nVALIDATION STATUS:")
            print(f"- Greeting Present: {has_greeting}")
            print(f"- Bot Insight Present: {has_bot}")
            print(f"- Market Insight Present: {has_market}")
            
            if has_greeting and has_bot and has_market:
                print("\n✅ SUCCESS: V1.2 Combined Response is correct.")
                
                # Length check
                bot_conc = insight['bot_insight'].get('conclusion', '')
                mkt_conc = insight['market_insight'].get('conclusion', '')
                
                if len(bot_conc.split('.')) <= 2 and len(mkt_conc.split('.')) <= 2:
                    print("✅ BREVITY: Insights are concise as requested.")
                else:
                    print("⚠️ WARNING: Insights might be longer than 1 sentence.")
                    
            else:
                print("\n❌ FAILED: Missing keys in response structure.")
                
        except Exception as e:
            print(f"\n❌ ERROR: {e}")

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(verify_final_insight())
