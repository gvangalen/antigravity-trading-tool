"""Run the idempotent FINN V2 dispatch recovery/dead-letter procedure.

Use this from an operator shell after a worker or broker incident. It never
creates runs; it only retries deliverable rows and terminalizes stale,
unclaimed rows through the normal typed run lifecycle.
"""
from __future__ import annotations

from backend.celery_task.finn_v2_task import _run_async, _recover_finn_v2_dispatches


if __name__ == "__main__":
    print(_run_async(_recover_finn_v2_dispatches()))
