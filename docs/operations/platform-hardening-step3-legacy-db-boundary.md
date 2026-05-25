# Platform Hardening Step 3 - Legacy DB Boundary

Last updated: 2026-05-25

Step 3 isolates legacy synchronous PostgreSQL access so the driver dependency is no longer scattered across business modules. The first two business flows have now also been moved behind SQLAlchemy repository boundaries.

## What Is Complete

- Direct `psycopg2` imports are centralized in `backend/utils/db.py`.
- JSONB parameters for legacy sync flows use `backend.utils.db.jsonb_param`.
- `backend/scripts/database.py` is now a compatibility wrapper around `backend.utils.db.get_db_connection`.
- Business modules no longer import `psycopg2.extras.Json` directly.
- `backend/ai_core/regime_memory.py` no longer calls `get_db_connection()` directly; it uses `RegimeMemoryRepository`.
- `backend/celery_task/daily_report_task.py` no longer calls `get_db_connection()` directly for the daily report write; it uses `DailyReportWriteRepository`.
- Tests enforce that direct driver imports cannot spread again.

## Current Boundary

Allowed direct driver module:

- `backend/utils/db.py`

Compatibility wrapper:

- `backend/scripts/database.py`

The wrapper is intentionally driver-free and exists for older standalone scripts.

## What Remains Legacy

Many older background/scoring/reporting modules still call `get_db_connection()`. That remains acceptable for the remaining legacy domains because this step specifically migrated the highest-value report/regime paths without rewriting the whole Celery estate in one risky change.

These callers are treated as legacy sync DB clients until their owning flows are migrated:

- Celery tasks
- AI/report agents
- scoring utilities
- backtest/validation scripts
- snapshot/report services that already run outside the new async request-path convention

Migrated from direct sync helper usage:

- `ai_core/regime_memory.py`
- `celery_task/daily_report_task.py`

## Request Path Rule

New API/request-path code should use async SQLAlchemy dependencies. The test suite guards API modules against sync `Session` / `.query()` usage.

## Next Cleanup

Legacy sync callers can continue to be migrated gradually by owning domain:

1. scoring utilities
2. report agents/tasks
3. AI agent data loaders
4. backtest/validation scripts
