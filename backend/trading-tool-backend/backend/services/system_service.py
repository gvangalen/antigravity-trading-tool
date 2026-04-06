import logging
from backend.celery_task.bootstrap_agents_task import bootstrap_agents_task

logger = logging.getLogger(__name__)

class SystemService:
    @staticmethod
    async def bootstrap_agents_for_user(user_id: int) -> dict:
        """
        Triggers the bootstrap celery task for initializing AI agents.
        """
        logger.info(f"SystemService: Triggering bot bootstrap for user {user_id}")
        
        # Fire off Celery background task
        bootstrap_agents_task.delay(user_id)
        
        return {
            "status": "started",
            "message": "AI agents worden geïnitialiseerd",
            "user_id": user_id,
        }
