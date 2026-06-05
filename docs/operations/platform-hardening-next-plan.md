# Tradamind Platform Hardening Plan

Last updated: 2026-06-04

## Purpose

This document turns the latest architecture review into a concrete platform hardening sequence.

The goal is not to broaden product scope.
The goal is to finish the reliability, concurrency, queue, and operations layer that determines whether Tradamind remains trustworthy under higher load.

This plan starts from an important truth:

- FINN product layers are now materially stronger
- the next major quality gains are more platform-oriented than feature-oriented

## Current Reading

What is already stronger than before:

- runtime schema mutation is out of app startup and in versioned migrations
- queue routing is split into named workload classes
- `conversation_state` uses UPSERT
- AI usage counters are atomically updated
- AI cache keys are context-aware
- mobile overview no longer shares one `AsyncSession` across parallel DB awaits
- notifications are ownership-safe
- deploy flow now has explicit migrations, health checks, and rollback markers

What still matters most before higher scale:

1. queue and dispatcher discipline
2. generated execution idempotency
3. async/session correctness across all read paths
4. retry semantics that currently risk absorbing failures
5. deploy-path consolidation
6. queue naming consistency between staging and production
7. symbol-aware state cleanup in older portfolio models

## Priority Order

### P0 — Execution Safety

This is the highest-risk work.

Why first:

- duplicate execution mistakes are more dangerous than stale reads
- retry + overlap issues become expensive fastest in execution paths
- this work improves both safety and operational predictability

Target outcomes:

- bot-generated execution becomes duplicate-safe at the DB boundary
- status transitions become overlap-safe
- retries become safe by construction

### P0 — Queue Discipline

This is the second major scaling risk.

Why next:

- per-cycle fan-out without backlog-awareness will drift under growth
- queue separation helps only if dispatch remains bounded and deduped

Target outcomes:

- dispatch no longer blindly enqueues every active user every cycle
- overlap per `(workflow, user, window)` is blocked
- producers and consumers always agree on queue naming

### P0 — Async Session Correctness

This is the third major correctness risk.

Why next:

- shared `AsyncSession` plus `asyncio.gather()` remains a known failure mode
- mobile overview was fixed, but dashboard/read paths still need a complete pass

Target outcomes:

- no request path concurrently uses one shared `AsyncSession`
- parallelism, where still needed, uses isolated session boundaries

## P1 — Operations Consolidation

Focus:

- one real deploy route
- legacy deploy scripts retired or explicitly blocked
- worker topology described in one source of truth

Target outcomes:

- no operational drift between “old deploy” and “new deploy”
- staging and production process naming stays aligned

## P1 — Symbol/State Model Cleanup

Focus:

- older single-asset assumptions in portfolio/state tables
- bot portfolio records and dependent state models

Target outcomes:

- no hidden BTC-default or single-symbol collapse in broader portfolio logic
- cleaner path to multi-asset scaling

## P2 — Read Amplification Strategy

Focus:

- selective shared caching for read-heavy but non-execution-critical endpoints
- lower polling cost without sacrificing correctness

Target outcomes:

- lower backend read amplification
- clearer freshness policy per endpoint class

## Workstreams

## Workstream A — Execution Safety

Primary files and likely touchpoints:

- [backend/trading-tool-backend/backend/api/bot_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/bot_api.py)
- [backend/trading-tool-backend/backend/services/bot_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/bot_service.py)
- [backend/trading-tool-backend/backend/services/ai_action_engine.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_action_engine.py)
- [backend/trading-tool-backend/backend/infrastructure/models.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/models.py)
- [backend/trading-tool-backend/backend/infrastructure/repositories/bot_repository.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/repositories/bot_repository.py)
- [backend/trading-tool-backend/backend/celery_task/trading_bot_task.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/trading_bot_task.py)

Acceptance:

- duplicate bot-generated execution is blocked at DB level
- replay/retry cannot create extra live/order/ledger side effects
- status transitions are explicitly serialized

## Workstream B — Queue Discipline

Primary files and likely touchpoints:

- [backend/trading-tool-backend/backend/celery_task/dispatcher.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/dispatcher.py)
- [backend/trading-tool-backend/backend/celery_task/celery_app.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/celery_app.py)
- [backend/trading-tool-backend/backend/services/system_health_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/system_health_service.py)
- [ops/deploy/deploy_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/deploy_env.sh)
- [ops/deploy/ecosystem.shared.js](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/ecosystem.shared.js)

Acceptance:

- dispatcher is backlog-aware
- duplicate enqueues for same user/workflow window are prevented
- staging/production queue names are consistent end to end

Current implementation note:

- first backlog-aware + overlap-safe dispatcher slice is now built locally in
  [Platform Hardening Tranche B — Queue Discipline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-b-queue-discipline.md)

## Workstream C — Async Session Correctness

Primary files and likely touchpoints:

- [backend/trading-tool-backend/backend/services/dashboard_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/dashboard_service.py)
- [backend/trading-tool-backend/backend/services/ai_assistant_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_assistant_service.py)
- [backend/trading-tool-backend/backend/infrastructure/repositories/assistant_context_repository.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/repositories/assistant_context_repository.py)

Acceptance:

- no shared `AsyncSession` is awaited concurrently
- known dashboard and assistant read paths are explicitly safe under load

## Workstream D — Operations Consolidation

Primary files and likely touchpoints:

- [deploy_live.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy_live.sh)
- [deploy_staging.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy_staging.sh)
- [rollback_live.sh](/Users/gvangalen/Documents/antigravity-trading-tool/rollback_live.sh)
- [ops/deploy/deploy_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/deploy_env.sh)
- [ops/deploy/rollback_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/rollback_env.sh)
- [ecosystem.config.js](/Users/gvangalen/Documents/antigravity-trading-tool/ecosystem.config.js)
- [ecosystem.production.config.js](/Users/gvangalen/Documents/antigravity-trading-tool/ecosystem.production.config.js)
- [ecosystem.staging.config.js](/Users/gvangalen/Documents/antigravity-trading-tool/ecosystem.staging.config.js)

Acceptance:

- one supported deployment route per environment
- legacy operator traps are removed from normal deploy flow

## What Not To Do In This Phase

Do not:

- add a new FINN major phase as a substitute for platform work
- widen autonomous execution before duplicate safety is stronger
- add more queue classes before dispatch overlap is controlled
- introduce new local caches for correctness-sensitive reads

## Recommended Sequence

1. Workstream A — Execution Safety
2. Workstream B — Queue Discipline
3. Workstream C — Async Session Correctness
4. Workstream D — Operations Consolidation
5. rerun platform hardening QA and live smoke

## Definition Of Done

This hardening plan is meaningfully done when:

- duplicate bot-generated execution is DB-safe
- retries do not silently mask failures
- dashboard and assistant read paths are async-safe
- dispatcher is overlap-safe and backlog-aware
- staging and production queue naming is consistent
- deploy operations have one clear supported path

## Immediate Next Step

Start with:

- [Platform Hardening Tranche A — Execution Safety](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-a-execution-safety.md)

Reason:

- this is the highest ROI safety work
- it reduces the most expensive class of failures first
- it improves both product trust and scale readiness
