# Local FINN V2 Integration

This starts only local PostgreSQL and Redis in Docker. FastAPI and the FINN
interactive worker use the production entrypoints and queue route locally.

1. `cp ops/local-finn/finn-local.env.example ops/local-finn/finn-local.env`
2. `ops/local-finn/finn-local.sh start`
3. `ops/local-finn/finn-local.sh health`
4. `ops/local-finn/finn-local.sh matrix`
5. `ops/local-finn/finn-local.sh matrix --case concept`
6. `ops/local-finn/finn-local.sh selector-eval development --output /tmp/finn-local-development.json`
7. `ops/local-finn/finn-local.sh logs`
8. `ops/local-finn/finn-local.sh stop` or `ops/local-finn/finn-local.sh reset`

The command reads `OPENAI_API_KEY` only from
`~/tradamind-local-secrets/finn-development.env`; it never reads production
credentials. `FINN_LOCAL_SAFE_ADAPTERS=1` is required for local fixture action
tests. It enables only the existing non-financial database adapters for the
isolated local fixture; broker orders and live bot activation remain disabled.

`matrix` uses real FastAPI, Celery, PostgreSQL, Redis, the structured OpenAI
selector, persisted contracts, polling and SSE. It creates only synthetic local
users and verifies a non-financial `watchlist_add` confirmation/execution
replay. A full `matrix` invocation also runs the canonical action-adapter
registry test: every existing supported V1 write contract must resolve to one
existing adapter. A targeted `matrix --case ...` run intentionally skips that
full registry assertion. `selector-eval` always loads the same local environment
before making real provider calls, so its telemetry cannot fall back to another
database.

PM2 parity is verified by `pytest -q backend/trading-tool-backend/backend/tests/test_finn_local_integration.py`:
the production ecosystem worker commands, work directories, queue names and
environment names are compared with this local harness.
