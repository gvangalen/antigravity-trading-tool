"""Compatibility tombstone for regime-agent jobs queued before the cutover.

No periodic schedule publishes this task. Workers acknowledge any old queued
message without generating or storing user-wide intelligence.
"""

from celery import shared_task


@shared_task(name="backend.celery_task.regime_memory_task.run_regime_memory")
def run_regime_memory(*args, **kwargs):
    return {"status": "disabled", "reason": "retired_regime_agent"}
