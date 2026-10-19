"""Request a new Score 2.0 snapshot after an indicator configuration changes."""

import logging

logger = logging.getLogger(__name__)


def queue_indicator_score_refresh(user_id: int, symbol: str) -> bool:
    """Refresh only the affected asset; the periodic sweep remains a fallback."""
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol:
        return False
    try:
        from backend.celery_task.celery_app import celery_app

        celery_app.send_task(
            "backend.celery_task.store_daily_scores_task.store_daily_scores_task",
            kwargs={"user_id": int(user_id), "symbol": normalized_symbol},
        )
        return True
    except Exception:
        logger.warning(
            "Indicator score refresh will wait for the periodic sweep: symbol=%s",
            normalized_symbol,
            exc_info=True,
        )
        return False
