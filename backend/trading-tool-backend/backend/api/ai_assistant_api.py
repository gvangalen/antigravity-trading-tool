import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.schemas.assistant_schema import AssistantChatRequest, AssistantChatResponse, AssistantPreferences, AssistantPreferenceUpdate, AssistantInsightResponse
from backend.services.ai_assistant_service import AiAssistantService
from backend.services.ai_gateway import AiGateway
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.infrastructure.repositories.setup_repository import SetupRepository
from backend.infrastructure.repositories.report_repository import ReportRepository
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.user_repository import UserRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.strategy_repository import StrategyRepository

router = APIRouter()
logger = logging.getLogger(__name__)

async def get_assistant_service(db: AsyncSession = Depends(get_db)):
    score_repo = ScoreRepository(db)
    setup_repo = SetupRepository(db)
    report_repo = ReportRepository(db)
    bot_repo = BotRepository(db)
    user_repo = UserRepository(db)
    market_data_repo = MarketDataRepository(db)
    strategy_repo = StrategyRepository(db)
    ai_gateway = AiGateway(user_repo, score_repo)
    return AiAssistantService(score_repo, setup_repo, report_repo, bot_repo, user_repo, market_data_repo, strategy_repo, ai_gateway)

@router.post("/assistant/chat", response_model=AssistantChatResponse)
async def assistant_chat(
    request: AssistantChatRequest,
    current_user: dict = Depends(get_current_user),
    service: AiAssistantService = Depends(get_assistant_service)
):
    try:
        user_id = current_user["id"]
        response, action = await service.get_chat_response(user_id, request.query, request.context)
        intent = service._classify_intent(request.query)
        if not isinstance(action, dict):
            action = None
        return AssistantChatResponse(response=response, intent=intent, action=action)
    except Exception as e:
        logger.error(f"❌ AI Assistant Chat Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij AI Assistant")

@router.get("/assistant/preferences", response_model=AssistantPreferences)
async def get_preferences(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(current_user["id"])
    prefs = getattr(user, "ai_preferences", {}) or {}
    # Inject first_name for UI greeting persistence
    if user.first_name:
        prefs["first_name"] = user.first_name
    return AssistantPreferences(preferences=prefs)

@router.patch("/assistant/preferences", response_model=AssistantPreferences)
async def update_preferences(
    request: AssistantPreferenceUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user_repo = UserRepository(db)
    updates = {k: v for k, v in request.dict().items() if v is not None}
    user = await user_repo.update_ai_preferences(current_user["id"], updates)
    return AssistantPreferences(preferences=user.ai_preferences)

@router.post("/assistant/insight", response_model=AssistantInsightResponse)
async def get_insight(
    context: dict,
    current_user: dict = Depends(get_current_user),
    service: AiAssistantService = Depends(get_assistant_service)
):
    try:
        user_id = current_user["id"]
        insight = await service.get_assistant_insight(user_id, context)
        return AssistantInsightResponse(
            greeting=insight.get("greeting", "Hoi!"),
            bot_insight=insight.get("bot_insight"),
            market_insight=insight.get("market_insight"),
            context_detected=context
        )
    except Exception as e:
        logger.error(f"❌ AI Assistant Insight Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Fout bij AI Insight")
