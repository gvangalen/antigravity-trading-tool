"""Request a new Score 2.0 snapshot after an indicator configuration changes."""

import logging
import os

logger = logging.getLogger(__name__)


def queue_exact_market_refresh(market_id: int, *, debounce_seconds: int = 0) -> bool:
    """Fetch source candles and materialize scores for one verified pair."""
    if type(market_id) is not int or market_id <= 0:
        return False
    throttle = None
    throttle_key = f"exact-market-select-refresh:{market_id}"
    try:
        from backend.celery_task.celery_app import celery_app
        if debounce_seconds > 0:
            import redis
            throttle = redis.from_url(
                os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/0"),
                socket_connect_timeout=1, socket_timeout=1,
            )
            if not throttle.set(throttle_key, "1", nx=True, ex=debounce_seconds):
                return True
        celery_app.send_task(
            "backend.celery_task.market_task.sync_exact_market_snapshots",
            kwargs={"market_id": market_id},
        )
        return True
    except Exception:
        if throttle is not None:
            try:
                throttle.delete(throttle_key)
            except Exception:
                pass
        logger.warning("Exact market refresh could not be queued: market_id=%s",
                       market_id, exc_info=True)
        return False
    finally:
        if throttle is not None:
            throttle.close()


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
