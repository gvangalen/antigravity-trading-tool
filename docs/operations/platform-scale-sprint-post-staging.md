# Tradamind Platform Scale Sprint

Last updated: 2026-06-08

## Current Status

Environments:

- local: green
- staging HTTPS: green
- production HTTPS: green

Separation:

- separate database per environment: green
- separate Redis / queue lane per environment: green
- separate deploy lane per environment: green

FINN status:

- Core: `89`
- Operator: `82`
- Performance Intelligence: `91`
- Governance: `91`

Current reading:

- FINN is no longer the primary bottleneck
- the next limiting factor is platform scale and operations discipline

## Sprint Goal

Prepare Tradamind for:

- real users
- stable releases
- higher load
- measurable infrastructure
- a safe path toward `500-1000` active users

This sprint is intentionally not a FINN feature sprint.

## Scope

### In scope

- worker throughput
- queue observability
- staging load validation
- read amplification reduction
- release discipline
- monitoring inventory
- real user usage measurement prep

### Out of scope

- FINN 6.0
- new AI agents
- new large FINN feature layers
- new execution automation

## P0 — Platform Scale

### 1. Worker Throughput

Investigate:

- current Celery concurrency
- queue occupancy
- queue lag

Actions:

- evaluate concurrency per queue class
- test safe increases on staging only
- measure impact before changing production

Success:

- no queue accumulation during staging runs
- stable worker behavior under mixed load

Current topology source:

- [ops/deploy/ecosystem.shared.js](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/ecosystem.shared.js)

### 2. Queue Observability

Track:

- queue lag
- retry metrics
- dedupe metrics
- replay block metrics
- task duration metrics

Success:

- bottlenecks are visible without log spelunking

Current observability sources:

- [backend/trading-tool-backend/backend/services/system_health_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/system_health_service.py)
- [backend/trading-tool-backend/backend/services/platform_metrics.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/platform_metrics.py)

### 3. Load Testing

First realistic scenario:

- `80%` dashboard/read users
- `15%` FINN users
- `5%` bot/governance-preview users

Rollout sequence:

1. `100` active users
2. `250` active users
3. `500` active users

Measure:

- API latency
- DB load
- Redis load
- queue lag
- worker utilization

Harness:

- [Platform Phase 2.1 Capacity Harness](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-capacity-harness.md)

Current measured outcome:

- `100` mixed staging users: stable
- `250` mixed staging users: stable
- `500` mixed staging users: stable
- remaining non-`200` traffic is dominated by expected `429` policy hits on AI/governance chat, not by broker, queue, or worker instability

### 4. Read Amplification

Inspect:

- polling frequencies
- `no-store` usage
- safely cacheable endpoints

Goal:

- reduce unnecessary backend pressure
- preserve perceived freshness

## P1 — Production Discipline

### Release Flow

Mandatory flow:

1. Local
2. Staging
3. Core QA
4. Operator QA
5. Performance QA
6. Governance QA
7. Production

Direct-to-production deploys are out of policy.

### Monitoring Inventory

Inventory and tighten:

- uptime monitoring
- error monitoring
- queue monitoring
- database monitoring

## P2 — Real User Signals

Measure:

- most-used FINN prompts
- most-used screens
- Decision Review usage
- Priority Engine usage
- repeat users

Goal:

- learn from real user behavior instead of only QA traffic

## Immediate Next Tranche — P0.1 Staging Scale Baseline

This is the next concrete build/run step.

Deliverables:

1. current worker topology snapshot
2. current queue/Redis/DB baseline snapshot
3. mixed staging load scenario for `100` active users
4. first measured staging results
5. concurrency recommendation before touching production

Current status:

- completed
- see [Platform Scale P0.1 — Staging Baseline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-scale-staging-baseline.md)

## Next Focus After The Baseline

With the `100 -> 250 -> 500` staging baseline now recorded, the next priority is no longer more synthetic scale escalation.

The better next work is:

1. FINN/product-quality improvements
2. platform polish where users will feel it directly
3. instrumentation for real user behavior

In practice this means:

- continue FINN iteration from a stronger platform footing
- tighten read amplification only where real usage shows it matters
- collect real user prompt/screen/returning-user patterns before the next scale jump

Operator runbook:

- [Platform Scale P0.1 — Staging Baseline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-scale-staging-baseline.md)
