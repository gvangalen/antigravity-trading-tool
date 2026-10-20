# backend/celery_task/trading_bot_task.py

import logging
from datetime import date
from typing import Optional

from celery import shared_task

from backend.engine.trading_bot_execution import run_trading_bot_execution
from backend.services.platform_metrics import increment_retry_counter
from backend.services.portfolio_snapshot_service import snapshot_all_for_user

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


@shared_task(
    name="backend.celery_task.trading_bot_task.run_daily_trading_bot",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={"max_retries": 3},
)
def run_daily_trading_bot(self, user_id: int, report_date: Optional[str] = None):

    try:
        run_date = date.fromisoformat(report_date) if report_date else date.today()
    except Exception:
        run_date = date.today()

    logger.info(f"🤖 START | user={user_id} | date={run_date}")

    try:
        # Strategy snapshots are generated independently. A high-frequency bot
        # check must only consume the latest valid snapshot, never invoke AI.
        result = run_trading_bot_execution(
            user_id=user_id,
            report_date=run_date,
        )

        if not result.get("ok"):
            raise RuntimeError(result.get("error") or "trading_bot_execution_failed")

        # 3️⃣ Portfolio snapshot
        try:
            snapshot_all_for_user(user_id, bucket="1h")
            snapshot_all_for_user(user_id, bucket="1d")
        except Exception:
            logger.exception("Portfolio snapshot failed")

        logger.info("✅ DONE")

        return {
            "ok": True,
            "user_id": user_id,
            "date": str(run_date),
            "bots": result.get("bots"),
            "decisions": len(result.get("decisions", [])),
        }

    except Exception as e:
        logger.exception("❌ CRASH")
        increment_retry_counter("trading_bot_task")
        raise
