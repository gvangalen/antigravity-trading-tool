"""Compatibility tombstone for queued jobs from the retired Setup AI Agent.

The live setup match is calculated from owner-scoped setup conditions and
measured benchmark components when read. Old queued Celery messages must not
write a second, incompatible daily setup score after the migration.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="backend.celery_task.setup_task.run_setup_agent_daily")
def run_setup_agent_daily(user_id: int):
    logger.info("Retired Setup AI Agent task ignored for user_id=%s", user_id)
    return {
        "status": "disabled",
        "reason": "retired_setup_ai_agent",
        "user_id": user_id,
    }
