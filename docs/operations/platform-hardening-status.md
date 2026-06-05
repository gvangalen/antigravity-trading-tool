# Platform Hardening Status

Last updated: 2026-06-05

This document tracks the reliability/platform hardening track after the first six phases. It separates what is now production-ready for V1 from what remains legacy, scale-tuning, or enterprise-level work.

## Executive Summary

The core platform hardening track is now green for V1 correctness:

- DB/state races have been reduced with atomic writes and explicit uniqueness.
- Portfolio snapshots no longer silently price every bot as BTC.
- App startup is schema-read-only; runtime DDL moved to explicit migrations.
- Celery routing is named, observable, and backed by split workers.
- Deploys are gated by lightweight/deep health checks and now print a concrete rollback helper command.
- Request-path consistency is guarded by tests; write-sensitive process-local caches are removed unless a future shared cache is added.

The main remaining risk is operational scale, not core request correctness:

- legacy `celery` backlog still needs controlled drain cycles
- old psycopg2/background flows remain explicit legacy boundaries, with regime memory and daily report writes moved behind repositories
- frontend polling/read-amplification has a first V1 reduction in place
- first enterprise rollout/tracing controls are in place
- security/auth hardening is functionally green with two final QA proofs still open

## Phase Status

| Phase | Status | What Is Now True |
| --- | --- | --- |
| Phase 1 - DB & State Correctness | Green | Conversation state UPSERT, atomic AI usage increments, AI cache context uniqueness, no parallel shared `AsyncSession` in mobile overview. |
| Phase 2 - Portfolio & Execution Invariants | Green | Bot snapshots use real symbols, missing symbol price skips that bot, BTC aggregate fields are BTC-specific, manual order idempotency and live preflight invariants are regression-tested. |
| Phase 3 - Runtime DDL To Migrations | Green | `main.py` startup is schema-read-only; prior startup DDL moved to explicit migration scripts. |
| Phase 4 - Queue & Celery Throughput | Green for architecture, operations ongoing | Named queues, split PM2 workers, centralized queue policy, bounded dispatcher, workload rate limits, deep-health queue visibility, and legacy drain tooling are in place. |
| Phase 5 - Observability & Deployment Safety | Green | `/api/health` remains lightweight; `/api/system/health` reports DB, broker, workers, queues, market/scores freshness; deploy gate parses deep health, supports strict degraded handling, and records rollback artifacts. |
| Phase 6 - Cleanup & Consistency | Green | Notifications API is authenticated-user scoped and async; dashboard/intelligence/transition process caches are removed for write-sensitive paths; API sync DB patterns and psycopg2 boundaries are tested. |
| Step 5 - Frontend Cache/Polling | Green | Authenticated GET helpers no longer force global `no-store`; dashboard polling is visibility-aware and single-flight. |
| Step 6 - Enterprise Safety Slice | Green | API responses carry `X-Trace-Id`; deploy verifies expected PM2 apps, rebuilds the process list if reload leaves gaps, persists `LAST_GOOD_COMMIT`, and ships an explicit rollback helper. |
| Step 7 - Multi-Instance Cache Coordination | Green | Mobile/dashboard, market-intelligence, and transition-risk process-local caches are removed; future caching must be shared/Redis-backed with explicit invalidation. |
| Step 8 - Replay/Exactly-Once Hardening | Green | Assistant pending actions are atomically claimed before side effects; stored execution results support safe retries; replay inventory documents execution-adjacent guards. |
| Tranche A - Execution Safety | Green | Bot-generated execution now has DB replay guards, atomic `planned -> executing` claims, explicit `failed_execution` fallback, and honest Celery retry semantics. |
| Tranche B - Queue Discipline | Green | Dispatcher now enforces backlog-aware skips, per-wave leases, per-user window dedupe, and queue naming is consistent across production/staging policy paths. |
| Tranche C - Async Session Correctness | Built locally, pending deploy | Dashboard and assistant context paths no longer parallelize shared-session DB reads, and platform hardening tests now guard those paths explicitly. |
| Security Hardening Slice | Nearly green | External `/api/system/health` is operator-only, web/mobile auth contracts are corrected, refresh rotation and logout invalidation work, Finn `action_id` execute + replay is live, and rate limits are enforced on execute/manual-order/preflight routes. Remaining QA is a real user-switch cache pass and hard no-write proof for market-data read routes. |

## Current Live Baseline

Latest deployed hardening commit:

- `ff19938` - `Finish auth refresh-session fix and lock down external system health`

Current rollout candidate:

- `Security slice final QA candidate on Oracle`

Latest smoke results from deploy:

- `/api/health`: `ok`
- `/api/system/health` externally: `401 Missing access token`
- `/report`: `200`
- Celery workers: `default`, `market-portfolio`, `scoring-execution`, `ai-reporting`
- Oracle markers: `HEAD=ff19938a`, `LAST_GOOD_COMMIT=ff19938`, `PREVIOUS_GOOD_COMMIT=4ba495f`

Latest local regression:

- `pytest -q`: `329 passed`

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
- Deploy captures the previous known-good commit in `ops/deploy/PREVIOUS_GOOD_COMMIT`.
- Successful deploys write `ops/deploy/LAST_GOOD_COMMIT`.
- Failed deploys print a ready-to-run `rollback_live.sh <commit>` command.
- `rollback_live.sh` resets code, reloads PM2, gates expected apps, and smokes `/api/health`, `/api/system/health`, and `/report` without running schema migrations.

### Traceability

- `X-Trace-Id` is generated on every request and returned on responses.
- Assistant action execution passes the request trace into Finn action audit rows.
- Manual live order/preflight responses and execution-audit events include the request trace.
- Bot decision trigger/skip/mark-executed responses carry the request trace.
- Mission Control activity feed exposes trace ids from `ai_pending_actions`.

### Security/auth hardening

- External deep health now requires auth; deploy/rollback smoke still works over direct localhost access on Oracle.
- Web login returns cookie-only auth transport and does not expose access/refresh tokens in the JSON body.
- Mobile login returns rotated access/refresh tokens in the JSON body and still sets cookies.
- Refresh tokens are DB-backed, rotated on refresh, and revoked on logout.
- Finn execute accepts server-issued `action_id` only; forged `{ action: ... }` payloads are rejected.
- Finn replay returns explicit `replayed = true`.
- Sensitive routes now enforce runtime rate limits:
  - `/api/assistant/actions/execute`
  - `/api/orders/manual`
  - `/api/orders/manual/preflight`

### Cleanup/consistency

- Notifications API no longer trusts `user_id` from request body for ownership.
- New API modules are guarded against sync `Session` / `.query()` patterns.
- Process-local dashboard, intelligence, and transition-risk caches are removed for write-sensitive paths.
- Old dashboard/intelligence cache env flags no longer enable per-process state.
- psycopg2 usage is explicitly allowlisted to legacy/background boundaries.
- Regime memory and daily report writes no longer call the legacy psycopg2 helper directly; they use SQLAlchemy repository boundaries.

### Replay/exactly-once

- Assistant pending action execution now atomically claims `pending -> executing` before side effects.
- Executed assistant actions persist `_execution_result`, allowing safe retry responses without repeating the action.
- Failed assistant action executions are marked `failed` with `_execution_error` context.
- Finn maintenance actions keep deterministic action ids and existing `ON CONFLICT (id) DO NOTHING` guards.
- Manual orders, live preflight tokens, bot decisions, snapshots, and reports are documented in `docs/operations/replay-exactly-once-inventory.md`.

## Remaining Risks

### V1 operations

- The default `celery` queue still contains a large legacy backlog.
- Continue bounded drain cycles and stop when the reroute ratio drops or default becomes mostly dispatcher/fallback work.
- Deep health may be slower while queue depth remains high; use component status and queue samples rather than raw depth alone.

### Legacy boundaries

- `PushService` is async-first; its sync compatibility method opens an async session and does not carry sync query logic.
- psycopg2 remains directly imported only in `backend/utils/db.py`; older background/scoring/reporting paths that still need sync access must go through an explicit boundary instead of importing the driver.
- Recently migrated off direct helper calls:
  - `backend/ai_core/regime_memory.py`
  - `backend/celery_task/daily_report_task.py`

### Scale tuning later

- Frontend polling and `no-store` read amplification have a broader pass complete across dashboard, admin logs, intelligence events, market price hooks, and report generation polling.
- Process-local read caches should remain opt-in unless moved to Redis/shared cache with explicit invalidation.
- Queue age/throughput metrics would make backlog health easier to interpret than depth alone.

### Enterprise later

- Deep end-to-end tracing per decision/order/report beyond the request `X-Trace-Id`.
- Admin search/report trace surfacing can be expanded further once QA decides which operator screens need trace-first filtering.
- Wider exactly-once semantics can still be expanded into provider/exchange replay protection if external exchange APIs expose stronger idempotency contracts.
- Security QA still has two non-blocking proofs to close:
  - browser user A -> user B cache/user-switch validation
  - hard no-write proof for market-data read routes beyond runtime/log indications

## Recommended Next Work

See also:

- [Tradamind Platform Hardening Plan](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-next-plan.md)
- [Platform Hardening Tranche A — Execution Safety](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-a-execution-safety.md)
- [Platform Hardening Tranche B — Queue Discipline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-b-queue-discipline.md)
- [Platform Hardening Tranche C — Async Session Correctness](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-c-async-session-correctness.md)

1. Finish the two remaining security QA proofs.
   - Browser user-switch cache check with a second onboarded account.
   - Harder no-write observability check for market-data read routes.
   - No new code is required unless one of those checks finds a regression.

2. Controlled legacy queue drain operations are active.
   - Use `docs/operations/legacy-celery-queue-drain.md`.
   - Save artifacts and compare `operator_summary`.
   - Stop based on `reroute_ratio_after` and `top_tasks_after`, not total backlog alone.
   - Latest controlled run processed `1500`, rerouted `1500`, kept `0`, then stopped on `max_processed_total_reached`.
   - Default queue was about `48714` after the follow-up health check; wait for named queues to visibly drain before another larger cycle.

3. Use queue age/throughput fields in deep health while draining.
   - `queue_metrics.<queue>.oldest_message_age_seconds` is available for newly published tasks stamped with `published_at`.
   - `queue_metrics.<queue>.timestamped_sample_size` shows how much of the sampled queue can be aged.
   - `queue_metrics.<queue>.estimated_drain_per_minute` is based on the previous health check in the current backend process.
   - Legacy messages without a publish timestamp intentionally report `age_source = unavailable`.

4. Continue with the remaining platform cleanup sequence.
   - psycopg2 legacy boundary migration/isolation is complete at the driver boundary: direct driver imports are centralized in `backend/utils/db.py`.
   - regime memory and daily report writes now use repository boundaries instead of direct `get_db_connection()` calls.
   - PushService sync DB cleanup is complete: PushService is async-first and the sync method is compatibility-only.
   - Frontend polling / `no-store` reduction is complete for the shared auth clients, dashboard scores hook, admin logs, intelligence events, market price hooks, and report generation polling.

5. Then return to product OS work.
   - Portfolio Risk 2.0 or Reports/Reflection 2.0 are now safer to build on top of this platform base.
   - The 8-step reliability remainder is now complete at V1 scope.

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
  backend/trading-tool-backend/backend/tests/test_frontend_cache_polling_policy.py
  backend/trading-tool-backend/backend/tests/test_frontend_polling_policy.py
  backend/trading-tool-backend/backend/tests/test_traceability_step5.py
  backend/trading-tool-backend/backend/tests/test_replay_exactly_once_step8.py
```

Live smoke:

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/system/health
curl -fsSI http://127.0.0.1:5002/report | head -n 1
```

Rollback helper smoke:

```bash
./rollback_live.sh <previous_good_commit>
```
