# Platform Scale P0.1 — Staging Baseline

Last updated: 2026-06-07

## Goal

Create the first measurable staging baseline before any production throughput tuning.

This tranche is intentionally staged as:

1. observe
2. run safe mixed load
3. inspect queue/worker behavior
4. only then tune concurrency

## Current Staging Baseline

Environment:

- URL: [https://staging.tradamind.com](https://staging.tradamind.com)
- backend health: `/api/health`
- operator health: `/api/system/health`

Worker topology source:

- [ops/deploy/ecosystem.shared.js](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/ecosystem.shared.js)

Current queue-class concurrency:

- `celery-worker-default`: `2`
- `celery-worker-market-portfolio`: `2`
- `celery-worker-scoring-execution`: `2`
- `celery-worker-ai-reporting`: `1`
- `celery-beat`: unchanged

## Pre-Run Checks

Before any mixed run:

1. confirm staging deploy is green
2. confirm `/api/health = 200`
3. confirm `/api/system/health = 401` externally and reachable with operator auth
4. save a baseline `/api/system/health` payload
5. note Redis queue depths before traffic

## First Mixed Scenario

Traffic mix:

- `80%` read-heavy
- `15%` ai-heavy
- `5%` bot-execution-heavy

First target:

- `100` virtual users
- `1` iteration per user
- `20` request concurrency cap

Harness command:

```bash
export TT_USER_PASSWORD="<password>"
export TT_HEALTH_BEARER_TOKEN="<operator-token>"

python3 /Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/run_platform_capacity_profiles.py \
  --base-url https://staging.tradamind.com \
  --login-email "<email>" \
  --password-env TT_USER_PASSWORD \
  --health-url https://staging.tradamind.com/api/system/health \
  --health-bearer-token-env TT_HEALTH_BEARER_TOKEN \
  --profiles mixed-load \
  --virtual-users 100 \
  --iterations-per-user 1 \
  --read-share 80 \
  --ai-share 15 \
  --bot-share 5 \
  --mixed-concurrency 20 \
  --output-json /tmp/platform-scale-staging-mixed-100.json \
  --output-md /tmp/platform-scale-staging-mixed-100.md
```

## What To Record

For each run, capture:

- avg / p95 / max latency
- request success/failure counts
- queue lag before/during/after
- retry counters
- replay block counters
- dedupe counters
- visible workers
- degraded deep-health components

## Promotion Criteria

Move from `100` to `250` only if:

- no request failures beyond transient auth noise
- no runaway queue accumulation
- no broker `down`
- no worker disappearance
- no severe latency regression that makes the run non-informative

Move from `250` to `500` only if the `250` run remains operationally readable.

## Not Part Of This Tranche

- no production concurrency changes
- no new AI features
- no FINN 6.0 work
- no execution automation changes

## Follow-up Decision

After the first `100`-user run, decide one of:

1. keep current concurrency and move to `250`
2. raise one queue-class carefully on staging
3. slim read amplification before scaling load further

