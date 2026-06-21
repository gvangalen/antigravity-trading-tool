# Platform Phase 2.1 AI-heavy Optimization Checklist

Last updated: 2026-06-06

## Why this exists

The Phase 2.1 capacity baseline now says pretty clearly:

- `bot-execution-heavy` is healthy and lightweight
- `read-heavy` is stable but somewhat expensive
- `ai-heavy` is the current throughput hotspot

This checklist keeps the next optimization pass narrow and evidence-driven.

## Current reference

Use these runs as the current baseline:

- initial AI-heavy run:
  - [/tmp/platform-phase2-1-capacity-ai-heavy-v1.json](/tmp/platform-phase2-1-capacity-ai-heavy-v1.json)
- confirm AI-heavy run:
  - [/tmp/platform-phase2-1-capacity-ai-heavy-v2.json](/tmp/platform-phase2-1-capacity-ai-heavy-v2.json)

Key numbers from the confirm run:

- `request_count = 8`
- `success_count = 8`
- `failure_count = 0`
- `avg_latency_ms = 13138.22`
- `p95_latency_ms = 30392.16`
- `max_latency_ms = 34103.99`

## P0 focus

### 1. Mission Control read path

Inspect:

- `/api/assistant/mission-control`
- the backend path that hydrates Mission Control summaries and related operator context

Goal:

- reduce the slowest read-heavy / AI-adjacent tail without changing lane ownership

### 2. Assistant-heavy context build

Inspect:

- assistant context assembly
- summary and read-only explain paths
- any expensive cross-repository aggregation in the assistant layer

Goal:

- reduce repeated heavy reads
- avoid unnecessary context hydration when a lighter read-only answer is enough

### 3. Daily report preview path

Inspect:

- `/api/report/daily/preview`
- report preview data collection and summarization steps

Goal:

- keep the preview useful, but cheaper

## P1 focus

### 1. Queue interaction under AI-heavy traffic

Watch:

- broker/deep-health degradation during AI-heavy runs
- whether AI-heavy traffic is correlating with named-queue lag or inspect timeouts

### 2. Worker topology reconsideration

Do not change this first.

Only revisit worker concurrency after:

- path-level slimming is attempted
- one more AI-heavy confirm run is measured

## Guardrails

- no route ownership changes as part of this optimization pass
- no product-surface rewrites
- no execute-path broadening
- keep deep-health interpretation honest:
  - distinguish runtime slowness from broker inspection noise

## Definition of a good next result

The next AI-heavy run should ideally show:

- `success_count` still clean
- lower `avg_latency_ms`
- lower `p95_latency_ms`
- less overlap with temporary `broker` degradation in health snapshots

## Follow-up artifact

After the optimization pass:

1. rerun `ai-heavy`
2. update [Platform Phase 2.1 Capacity Baseline](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/platform-phase-2-1-capacity-baseline.md)
3. decide whether worker concurrency tuning is still needed
