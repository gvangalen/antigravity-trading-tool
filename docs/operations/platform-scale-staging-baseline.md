# Platform Scale P0.1 — Staging Baseline

Last updated: 2026-06-08

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
- paced FINN/governance requests to avoid measuring only rate-limit collisions

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
  --mixed-ai-think-time-seconds 2.5 \
  --mixed-bot-think-time-seconds 3.0 \
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

## Measured Baseline Results

### 100-user mixed run — cleaned baseline

Artifacts:

- `/tmp/platform-scale-staging-mixed-100-v3.json`
- `/tmp/platform-scale-staging-mixed-100-v3.md`

Result:

- requests: `480`
- success: `440`
- failures: `40`
- avg latency: `426.62 ms`
- p95 latency: `1084.76 ms`
- max latency: `1686.66 ms`

Operational reading:

- health stayed `ok` before, during, and after
- broker stayed `ok`
- celery stayed `ok`
- total queue depth stayed `0`
- remaining failures were `429` guardrails on AI/governance chat paths

### 250-user mixed run

Artifacts:

- `/tmp/platform-scale-staging-mixed-250-v1.json`
- `/tmp/platform-scale-staging-mixed-250-v1.md`

Result:

- requests: `1200`
- success: `1070`
- failures: `130`
- avg latency: `507.24 ms`
- p95 latency: `1073.24 ms`
- max latency: `1800.91 ms`

Operational reading:

- health stayed `ok` before, during, and after
- broker stayed `ok`
- celery stayed `ok`
- total queue depth stayed `0`
- failures remained limited to `429` policy hits on AI/governance chat

### 500-user mixed run

Artifacts:

- `/tmp/platform-scale-staging-mixed-500-v1.json`
- `/tmp/platform-scale-staging-mixed-500-v1.md`

Result:

- requests: `2400`
- success: `2120`
- failures: `280`
- avg latency: `502.96 ms`
- p95 latency: `1008.92 ms`
- max latency: `1971.81 ms`

Operational reading:

- health stayed `ok` before, during, and after
- broker stayed `ok`
- celery stayed `ok`
- total queue depth stayed `0`
- failures again remained `429` guardrails, not queue collapse or backend faults

## Conclusion

The staging platform now has a meaningful mixed-load proof point through `500` virtual users.

What this does mean:

- mixed read + FINN + governance-preview traffic remains operationally stable
- queue lanes do not accumulate under this staged load
- broker and worker topology remain readable under pressure

What this does not mean:

- unlimited FINN chat concurrency is supported
- AI/governance rate limits should be read as platform failures

Current interpretation:

- the platform bottleneck is no longer queue throughput at this stage
- the visible guardrail is AI/governance rate limiting by policy
- this is sufficient to pause further synthetic scale escalation for now
- the next highest-value work moves back toward FINN/product quality and real user signals

## Not Part Of This Tranche

- no production concurrency changes
- no new AI features
- no FINN 6.0 work
- no execution automation changes

## Follow-up Decision

After the staged `100 -> 250 -> 500` sequence, the current recommendation is:

1. keep current worker concurrency as-is for now
2. treat current `429` AI/governance responses as expected guardrails
3. return to FINN/product-quality work and real-user instrumentation before any larger synthetic scale jump
