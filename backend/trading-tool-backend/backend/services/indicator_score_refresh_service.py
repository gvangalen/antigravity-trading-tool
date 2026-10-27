"""Request a new Score 2.0 snapshot after an indicator configuration changes."""

import logging

logger = logging.getLogger(__name__)


def queue_indicator_score_refresh(user_id: int, symbol: str,
                                  *, market_id: int | None = None) -> bool:
    """Refresh only the affected asset; the periodic sweep remains a fallback."""
    normalized_symbol = str(symbol or "").strip().upper()
    if not normalized_symbol or (market_id is not None and
                                  (type(market_id) is not int or market_id <= 0)):
        return False
    try:
        from backend.celery_task.celery_app import celery_app

        kwargs = ({"user_id": int(user_id), "market_id": market_id}
                  if market_id is not None else
                  {"user_id": int(user_id), "symbol": normalized_symbol})
        celery_app.send_task(
            "backend.celery_task.store_daily_scores_task.store_daily_scores_task",
            kwargs=kwargs,
        )
        return True
    except Exception:
        logger.warning(
            "Indicator score refresh will wait for the periodic sweep: symbol=%s",
            normalized_symbol,
            exc_info=True,
        )
        return False
