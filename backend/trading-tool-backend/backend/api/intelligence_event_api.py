import logging
from typing import List, Dict, Any
from fastapi import APIRouter, HTTPException, Depends

from backend.infrastructure.database import get_db
from backend.utils.auth_utils import get_current_user
from backend.infrastructure.repositories.bot_repository import BotRepository
from backend.infrastructure.repositories.market_data_repository import MarketDataRepository
from backend.infrastructure.repositories.score_repository import ScoreRepository
from backend.services.intelligence_event_service import IntelligenceEventService

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/assistant/events", response_model=List[Dict[str, Any]])
async def get_assistant_events(
    current_user: dict = Depends(get_current_user),
    session = Depends(get_db)
):
    """
    Triggert de realtime evaluatie van actieve risico's en portfolio-events,
    en retourneert de lijst met alle actieve, niet-gearchiveerde events.
    """
    user_id = current_user["id"]
    
    bot_repo = BotRepository(session)
    market_data_repo = MarketDataRepository(session)
    score_repo = ScoreRepository(session)
    
    service = IntelligenceEventService(session, bot_repo, market_data_repo, score_repo)
    
    try:
        # Trigger realtime evaluatie
        try:
            await service.evaluate_and_generate_events(user_id)
        except Exception as eval_err:
            logger.warning(f"⚠️ Fout tijdens evaluate_and_generate_events (geïsoleerd): {eval_err}")
            await session.rollback()
        
        # Haal actieve events op
        events = await service.get_active_events(user_id)
        
        # Format naar JSON dictionaries
        return [
            {
                "id": ev.id,
                "user_id": ev.user_id,
                "type": ev.type,
                "symbol": ev.symbol,
                "title": ev.title,
                "description": ev.description,
                "severity": ev.severity,
                "payload": ev.payload,
                "status": ev.status,
                "created_at": ev.created_at.isoformat() if ev.created_at else None
            }
            for ev in events
        ]
    except Exception as e:
        logger.exception(f"❌ Error in get_assistant_events: {e}")
        raise HTTPException(status_code=500, detail="Fout bij ophalen van live intelligence events")

@router.post("/assistant/events/{event_id}/archive")
async def archive_assistant_event(
    event_id: int,
    current_user: dict = Depends(get_current_user),
    session = Depends(get_db)
):
    """
    Archiveert een specifiek event (wegklikken of dismissen).
    """
    user_id = current_user["id"]
    
    bot_repo = BotRepository(session)
    market_data_repo = MarketDataRepository(session)
    score_repo = ScoreRepository(session)
    
    service = IntelligenceEventService(session, bot_repo, market_data_repo, score_repo)
    
    try:
        success = await service.archive_event(user_id, event_id)
        if not success:
            raise HTTPException(status_code=404, detail="Event niet gevonden of al gearchiveerd")
        return {"success": True, "message": "Event gearchiveerd"}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"❌ Error in archive_assistant_event: {e}")
        raise HTTPException(status_code=500, detail="Fout bij archiveren van event")
