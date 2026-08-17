from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from celery import shared_task

from backend.services.finn_v2_gateway_service import (
    run_retention_cleanup_job,
    run_shadow_foundation_job,
)


logger = logging.getLogger(__name__)


@shared_task(name="backend.celery_task.finn_v2_task.process_shadow_foundation_run")
def process_shadow_foundation_run(
    *,
    user_id: int,
    request_payload: Dict[str, Any],
    request_path: str,
    request_id: str,
    trace_id: str,
) -> str:
    return asyncio.run(
        run_shadow_foundation_job(
            user_id=user_id,
            request_payload=request_payload,
            request_path=request_path,
            request_id=request_id,
            trace_id=trace_id,
        )
    )


@shared_task(name="backend.celery_task.finn_v2_task.cleanup_finn_v2_retention")
def cleanup_finn_v2_retention() -> Dict[str, int]:
    result = asyncio.run(run_retention_cleanup_job())
    logger.info("FINN V2 retention task completed: %s", result)
    return result
