# Platform Hardening Step 3 - Legacy DB Boundary

Last updated: 2026-05-25

Step 3 isolates legacy synchronous PostgreSQL access so the driver dependency is no longer scattered across business modules.

## What Is Complete

- Direct `psycopg2` imports are centralized in `backend/utils/db.py`.
- JSONB parameters for legacy sync flows use `backend.utils.db.jsonb_param`.
- `backend/scripts/database.py` is now a compatibility wrapper around `backend.utils.db.get_db_connection`.
- Business modules no longer import `psycopg2.extras.Json` directly.
- Tests enforce that direct driver imports cannot spread again.

## Current Boundary

Allowed direct driver module:

- `backend/utils/db.py`

Compatibility wrapper:

- `backend/scripts/database.py`

The wrapper is intentionally driver-free and exists for older standalone scripts.

## What Remains Legacy

Many older background/scoring/reporting modules still call `get_db_connection()`. That is acceptable for this step because the goal is driver isolation, not rewriting every legacy business flow at once.

These callers are treated as legacy sync DB clients until their owning flows are migrated:

- Celery tasks
- AI/report agents
- scoring utilities
- backtest/validation scripts
- snapshot/report services that already run outside the new async request-path convention

## Request Path Rule

New API/request-path code should use async SQLAlchemy dependencies. The test suite guards API modules against sync `Session` / `.query()` usage.

## Next Cleanup

The next platform step is `PushService` sync DB cleanup. After that, legacy sync callers can be migrated gradually by owning domain:

1. scoring utilities
2. report agents/tasks
3. AI agent data loaders
4. backtest/validation scripts
