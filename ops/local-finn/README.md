# Local FINN V2 Integration

This starts only local PostgreSQL and Redis in Docker. FastAPI and the FINN
interactive worker use the production entrypoints and queue route locally.

1. `cp ops/local-finn/finn-local.env.example ops/local-finn/finn-local.env`
2. `ops/local-finn/finn-local.sh start`
3. `ops/local-finn/finn-local.sh health`
4. `ops/local-finn/finn-local.sh matrix`
5. `ops/local-finn/finn-local.sh selector-eval development --output /tmp/finn-local-development.json`
6. `ops/local-finn/finn-local.sh logs`
7. `ops/local-finn/finn-local.sh stop` or `ops/local-finn/finn-local.sh reset`

The command reads `OPENAI_API_KEY` only from
`~/tradamind-local-secrets/finn-development.env`; it never reads production
credentials. `FINN_LOCAL_SAFE_ADAPTERS=1` is required for local fixture action
tests. It enables only the existing non-financial database adapters for the
isolated local fixture; broker orders and live bot activation remain disabled.

`matrix` runs all 16 current action contracts through real FastAPI, Celery,
PostgreSQL, Redis and Responses calls. It verifies proposal, confirmation,
execution, owner scope, idempotent replay and guided follow-up using only
synthetic local users. The canonical action-adapter registry test follows the
runtime matrix. Its artifact is written to
`.local-finn-parity-artifacts/full-action-matrix.json`. `selector-eval` always
loads the same local environment before making real provider calls, so its
telemetry cannot fall back to another database.

PM2 parity is verified by `pytest -q backend/trading-tool-backend/backend/tests/test_finn_local_integration.py`:
the production ecosystem worker commands, work directories, queue names and
environment names are compared with this local harness.

To check a dated but stale Score 2.0 source through the actual Smart-DCA Paper
task, run `bash ops/local-finn/score2-stale-paper.sh` after `start`. This creates
one disposable local fixture, builds its scores, dispatches through a dedicated
local Redis/Celery queue, and verifies Hold, zero amount, no order or ledger
entry, unchanged virtual cash, and both portfolio snapshots. The probe refuses
any environment other than the exact local PostgreSQL and Redis endpoints.
It uses synthetic indicator history, so it does not establish a production
provider's behavior or replace authenticated live QA.
