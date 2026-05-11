import asyncio
import sys
import os

# Set up path so we can import backend packages
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.infrastructure.database import async_session_factory
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository
from backend.infrastructure.repositories.conversation_state_repository import ConversationStateRepository
from backend.infrastructure.repositories.assistant_context_repository import AssistantContextRepository
from backend.services.ai_gateway import AiGateway
from backend.services.ai_assistant_service import AiAssistantService

import logging
logging.basicConfig(level=logging.INFO)

async def test_flow():
    print("🚀 Starting Hybrid AI + Confirm UX Sequential Verification...\n")
    
    async with async_session_factory() as session:
        score_repo = ScoreRepository(session)
        setup_repo = SetupRepository(session)
        report_repo = ReportRepository(session)
        bot_repo = BotRepository(session)
        user_repo = UserRepository(session)
        market_data_repo = MarketDataRepository(session)
        strategy_repo = StrategyRepository(session)
        state_repo = ConversationStateRepository(session)
        context_repo = AssistantContextRepository(session)
        ai_gateway = AiGateway(user_repo, score_repo)
        
        service = AiAssistantService(
            score_repo, setup_repo, report_repo, bot_repo, user_repo,
            market_data_repo, strategy_repo, state_repo, ai_gateway, context_repo
        )
        
        user_id = 30  # Henk
        
        # Clear any existing state first
        await state_repo.clear_state(user_id)
        print("🧹 Cleared initial state.")

        # SEQUENCE OF TURNS
        turns = [
            ("maak een strategie voor SOL", "Init strategy flow for SOL"),
            ("trade", "Specify setup_type as 'trade'"),
            ("stop-loss is 140", "Specify stop-loss (Verify NO premature cancel, and slot captured!)"),
            ("maak de setup", "Finalize flow immediately")
        ]

        for idx, (query, desc) in enumerate(turns, 1):
            print(f"\n--- [TURN {idx}] {desc} ---")
            print(f"User Query: '{query}'")
            
            # Use non-streaming chat endpoint to inspect the full parsed structure easily
            response_text, action, draft, state, reasoning, suggested_actions = await service.get_chat_response(
                user_id=user_id,
                user_query=query,
                context_data={"symbol": "SOL"}
            )
            
            print(f"AI Response: {response_text}")
            print(f"Returned State: {state}")
            print(f"Returned Action: {action}")
            print(f"Returned Draft: {draft}")
            print(f"Returned Suggested Actions: {suggested_actions}")
            
            # Fetch and print DB state to confirm state persistence
            db_state = await state_repo.get_state(user_id)
            print(f"DB Saved State: {db_state}")

if __name__ == "__main__":
    asyncio.run(test_flow())
