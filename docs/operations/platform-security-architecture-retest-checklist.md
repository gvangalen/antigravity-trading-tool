# Platform Security & Architecture Retest Checklist

Last updated: 2026-06-06

This checklist is the fastest clean rerun path for the security agent and the system architect agent after the latest live baseline:

- `production_head = 2f56033`
- `LAST_GOOD_COMMIT = 2f56033`

Use this document to keep both reruns anchored to the same runtime truth, smoke state, and test scope.

## Before Either Agent Runs

Confirm these first:

1. live commit markers
   - host `HEAD = 2f56033`
   - `ops/deploy/production/LAST_GOOD_COMMIT = 2f56033`

2. health and reachability
   - external `/api/health` -> `200`
   - external `/report` -> `200`
   - external `/api/system/health` -> `401` as expected
   - internal `/api/system/health` may be `degraded` if broker/Celery inspection is noisy, but it must not be `down` or `error`

3. runtime expectations
   - frontend security stack is on `next@15.5.19`
   - `npm audit` on the frontend is `0 vulnerabilities`
   - web auth is cookie + CSRF protected
   - Finn action execution is `action_id` only

If any of those are false, stop and re-check the deployment state before scoring the platform.

## Security Agent Retest

### Primary Questions

The security agent should explicitly re-check:

1. auth/session hardening
2. CSRF enforcement on web cookie flows
3. Finn action authorization and replay behavior
4. cache/logout/user-switch safety
5. public/operator endpoint exposure
6. remaining dependency/security debt after the frontend upgrade

### Must-Verify Behaviors

#### Auth and session

- web login must not return access/refresh tokens in the JSON body
- mobile login may still return body tokens
- logout must invalidate refresh tokens
- refresh rotation must reject re-use of old refresh tokens
- unsafe web API methods without matching CSRF header must be rejected

#### Finn action safety

- crafted `POST /api/assistant/actions/execute` with raw `{ "action": ... }` must fail
- valid execution with server-issued `{ "action_id": ... }` must succeed
- replaying the same execute call must return `replayed = true` without a duplicate side effect

#### Endpoint exposure

- external `/api/system/health` must remain unauthorized
- authenticated internal/operator path may expose deep health
- public report token handling must not log raw token fragments

#### Client/cache safety

- logout + refresh failure must clear stale local user/token state
- authenticated API responses must not be served from the old PWA service-worker cache path
- user A data must not reappear for user B after logout/login switch on web

#### Dependency state

Run at minimum:

```bash
cd /Users/gvangalen/Documents/antigravity-trading-tool/frontend/trading-tool-frontend
npm audit --json
npm run build
```

Expected:

- `npm audit`: `0 vulnerabilities`
- build: pass

### Recommended Regression Slice

```bash
cd /Users/gvangalen/Documents/antigravity-trading-tool
pytest -q \
  backend/trading-tool-backend/backend/tests/test_security_phase8.py \
  backend/trading-tool-backend/backend/tests/test_security_phase9.py \
  backend/trading-tool-backend/backend/tests/test_security_phase10.py
```

## System Architect Agent Retest

### Primary Questions

The architect rerun should now focus on:

1. whether V1 correctness is still green
2. whether Phase 2 observability remains coherent
3. whether the current bottleneck has moved from correctness to throughput/cluster operations
4. whether runtime truth and repo truth are aligned

### What Should Already Be True

- queue discipline remains in place:
  - named queues
  - backlog-aware dispatcher
  - per-wave lease semantics
  - per-user window dedupe
- execution safety remains in place:
  - replay guards
  - idempotent assistant action execution
  - bot execution duplicate protection
- request-path correctness remains in place:
  - no shared-session `asyncio.gather()` misuse in guarded paths
  - read-only GET behavior for market-data read routes
- security hardening is now part of the platform baseline:
  - cookie CSRF
  - corrected auth contracts
  - operator-only deep health
  - upgraded frontend dependency stack

### What the Architect Agent Should Treat as Open

These are still fair game for critique:

- cluster-wide observability is still a follow-up, not fully solved
- deep health counters are still process-lifetime, not distributed truth
- queue backlog on named queues is still operational noise
- worker throughput/capacity should still be treated as a scale question
- rollout/deep-health noise around broker/Celery should still be watched

### Recommended Regression Slice

```bash
cd /Users/gvangalen/Documents/antigravity-trading-tool
pytest -q \
  backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py \
  backend/trading-tool-backend/backend/tests/test_celery_dispatcher.py \
  backend/trading-tool-backend/backend/tests/test_celery_queue_policy.py \
  backend/trading-tool-backend/backend/tests/test_system_health_service.py \
  backend/trading-tool-backend/backend/tests/test_platform_hardening.py \
  backend/trading-tool-backend/backend/tests/test_runtime_reliability_hardening.py \
  backend/trading-tool-backend/backend/tests/test_platform_phase2_scale_observability.py \
  backend/trading-tool-backend/backend/tests/test_frontend_cache_polling_policy.py \
  backend/trading-tool-backend/backend/tests/test_platform_hardening_docs_status.py
```

### Optional Full Acceptance Slice

```bash
cd /Users/gvangalen/Documents/antigravity-trading-tool
pytest -q \
  backend/trading-tool-backend/backend/tests/test_security_phase1.py \
  backend/trading-tool-backend/backend/tests/test_security_phase3.py \
  backend/trading-tool-backend/backend/tests/test_security_phase7.py \
  backend/trading-tool-backend/backend/tests/test_security_phase8.py \
  backend/trading-tool-backend/backend/tests/test_security_phase9.py \
  backend/trading-tool-backend/backend/tests/test_security_phase10.py \
  backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py \
  backend/trading-tool-backend/backend/tests/test_celery_dispatcher.py \
  backend/trading-tool-backend/backend/tests/test_celery_queue_policy.py \
  backend/trading-tool-backend/backend/tests/test_system_health_service.py \
  backend/trading-tool-backend/backend/tests/test_platform_hardening.py \
  backend/trading-tool-backend/backend/tests/test_runtime_reliability_hardening.py \
  backend/trading-tool-backend/backend/tests/test_frontend_cache_polling_policy.py \
  backend/trading-tool-backend/backend/tests/test_platform_phase2_scale_observability.py \
  backend/trading-tool-backend/backend/tests/test_platform_hardening_docs_status.py
```

## Reporting Format

Ask both agents to report back in this shape:

1. runtime/repo baseline used
2. suites or probes run
3. pass/fail counts
4. critical findings only
5. high-risk findings only
6. what is genuinely fixed since the previous review
7. what is still open but belongs to scale/operations rather than correctness

## Current Expected Baseline

If the reruns are clean, the expected reading should roughly be:

- security: no remaining V1-critical auth/session/action-authorization gap
- architecture: V1 hardening green, with open work shifted to:
  - cluster observability
  - throughput validation
  - queue backlog reduction
  - multi-instance rollout discipline

