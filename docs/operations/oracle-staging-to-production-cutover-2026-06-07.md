# Oracle Staging To Production Cutover

Last updated: 2026-06-07

## Current State

- repo `main` head: `f4058aa`
- current production host: `143.47.186.148`
- current staging / candidate-production host: `134.98.148.12`
- staging hostname: `tradamind-staging`
- staging branch: `develop`
- staging remote dir: `/home/ubuntu/antigravity-trading-tool`

## What Is Already Done

- Splitpay has been fully removed from `134.98.148.12`
- Tradamind staging is deployed and online on `134.98.148.12`
- nginx now routes only Tradamind traffic on that host
- staging PM2 apps are running:
  - `frontend-staging`
  - `backend-staging`
  - `celery-worker-default-staging`
  - `celery-worker-market-portfolio-staging`
  - `celery-worker-scoring-execution-staging`
  - `celery-worker-ai-reporting-staging`
  - `celery-beat-staging`
- local staging health checks currently pass:
  - `GET /api/health` -> `200`
  - external `GET /api/system/health` -> `401`
  - `GET /report` -> `200`
- PM2 reboot persistence is configured through `pm2-ubuntu.service`
- a production-mode core dry run also runs locally on the same host:
  - `frontend` on `:5002`
  - `backend` on `:8000`
- host-based nginx routing is prepared for:
  - `app.tradamind.com`
  - `api.tradamind.com`
  - `staging.tradamind.com`
  - `api-staging.tradamind.com`
- production workers are intentionally not started yet, to avoid duplicate scheduled work while the old production host is still active

## Current Live State

As of 2026-06-07:

- the old public host `143.47.186.148` now keeps TLS termination for `tradamind.com`
- live public traffic for:
  - `https://tradamind.com/`
  - `https://tradamind.com/api/*`
  is proxied to the new host `134.98.148.12`
- production frontend/backend now run on the new host on:
  - frontend `:5002`
  - backend `:8000`
- production workers and beat now also run on the new host
- old production workers and beat on `143.47.186.148` are stopped to avoid duplicate queue execution
- old frontend/backend on `143.47.186.148` remain available only as rollback capacity

## Promotion Goal

Promote `134.98.148.12` from staging / candidate-production to the primary Tradamind production host after final validation.

## Recommended Cutover Order

1. Validate staging on `134.98.148.12`
2. Freeze non-essential changes on the old production host
3. Copy final production secrets and production env values to `134.98.148.12`
4. Deploy `main` to `134.98.148.12` in production mode
5. Verify production-mode health locally on the new host
6. Switch DNS / public traffic to `134.98.148.12`
7. Run external smoke checks
8. Keep `143.47.186.148` untouched as rollback capacity until the new host has settled

## Validation Before Promotion

- run QA / architect / security smoke against staging on `134.98.148.12`
- confirm staging auth, report, assistant, bot, and market read paths behave as expected
- confirm staging deep health is locally reachable from the host
- confirm Redis and Postgres are enabled and healthy after restart

## Production Preparation On New Host

- create production backend env from the current live production baseline
- set:
  - `APP_ENV=production`
  - production-only `JWT_SECRET_KEY`
  - production-only `ENCRYPTION_KEY`
  - production-only database name and password
  - production Redis URLs
  - production `FRONTEND_URL`, `API_BASE_URL`, and CORS values
- provision production Postgres database on `134.98.148.12`
- keep staging database separate from production database

## DNS / Traffic Cutover

Expected target after promotion:

- `app.tradamind.com` -> `134.98.148.12`
- `api.tradamind.com` -> `134.98.148.12`

Optional staging targets if DNS is added later:

- `staging.tradamind.com` -> `134.98.148.12`
- `api-staging.tradamind.com` -> `134.98.148.12`

## Rollback Posture

Until the new production host has proven stable:

- keep `143.47.186.148` intact
- do not delete the old production database or env files
- keep rollback limited to traffic reversal plus production redeploy on the old host if needed

## Immediate Next Actions

1. monitor live traffic on `https://tradamind.com`
2. verify queue depth and worker stability on `134.98.148.12`
3. optionally add direct DNS records later for:
   - `app.tradamind.com`
   - `api.tradamind.com`
   - `staging.tradamind.com`
   - `api-staging.tradamind.com`
4. once stable, retire or repurpose the old frontend/backend processes on `143.47.186.148`
