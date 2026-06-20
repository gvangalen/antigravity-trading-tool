# Tradamind Platform Hardening Plan

Last updated: 2026-06-08

## Purpose

This document turns the latest architecture review into a concrete platform hardening sequence.

The goal is not to broaden product scope.
The goal is to finish the reliability, concurrency, queue, and operations layer that determines whether Tradamind remains trustworthy under higher load.

This plan starts from an important truth:

- FINN product layers are now materially stronger
- the next major quality gains are more platform-oriented than feature-oriented
- the next tranche is now scale/ops optimization rather than correctness rescue

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

Current implementation note:

- first symbol-scoped portfolio state slice is now built locally in
  [Platform Hardening Tranche E — Symbol/State Cleanup](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-e-symbol-state-cleanup.md)

## P2 — Read Amplification Strategy

Focus:

- selective shared caching for read-heavy but non-execution-critical endpoints
- lower polling cost without sacrificing correctness

Target outcomes:

- lower backend read amplification
- clearer freshness policy per endpoint class

## Phase 2 — Scale & Observability

Current implementation focus:

1. queue-specific worker concurrency instead of one global worker setting
2. deep-health process-lifetime counters for retry/replay/dedupe/latency
3. source-vs-generated artifact hygiene in frontend contract review
4. visibility-aware single-flight polling on read-heavy frontend surfaces
5. explicit containment of remaining legacy sync DB boundaries

Next operating sprint after the staging HTTPS milestone:

- [Tradamind Platform Scale Sprint](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-scale-sprint-post-staging.md)
- immediate execution tranche:
  - [Platform Scale P0.1 — Staging Baseline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-scale-staging-baseline.md)

Current sprint outcome:

- the staging scale baseline has now been executed through `100`, `250`, and `500` mixed virtual users
- staging remained operationally stable during those runs
- visible failures were dominated by expected `429` AI/governance guardrails rather than queue or broker instability
- this shifts the next priority back toward FINN/product quality and real-user signal collection instead of immediate further synthetic scale escalation

Active product follow-up:

- [Tradamind FINN Product Sprint 1](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-product-sprint-1.md)
- [Testing Blind Spots And Improvement Plan](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/testing-blind-spots-and-improvement-plan.md)
- [Overview And Market Performance Plan](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/overview-market-performance-long-term-plan.md)

Current implementation note:

- the first Phase 2 scale/observability slice is now live on production commit `52fbc52`
- deploy stability now tolerates temporary broker/deep-health startup noise instead of rolling back on the first timeout

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

Current implementation note:

- first shared-session cleanup slice is now built locally in
  [Platform Hardening Tranche C — Async Session Correctness](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-c-async-session-correctness.md)

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

Current implementation note:

- first deploy-path consolidation slice is now built locally in
  [Platform Hardening Tranche D — Operations Consolidation](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-d-operations-consolidation.md)

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
5. Tranche F — Deploy Stability
6. rerun platform hardening QA and live smoke

Current state:

- Tranches A through F are now built
- Tranches D, E, and F are live on production
- the main remaining operational irritant is host startup jitter, not missing hardening slices
- security hardening is now green at V1 scope instead of waiting on extra manual proof notes
- the first Phase 2 scale/observability slice is live at `52fbc52`

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

- [Platform Phase 2.1 — Cluster Observability & Capacity Validation](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-cluster-observability-capacity.md)
- first bridge slice now landed on `main` with `runtime_identity`, `observability_scope`, and `cluster_observability` in deep health
- first profile runs now captured in [Platform Phase 2.1 Capacity Baseline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-capacity-baseline.md)
- the next narrow optimization target is now captured in [Platform Phase 2.1 AI-heavy Optimization Checklist](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-ai-heavy-optimization-checklist.md)

Reason:

- the remaining risk is now cluster-scale behavior, not missing safety invariants
- current process-lifetime counters are useful operator hints but not distributed truth
- the next meaningful proof is measured throughput and observability under load
