# Platform Hardening Status

Last updated: 2026-05-25

This document tracks the reliability/platform hardening track after the first six phases. It separates what is now production-ready for V1 from what remains legacy, scale-tuning, or enterprise-level work.

## Executive Summary

The core platform hardening track is now green for V1 correctness:

- DB/state races have been reduced with atomic writes and explicit uniqueness.
- Portfolio snapshots no longer silently price every bot as BTC.
- App startup is schema-read-only; runtime DDL moved to explicit migrations.
- Celery routing is named, observable, and backed by split workers.
- Deploys are gated by lightweight and deep health checks.
- Request-path consistency is guarded by tests; process-local caches are disabled or explicit.

The main remaining risk is operational scale, not core request correctness:

- legacy `celery` backlog still needs controlled drain cycles
- old psycopg2/background flows remain as explicit legacy boundaries
- frontend polling/read-amplification has a first V1 reduction in place
- first enterprise rollout/tracing controls are in place

## Phase Status

| Phase | Status | What Is Now True |
| --- | --- | --- |
| Phase 1 - DB & State Correctness | Green | Conversation state UPSERT, atomic AI usage increments, AI cache context uniqueness, no parallel shared `AsyncSession` in mobile overview. |
| Phase 2 - Portfolio & Execution Invariants | Green | Bot snapshots use real symbols, missing symbol price skips that bot, BTC aggregate fields are BTC-specific, manual order idempotency and live preflight invariants are regression-tested. |
| Phase 3 - Runtime DDL To Migrations | Green | `main.py` startup is schema-read-only; prior startup DDL moved to explicit migration scripts. |
| Phase 4 - Queue & Celery Throughput | Green for architecture, operations ongoing | Named queues, split PM2 workers, centralized queue policy, bounded dispatcher, workload rate limits, deep-health queue visibility, and legacy drain tooling are in place. |
| Phase 5 - Observability & Deployment Safety | Green | `/api/health` remains lightweight; `/api/system/health` reports DB, broker, workers, queues, market/scores freshness; deploy gate parses deep health and supports strict degraded handling. |
| Phase 6 - Cleanup & Consistency | Green | Notifications API is authenticated-user scoped and async; dashboard/intelligence process caches are opt-in; API sync DB patterns and psycopg2 boundaries are tested. |
| Step 5 - Frontend Cache/Polling | Green | Authenticated GET helpers no longer force global `no-store`; dashboard polling is visibility-aware and single-flight. |
| Step 6 - Enterprise Safety Slice | Green | API responses carry `X-Trace-Id`; deploy verifies expected PM2 apps are online and rebuilds the process list if reload leaves gaps. |

## Current Live Baseline

Latest deployed hardening commit:

- `d8199a2` - `Fix PM2 deploy gate parser`

Latest smoke results from deploy:

- `/api/health`: `ok`
- `/api/system/health`: `ok`
- `/report`: `200`
- Celery workers: `default`, `market-portfolio`, `scoring-execution`, `ai-reporting`

Latest local regression:

- `pytest -q`: `283 passed`

## What Is Done

### DB/state correctness

- `conversation_state` saves with `ON CONFLICT (user_id) DO UPDATE`.
- AI usage increments use atomic SQL updates.
- AI cache uniqueness is context-aware: `query_hash + symbol + timeframe + category`.
- Mobile overview no longer parallelizes DB work through the same request `AsyncSession`.

### Portfolio/execution invariants

- Bot portfolio snapshots resolve the bot/strategy/setup symbol.
- Missing symbol price skips only that bot snapshot and logs the skip.
- Global snapshot keeps legacy `btc_qty` / `btc_value_eur` BTC-specific.
- Manual orders have DB-level idempotency on `(user_id, idempotency_key)`.
- Live manual orders require idempotency, risk acknowledgement, and a recent approved live preflight before persistence.
- Bot decision writes remain unique per `user_id / bot_id / decision_date`.

### Migrations/startup

- Startup no longer mutates schema.
- Runtime DDL hotfixes are in versioned scripts.
- Deploy runs explicit migrations before PM2 reload.

### Queue/Celery

- Queue routing lives in one policy module.
- Beat and dispatcher use the same queue policy.
- Workers are split by queue class.
- Global wildcard throttle is gone.
- Rate limits are workload/provider-aware.
- Deep health shows queue depths, worker mapping, rate-limit policy, and default queue sample.
- Legacy/default queue drain tooling is bounded and writes operator artifacts.

### Observability/deploy

- Lightweight health stays load-balancer friendly.
- Deep health is operationally useful and rollout-gated.
- Deploy script no longer runs user-specific business actions.
- Deploy readiness window is robust enough for current backend startup time.

### Cleanup/consistency

- Notifications API no longer trusts `user_id` from request body for ownership.
- New API modules are guarded against sync `Session` / `.query()` patterns.
- Process-local dashboard and intelligence caches are disabled by default.
- psycopg2 usage is explicitly allowlisted to legacy/background boundaries.

## Remaining Risks

### V1 operations

- The default `celery` queue still contains a large legacy backlog.
- Continue bounded drain cycles and stop when the reroute ratio drops or default becomes mostly dispatcher/fallback work.
- Deep health may be slower while queue depth remains high; use component status and queue samples rather than raw depth alone.

### Legacy boundaries

- `PushService` is async-first; its sync compatibility method opens an async session and does not carry sync query logic.
- psycopg2 remains in explicit background/scoring/reporting paths:
  - `backend/ai_core/regime_memory.py`
  - `backend/celery_task/daily_report_task.py`
  - `backend/scripts/database.py`
  - `backend/utils/db.py`

### Scale tuning later

- Frontend polling and `no-store` read amplification have a first pass complete; deeper page-by-page polling tuning can follow once traffic data shows the next hotspot.
- Process-local read caches should remain opt-in unless moved to Redis/shared cache with explicit invalidation.
- Queue age/throughput metrics would make backlog health easier to interpret than depth alone.

### Enterprise later

- Deep end-to-end tracing per decision/order/report beyond the request `X-Trace-Id`.
- Rollback automation beyond documented commands and PM2 process-state gates.
- Multi-instance cache coordination.
- Stronger replay protection and exactly-once semantics across all execution-adjacent flows.

## Recommended Next Work

1. Controlled legacy queue drain operations are active.
   - Use `docs/operations/legacy-celery-queue-drain.md`.
   - Save artifacts and compare `operator_summary`.
   - Stop based on `reroute_ratio_after` and `top_tasks_after`, not total backlog alone.
   - Latest controlled run processed `9000`, rerouted `8782`, kept `218`, then stopped on `reroute_ratio_below_threshold`.
   - Do not continue immediately when named queues are already materially fuller; wait for them to drain first.

2. Use queue age/throughput fields in deep health while draining.
   - `queue_metrics.<queue>.oldest_message_age_seconds` is available for newly published tasks stamped with `published_at`.
   - `queue_metrics.<queue>.timestamped_sample_size` shows how much of the sampled queue can be aged.
   - `queue_metrics.<queue>.estimated_drain_per_minute` is based on the previous health check in the current backend process.
   - Legacy messages without a publish timestamp intentionally report `age_source = unavailable`.

3. Continue with the remaining platform cleanup sequence.
   - psycopg2 legacy boundary migration/isolation is complete at the driver boundary: direct driver imports are centralized in `backend/utils/db.py`.
   - PushService sync DB cleanup is complete: PushService is async-first and the sync method is compatibility-only.
   - Frontend polling / `no-store` reduction is complete for the shared auth clients and dashboard scores hook.

4. Then return to product OS work.
   - Portfolio Risk 2.0 or Reports/Reflection 2.0 are now safer to build on top of this platform base.

## QA Reference

Useful commands:

```bash
pytest -q
```

Targeted platform checks:

```bash
pytest -q \
  backend/trading-tool-backend/backend/tests/test_platform_hardening.py \
  backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py \
  backend/trading-tool-backend/backend/tests/test_phase6_consistency_boundaries.py \
  backend/trading-tool-backend/backend/tests/test_celery_queue_policy.py \
  backend/trading-tool-backend/backend/tests/test_system_health_service.py \
  backend/trading-tool-backend/backend/tests/test_run_legacy_queue_drain_cycle_script.py
```

Live smoke:

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/system/health
curl -fsSI http://127.0.0.1:5002/report | head -n 1
```
