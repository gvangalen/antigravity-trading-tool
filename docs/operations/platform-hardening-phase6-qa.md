# Platform Hardening Phase 6 QA

Phase 6 focuses on cleanup and consistency after the DB/state, migrations, observability, and queue-hardening phases.

## Scope In This Batch

### Notifications API user scope

`backend/api/notifications_api.py`

- Uses `AsyncSession` with `select` / `delete`.
- Uses authenticated `current_user["id"]` for ownership.
- Keeps optional `user_id` payload fields only for backwards compatibility.
- Web push unsubscribe is scoped to the authenticated user.
- Mobile push unsubscribe is scoped to the authenticated user.

### Dashboard/mobile cache policy

`backend/services/dashboard_service.py`

- Process-local mobile overview cache is disabled by default.
- Cache can only be enabled explicitly with:

```bash
DASHBOARD_OVERVIEW_CACHE_ENABLED=true
```

- This avoids consistency-sensitive mobile/dashboard state depending on a single backend process.

### Market intelligence cache policy

`backend/services/intelligence_service.py`

- Process-local market-intelligence cache is disabled by default.
- Cache can only be enabled explicitly with:

```bash
INTELLIGENCE_SERVICE_CACHE_ENABLED=true
```

- This keeps market-intelligence state consistent across backend processes by default.

### Removed unused service caches

`backend/services/macro_data_service.py`
`backend/services/technical_data_service.py`

- Removed unused class-level process-local cache placeholders.
- This keeps the service boundary honest: if a cache is needed later, it must be intentionally configured and tested.

### Legacy sync DB boundary

The request/API layer is guarded against sync `Session` / `.query()` patterns.

Known psycopg2 usage remains isolated to explicit legacy/background boundaries:

- `backend/ai_core/regime_memory.py`
- `backend/celery_task/daily_report_task.py`
- `backend/scripts/database.py`
- `backend/utils/db.py`

Those paths are not part of the new async request-path convention and can be migrated later when their owning flows are touched.

### Test discovery hygiene

`pytest.ini`

- Root `pytest -q` now runs the maintained backend test suite.
- Old loose scripts outside `backend/tests` are no longer collected as tests.

## Regression Commands

From repo root:

```bash
pytest -q
```

Expected:

- all tests pass
- no collection errors from `scratch/`, root utility scripts, frontend, mobile, or generated output folders

Targeted checks:

```bash
cd backend/trading-tool-backend
PYTHONPATH=. pytest \
  backend/tests/test_notifications_api_hardening.py \
  backend/tests/test_dashboard_cache_policy.py \
  backend/tests/test_intelligence_cache_policy.py \
  backend/tests/test_phase6_consistency_boundaries.py \
  -q
```

Expected:

- notifications API has no sync `.query()` request path
- notifications API uses authenticated user context
- dashboard mobile overview cache is disabled by default
- dashboard mobile overview cache only enables through explicit env flag
- market-intelligence cache is disabled by default
- API modules do not use sync `Session` / `.query()` request-path patterns
- psycopg2 imports stay inside the explicit legacy allowlist

## Live Smoke

After deploy:

```bash
curl -fsS http://127.0.0.1:8000/api/health
```

Expected:

- `{"status":"ok","message":"API is running"}`

Optional deep health:

```bash
curl -fsS http://127.0.0.1:8000/api/system/health
```

Note: deep health can be slower during queue drain/load windows. Treat a timeout separately from this Phase 6 API/cache cleanup unless lightweight health or PM2 is also unhealthy.

## Remaining Phase 6 Follow-Ups

- Keep sync `PushService` DB usage isolated to legacy/background notification dispatch paths.
- Later migrate legacy psycopg2 usage out of scoring/reporting/background paths when those flows are being touched.
- Frontend polling / `no-store` read-amplification remains a later scale-tuning track, not a request-path correctness blocker.
