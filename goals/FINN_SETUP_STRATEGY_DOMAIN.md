# GOAL - FINN Setup and Strategy Domain

## Scope

Repair the setup identifier handoff, onboarding continuation, setup reads, and
the Strategy domain relationship for one setup with multiple owner-scoped
strategies. Validate the public browser, API, worker, and persistence paths.

## Non-goals

- No deployment or independent QA run.
- No change to FINN action-contract authority, confirmation, execution
  idempotency, broker execution, live trading, or live bot policy.
- No change to the setup-to-strategy relationship outside this domain.

## Acceptance

- `setup_id` is the canonical public setup identifier across consumers.
- Strategies have owner-scoped `setup_id`, canonical name, asset, and
  timeframe; a setup can have multiple strategies.
- Guided strategy input survives continuation and process boundaries.
- Strategy proposal, confirmation, one safe execution, and replay are proven.
- Setup and strategy browser flows, persistence, and FINN reads pass locally.
- No broker order, live trading, or live bot activation occurs.

## Validation

Run targeted backend/frontend contract tests, public API and worker-driven
flows with PostgreSQL/Redis/Celery, true-provider tests where FINN behavior is
claimed, and the applicable root/frontend suites. Record a local evidence
bundle. Do not deploy or start QA.
