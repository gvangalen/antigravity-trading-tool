# Platform Hardening Step 6 - Enterprise Safety Slice

Date: 2026-05-25

## Goal

Add the first enterprise-style reliability controls without introducing new product behavior:

- request-level traceability for every backend request
- deploy recovery that verifies PM2 process state, not only command exit codes

## Changes

### Request Trace ID

The FastAPI app now attaches a trace id to every request:

- accepts incoming `x-trace-id`
- generates `trdm-req-...` when no trace id is provided
- stores it on `request.state.trace_id`
- returns it as `X-Trace-Id` on the response

This does not replace the richer assistant `trace_id`; it gives every API path a common operational correlation id.

### PM2 Deploy Gate

`deploy_live.sh` now verifies that all expected PM2 apps are present and `online` after reload:

- `frontend`
- `backend`
- `celery-worker-default`
- `celery-worker-market-portfolio`
- `celery-worker-scoring-execution`
- `celery-worker-ai-reporting`
- `celery-beat`

If `pm2 startOrReload` returns but one of those apps is missing or not online, deploy rebuilds the process list with:

```bash
pm2 delete all
pm2 start ecosystem.config.js --update-env
```

Then it runs the PM2 gate again before saving the process list and continuing to API health checks.

## Why This Matters

The previous deploy path could reach the health gate after PM2 reported reload errors or left processes in `stopping`. The deploy now treats PM2 state as an explicit rollout invariant.

## Regression Coverage

`backend/tests/test_enterprise_hardening_step6.py` checks:

- backend request trace middleware is registered
- `X-Trace-Id` is returned
- deploy script validates PM2 state
- deploy script has a fallback rebuild path

