# Platform Hardening Tranche D — Operations Consolidation

Last updated: 2026-06-05

## Goal

Reduce operational drift by keeping one supported deploy and rollback path per
environment.

This tranche focuses on two specific problems:

- environment deploys were still carrying mixed PM2 config assumptions
- a legacy `deploy.sh` path still existed with old behavior that could bypass
  the safer deploy flow

## What Changed

Implemented in the current working tree:

- production deploys now resolve explicitly to
  `ecosystem.production.config.js`
- staging deploys continue to resolve explicitly to
  `ecosystem.staging.config.js`
- rollback no longer falls back to a generic ecosystem file
- missing PM2 config is now a hard deploy/rollback failure instead of a silent
  fallback
- legacy [deploy.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy.sh)
  is now an explicit blocked shim that points operators to:
  - [deploy_live.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy_live.sh)
  - [deploy_staging.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy_staging.sh)
  - [ops/deploy/deploy_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/deploy_env.sh)

## Primary Touchpoints

- [deploy.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy.sh)
- [deploy_live.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy_live.sh)
- [deploy_staging.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy_staging.sh)
- [rollback_live.sh](/Users/gvangalen/Documents/antigravity-trading-tool/rollback_live.sh)
- [rollback_staging.sh](/Users/gvangalen/Documents/antigravity-trading-tool/rollback_staging.sh)
- [ops/deploy/deploy_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/deploy_env.sh)
- [ops/deploy/rollback_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/rollback_env.sh)
- [ecosystem.production.config.js](/Users/gvangalen/Documents/antigravity-trading-tool/ecosystem.production.config.js)
- [ecosystem.staging.config.js](/Users/gvangalen/Documents/antigravity-trading-tool/ecosystem.staging.config.js)

## Validation Snapshot

- deploy/rollback hardening tests should now verify the shared env scripts
  instead of expecting old inline logic in `deploy_live.sh`
- missing PM2 config is intentionally treated as a hard failure
- `deploy.sh` is intentionally blocked

## Acceptance Read

This tranche is ready when:

- operators have one supported entrypoint per environment
- production and staging both use explicit environment PM2 configs
- rollback uses the same environment-specific config contract
- legacy deploy paths cannot silently bypass the guarded flow
