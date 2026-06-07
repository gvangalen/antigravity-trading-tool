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

## Release process

- [ ] feature work targets `feature/*`
- [ ] staging deploys from `develop`
- [ ] production deploys from `main`
- [ ] QA/security validation happens on staging before production merge
