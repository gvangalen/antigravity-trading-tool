# Staging / Production Cutover Checklist

## Provisioning

- [ ] Terraform vars filled in
- [ ] `terraform init`
- [ ] `terraform plan`
- [ ] `terraform apply`
- [ ] public IPs captured for staging and production

## DNS / TLS

- [ ] `staging.tradamind.com` DNS points to staging
- [ ] `api-staging.tradamind.com` DNS points to staging
- [ ] `app.tradamind.com` DNS points to production
- [ ] `api.tradamind.com` DNS points to production
- [ ] TLS certificates issued for all four domains

## Secrets

- [ ] staging `.env` created
- [ ] production `.env` created
- [ ] staging JWT / encryption / OpenAI / exchange secrets isolated
- [ ] production JWT / encryption / OpenAI / exchange secrets isolated

## Services

- [ ] Postgres running on staging
- [ ] Redis running on staging
- [ ] Postgres running on production
- [ ] Redis running on production
- [ ] PM2 configured for staging
- [ ] PM2 configured for production

## Deploy validation

- [ ] runtime bootstrap auto-installs backend Python deps, `email-validator`, and Playwright Chromium
- [ ] runtime bootstrap auto-installs frontend Node deps on a fresh host
- [ ] `deploy_staging.sh` succeeds
- [ ] staging `/api/health` passes
- [ ] staging `/api/system/health` passes from localhost
- [ ] staging `/report` returns `200`
- [ ] `deploy_live.sh` succeeds
- [ ] production `/api/health` passes
- [ ] production `/api/system/health` stays operator-only externally
- [ ] production `/report` returns `200`

## FINN trader-profile release signoff

- [ ] staging release-under-test commit is explicitly recorded
- [ ] trader-profile preflight is green on staging
- [ ] trader-profile replay gate is green on staging (`41/41`, `0` generic failures, `0` transactional misroutes)
- [ ] weighted trader-profile QA score is `>= 90`
- [ ] legacy/general-help lane is visibly profile-aware across A / B / C profiles
- [ ] memory / habit-aware interventions are evidence-based and stable
- [ ] behavioral telemetry is visible from real FINN flows

## Release process

- [ ] feature work targets `feature/*`
- [ ] staging deploys from `develop`
- [ ] production deploys from `main`
- [ ] QA/security validation happens on staging before production merge
- [ ] attach the latest trader-profile release note to the production rollout decision:
  - [FINN Trader Profile Release Note](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/finn-trader-profile-release-note-2026-06-23.md)
