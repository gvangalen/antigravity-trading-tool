# Platform Phase 2.1 — Cluster Observability & Capacity Validation

Last updated: 2026-06-06

## Goal

Take Tradamind from:

- V1-correct
- Phase 2 process-observable

to:

- cluster-observable
- throughput-validated
- easier to operate under real multi-user pressure

This is not a correctness rescue slice.
This is the first scale-proof slice after the A–F hardening track and the initial Phase 2 observability pass.

## Why This Phase Exists

What is already true:

- request-path correctness is much stronger
- replay/duplicate safety is materially better
- queue routing and worker topology are more intentional
- deep health already surfaces queue, rate-limit, replay, retry, dedupe, and latency signals

What is still missing:

- those signals are still mostly **process-lifetime** and **instance-local**
- worker concurrency is configured, but not yet proven under controlled load profiles
- the legacy queue backlog still adds operational noise
- operators still need clearer runtime-vs-repo truth during deploys

## Objectives

### 1. Cluster-aware observability

Move beyond single-process hints.

Target outcomes:

- queue lag is visible across the cluster, not only per process
- retry volume is attributable by task family and instance
- replay/duplicate guard hits are aggregated across workers
- dedupe skip behavior is measurable across dispatcher instances
- latency percentiles are distinguishable per process and per environment

### 2. Capacity validation

Prove the current worker topology under realistic profiles.

Target outcomes:

- queue-specific concurrency is validated under:
  - read-heavy users
  - AI-heavy users
  - bot/execution-heavy users
- queue lag growth and drain curves are measured
- operator guidance exists for safe concurrency increases

### 3. Runtime truth discipline

Keep deployment and docs operationally unambiguous.

Target outcomes:

- `repo_head`, `production_head`, and `LAST_GOOD_COMMIT` are explicitly updated after each production rollout
- statusdocs cannot lag multiple deploys behind without a visible mismatch
- generated frontend artifacts remain documented as build output, not contract truth

## Scope

### In scope

- deep-health output enrichment for cluster-oriented interpretation
- deploy/status docs alignment
- load-profile playbooks and measurement runs
- queue lag / retry / replay / dedupe visibility improvements
- worker topology validation

### Out of scope

- broad new product features
- Redis/shared response caching rollout
- autoscaling
- a full async migration of every legacy background path
- enterprise-grade distributed tracing infrastructure

## Workstreams

### Workstream A — Cluster Metrics Bridge

Primary goal:
make current observability less process-myopic.

Current status:

- first bridge slice is now in code on `main`
- `/api/system/health` now exposes:
  - `runtime_identity`
  - `observability_scope`
  - `cluster_observability`
- queue metrics now label their source for:
  - depth
  - worker mapping
  - rate limits

Likely touchpoints:

- [backend/trading-tool-backend/backend/services/system_health_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/system_health_service.py)
- [backend/trading-tool-backend/backend/services/platform_metrics.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/platform_metrics.py)
- [backend/trading-tool-backend/backend/celery_task/celery_app.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/celery_app.py)
- [backend/trading-tool-backend/backend/celery_task/dispatcher.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/dispatcher.py)

Acceptance:

- deep health distinguishes clearly between:
  - process-lifetime counters
  - queue/broker truth
  - cluster-interpretation limits
- operator-facing payload includes enough metadata to compare multiple instances safely

### Workstream B — Capacity Validation

Primary goal:
measure the current topology instead of assuming it is enough.

Current status:

- the first safe capacity harness is now in repo:
  - [Platform Phase 2.1 Capacity Harness](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-capacity-harness.md)
- the first post-staging scale sprint baseline is now tracked in:
  - [Platform Scale P0.1 — Staging Baseline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-scale-staging-baseline.md)
- the first baseline runs are also now recorded in:
  - [Platform Phase 2.1 Capacity Baseline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-capacity-baseline.md)
- the next narrow follow-up is tracked in:
  - [Platform Phase 2.1 AI-heavy Optimization Checklist](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-ai-heavy-optimization-checklist.md)
- it is intentionally read-first:
  - no execute endpoints
  - no report generation endpoints
  - optional manual-order preview only with an explicit fixture

Profiles:

1. read-heavy dashboard/report traffic
2. AI-heavy assistant/report traffic
3. bot/execution-heavy workflow traffic
4. mixed-load staging traffic using `80/15/5` distribution

Acceptance:

- queue lag is measured before, during, and after each profile
- p50/p95 latency and retry volume are captured
- one recommended safe concurrency profile is documented per worker class

### Workstream C — Runtime Truth & Docs Discipline

Primary goal:
remove ambiguity between repo and production state.

Likely touchpoints:

- [docs/operations/platform-hardening-status.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-status.md)
- [docs/operations/platform-hardening-next-plan.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-next-plan.md)
- [docs/operations/platform-hardening-tranche-f-deploy-stability.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-hardening-tranche-f-deploy-stability.md)

Acceptance:

- docs explicitly state the live production commit for the latest validated rollout
- deploy markers and docs can be reconciled in one short operator check
- stale generated frontend artifacts remain excluded from contract authority

## Suggested Sequence

1. Workstream C — Runtime Truth & Docs Discipline
2. Workstream A — Cluster Metrics Bridge
3. Workstream B — Capacity Validation
4. rerun architect/reliability review

## Definition Of Done

This phase is meaningfully done when:

- operators can explain queue/retry/replay behavior across instances, not just one process
- worker concurrency has been validated under at least three realistic load profiles
- repo/docs/runtime commit truth is explicitly aligned after rollout
- the next architect review finds scale questions, not observability blind spots
