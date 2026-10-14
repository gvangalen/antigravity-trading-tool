"""Poll submitted exchange orders and settle confirmed fills."""

from celery import shared_task

from backend.services.bot_live_reconciliation import reconcile_live_orders


@shared_task(name="backend.celery_task.bot_reconciliation_task.reconcile_live_bot_orders")
def reconcile_live_bot_orders():
    return reconcile_live_orders()
