# Platform Hardening Tranche B — Queue Discipline

Last updated: 2026-06-05

## Goal

Make periodic fan-out safer under load by tightening dispatch discipline.

This tranche focuses on three things:

- backlog-aware dispatch
- overlap-safe wave dispatch
- consistent queue naming across production and staging

## What Changed

Implemented in the current working tree:

- queue policy now resolves environment-aware queue names
- staging uses prefixed queue names consistently from routing through PM2 worker topology
- dispatcher now checks queue backlog before enqueueing a new wave
- dispatcher now acquires a per-workflow wave lease per dispatch window
- dispatcher now dedupes per `(workflow, user, window)` before enqueueing
- deep health now reads default queue depth from the resolved queue policy instead of a hardcoded queue name

## Primary Touchpoints

- [backend/trading-tool-backend/backend/celery_task/queue_policy.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/queue_policy.py)
- [backend/trading-tool-backend/backend/celery_task/dispatcher.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/dispatcher.py)
- [backend/trading-tool-backend/backend/celery_task/celery_app.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/celery_app.py)
- [backend/trading-tool-backend/backend/services/system_health_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/system_health_service.py)

## Validation Snapshot

- `pytest -q backend/trading-tool-backend/backend/tests/test_celery_dispatcher.py backend/trading-tool-backend/backend/tests/test_celery_queue_policy.py` -> `21 passed`
- `pytest -q backend/trading-tool-backend/backend/tests/test_system_health_service.py backend/trading-tool-backend/backend/tests/test_celery_dispatcher.py backend/trading-tool-backend/backend/tests/test_celery_queue_policy.py` -> `34 passed`
- `python3 -m py_compile` on touched queue files -> green

## Acceptance Read

This tranche is locally ready when:

- a queue that is already behind can skip a new dispatch wave cleanly
- the same workflow window cannot dispatch multiple concurrent waves
- the same user is not re-enqueued twice inside one workflow window
- staging and production producers/consumers resolve the same queue names
