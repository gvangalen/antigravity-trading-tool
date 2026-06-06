# Platform Hardening Tranche F — Deploy Stability

Last updated: 2026-06-06

## Goal

Make deploy and rollback flows less sensitive to the recurring host pattern where:

- PM2 reports `online`
- backend has not bound to `:8000` yet
- or a stale git remote ref blocks an otherwise valid rollout

## What Changed

Originally implemented on production commit `404b4ec`, then extended again on June 6, 2026 by commit `52fbc52`:

- deploy flow now tracks an explicit `BACKEND_APP` per environment
- deploy flow waits for both:
  - backend port bind
  - backend `/api/health`
- if backend startup drifts, deploy now does a backend-only PM2 rescue restart
  before giving up
- deep health now retries across temporary broker/startup instability instead of rolling back on the first timeout
- rollback now clears stale git remote refs before `git fetch`
- rollback now uses the same backend bind + health stabilization logic

## Primary Touchpoints

- [ops/deploy/deploy_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/deploy_env.sh)
- [ops/deploy/rollback_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/rollback_env.sh)
- [backend/trading-tool-backend/backend/tests/test_enterprise_hardening_step6.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_enterprise_hardening_step6.py)
- [backend/trading-tool-backend/backend/tests/test_runtime_reliability_hardening.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_runtime_reliability_hardening.py)

## Acceptance Read

This tranche is ready when:

- deploy does not treat PM2 `online` as sufficient by itself
- backend bind drift can self-heal through one backend-only restart
- rollback is less likely to fail on stale `origin/*` ref locks

## Live Outcome

Confirmed after rollout:

- host `HEAD=52fbc52`
- host `LAST_GOOD_COMMIT=52fbc52`
- external `/api/health` returned `200`
- external `/report` returned `200`
- external `/api/system/health` returned `401` as expected

Operational note:

- this host still shows rollout jitter, especially while backend bind, Redis responsiveness, and Celery inspect are settling
- the June 6, 2026 deploy path is much less trigger-happy now: it can wait through temporary broker/deep-health noise instead of immediately rolling back a good build
