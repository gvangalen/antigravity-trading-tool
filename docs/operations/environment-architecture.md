# Tradamind Environment Architecture

Last updated: 2026-05-26

## Goal

Tradamind now has a repo-level deployment architecture for three distinct modes:

- local development
- staging / QA
- production

The purpose is to stop treating production as a mixed live + test environment and make releases safer, more testable, and easier to reason about.

## Environment Model

### Local development

Purpose:

- feature work
- builder-agent iteration
- migration dry-runs
- experiments

Expected characteristics:

- localhost frontend/backend
- local Postgres + Redis
- sandbox API keys only
- fake/test users only

### Staging

Recommended domains:

- `staging.tradamind.com`
- `api-staging.tradamind.com`

Purpose:

- QA
- mobile validation
- auth/session testing
- security review
- migration validation
- release rehearsal

Expected characteristics:

- dedicated Oracle VM
- dedicated Postgres and Redis for staging only
- dedicated staging `.env`
- dedicated PM2 and Celery namespace
- sandbox exchange keys only

### Production

Recommended domains:

- `app.tradamind.com`
- `api.tradamind.com`

Purpose:

- real users
- real bots
- real reports
- stable releases

Expected characteristics:

- dedicated Oracle VM
- dedicated production Postgres and Redis
- production-only secrets
- controlled deploys and rollback

## Git / Release Flow

Branches:

- `feature/*` for local development
- `develop` for staging deploys
- `main` for production deploys

Release flow:

1. build on `feature/*`
2. merge into `develop`
3. auto or operator deploy to staging
4. QA + security + systems validation on staging
5. merge into `main`
6. production deploy

## Repo Artifacts

### PM2 configs

- [ecosystem.production.config.js](/Users/gvangalen/Documents/antigravity-trading-tool/ecosystem.production.config.js)
- [ecosystem.staging.config.js](/Users/gvangalen/Documents/antigravity-trading-tool/ecosystem.staging.config.js)
- shared generator:
  [ops/deploy/ecosystem.shared.js](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/ecosystem.shared.js)

Ports:

- production frontend/backend: `5002` / `8000`
- staging frontend/backend: `5102` / `8100`

### Deploy / rollback

- production deploy:
  [deploy_live.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy_live.sh)
- staging deploy:
  [deploy_staging.sh](/Users/gvangalen/Documents/antigravity-trading-tool/deploy_staging.sh)
- shared deploy engine:
  [ops/deploy/deploy_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/deploy_env.sh)
- production rollback:
  [rollback_live.sh](/Users/gvangalen/Documents/antigravity-trading-tool/rollback_live.sh)
- staging rollback:
  [rollback_staging.sh](/Users/gvangalen/Documents/antigravity-trading-tool/rollback_staging.sh)
- shared rollback engine:
  [ops/deploy/rollback_env.sh](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/rollback_env.sh)

State markers are environment-specific:

- `ops/deploy/production/LAST_GOOD_COMMIT`
- `ops/deploy/staging/LAST_GOOD_COMMIT`

### Oracle infrastructure

Terraform stack:

- [backend/trading-tool-backend/backend/infrastructure/oci/main.tf](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/oci/main.tf)
- [backend/trading-tool-backend/backend/infrastructure/oci/variables.tf](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/oci/variables.tf)
- [backend/trading-tool-backend/backend/infrastructure/oci/outputs.tf](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/oci/outputs.tf)
- [backend/trading-tool-backend/backend/infrastructure/oci/cloud-init.yaml.tpl](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/oci/cloud-init.yaml.tpl)
- [backend/trading-tool-backend/backend/infrastructure/oci/terraform.tfvars.example](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/oci/terraform.tfvars.example)

This stack is prepared to provision:

- one staging VM
- one production VM
- one shared VCN with isolated public subnets
- per-environment NSGs

## Nginx / DNS

Example nginx configs:

- [ops/deploy/nginx/app.tradamind.com.conf.example](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/nginx/app.tradamind.com.conf.example)
- [ops/deploy/nginx/staging.tradamind.com.conf.example](/Users/gvangalen/Documents/antigravity-trading-tool/ops/deploy/nginx/staging.tradamind.com.conf.example)

Required DNS after provisioning:

- `app.tradamind.com` -> production VM public IP
- `api.tradamind.com` -> production VM public IP
- `staging.tradamind.com` -> staging VM public IP
- `api-staging.tradamind.com` -> staging VM public IP

## What Still Needs Real Cloud Access

This repo now contains the infrastructure and deployment plan, but actual server creation still needs:

1. OCI credentials (`tenancy_ocid`, `user_ocid`, `compartment_ocid`, fingerprint, private key)
2. Terraform apply access
3. DNS record creation
4. SSL certificate issuance
5. environment-specific `.env` and secrets setup

## Recommended Cutover Order

1. provision staging VM
2. provision production VM or migrate current prod into the new production lane
3. attach DNS
4. configure staging secrets
5. run `deploy_staging.sh`
6. validate QA/security flows on staging
7. configure production secrets
8. deploy production via `deploy_live.sh`

## Immediate Next Build Layer

Once staging is actually provisioned and reachable, the recommended next product layer remains:

1. Portfolio Risk 2.0
2. Reports / Reflection 2.0
3. Execution Guardrails 3.0 UI
