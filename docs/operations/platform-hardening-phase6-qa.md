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
  -q
```

Expected:

- notifications API has no sync `.query()` request path
- notifications API uses authenticated user context
- dashboard mobile overview cache is disabled by default
- dashboard mobile overview cache only enables through explicit env flag

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

- Review process-local read caches in macro/technical/intelligence services and decide which are acceptable read-through caches versus consistency-sensitive state.
- Keep sync `PushService` DB usage isolated to legacy/background notification dispatch paths.
- Later migrate legacy psycopg2 usage out of scoring/reporting/background paths when those flows are being touched.
