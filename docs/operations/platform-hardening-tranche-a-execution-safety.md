# Platform Hardening Tranche A — Execution Safety

Last updated: 2026-06-05

## Goal

Close the highest-risk platform gaps around generated execution:

- duplicate bot-generated execution
- weak retry semantics
- overlapping status transitions

This tranche should make execution safety stronger by construction, not by convention.

## Scope

In scope:

- bot-generated order and execution idempotency
- serialized execution status transitions
- retry behavior that surfaces real failures
- tests that prove replay and overlap safety

Out of scope:

- broad queue redesign
- frontend changes
- new product features

## Suspected Problem Areas

### 1. Bot-generated execution lacks manual-order-grade idempotency

Current state:

- manual orders already have explicit idempotency protection
- bot-generated execution paths do not yet appear to have an equally hard DB invariant

Risk:

- replay, overlap, or worker retry can create duplicate side effects

### 2. Status transitions are not explicitly serialized everywhere

Current state:

- some flows rely on control flow and “normal timing”
- critical transitions do not all obviously use row locking or compare-and-swap semantics

Risk:

- parallel workers or retries can both believe they are the valid executor

### 3. Retry semantics may absorb failures

Current state:

- some Celery tasks use `autoretry_for`
- but business code can catch broad exceptions and return `{ ok: false }`

Risk:

- Celery sees a “completed” task where operators expected a retryable failure

## Primary Touchpoints

### Execution and bot paths

- [backend/trading-tool-backend/backend/services/bot_service.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/bot_service.py)
- [backend/trading-tool-backend/backend/api/bot_api.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/api/bot_api.py)
- [backend/trading-tool-backend/backend/celery_task/trading_bot_task.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/celery_task/trading_bot_task.py)

### Existing action safety patterns to reuse

- [backend/trading-tool-backend/backend/services/ai_action_engine.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/services/ai_action_engine.py)
- [docs/operations/replay-exactly-once-inventory.md](/Users/gvangalen/Documents/antigravity-trading-tool/docs/operations/replay-exactly-once-inventory.md)

### Schema and persistence

- [backend/trading-tool-backend/backend/infrastructure/models.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/models.py)
- [backend/trading-tool-backend/backend/infrastructure/repositories/bot_repository.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/repositories/bot_repository.py)
- [backend/trading-tool-backend/backend/migrations](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/migrations)

## Build Checklist

### Step 1 — Map the execution write path

Answer explicitly:

- where is a generated bot decision turned into an order/execution write?
- what record acts as the current execution identity?
- what state changes occur before and after the side effect?

Deliverable:

- one short doc section or inline notes in the implementation PR

### Step 2 — Add DB-level duplicate prevention

Goal:

- define a real uniqueness invariant for generated execution

Likely shapes:

- unique by `(decision_id, execution_kind)`
- or unique by `(user_id, bot_decision_id, execution_window)`

Requirement:

- duplicate requests must become a safe no-op or existing-result lookup

### Step 3 — Serialize state transitions

Goal:

- make transition from “pending review/executable” to “executing/executed” overlap-safe

Acceptable patterns:

- `SELECT ... FOR UPDATE`
- conditional update / compare-and-swap
- atomic claim semantics similar to assistant pending actions

### Step 4 — Fix retry semantics

Goal:

- retryable failures should raise, not quietly return a soft failure object

Rule:

- if a Celery task is configured for retry, business code must not swallow the exception path unless that path is truly terminal and intentional

### Step 5 — Add replay/overlap tests

Add or extend tests for:

- duplicate bot-generated execution request
- replay after partial failure
- overlapping execution attempt
- retry path where failure raises and retries cleanly

Likely test homes:

- [backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py)
- [backend/trading-tool-backend/backend/tests/test_replay_exactly_once_step8.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_replay_exactly_once_step8.py)
- new targeted tests near bot execution if needed

## Acceptance Criteria

This tranche is done when:

- duplicate bot-generated execution is blocked by the DB layer
- replay of the same generated execution returns safe deterministic behavior
- overlapping workers cannot both execute the same transition
- retryable failures are not silently downgraded into `{ ok: false }`
- regression tests prove the invariant

## Suggested Implementation Order

1. inspect and map generated execution writes
2. add schema invariant
3. add repository/service claim transition
4. make Celery retry semantics honest
5. add tests

## Non-Goals

This tranche does not try to:

- solve all queue backlog issues
- redesign bot architecture
- optimize read latency
- refactor every execution path at once

It is a safety tranche first.

## Implementation Status

Implemented in current working tree:

- DB uniqueness for bot-generated execution rows and execute-ledger rows
- atomic `planned -> executing` claim for bot decision execution
- explicit `failed_execution` fallback when claimed execution crashes
- duplicate execute-ledger writes skip portfolio mutation
- Celery bot task now raises retryable failures instead of returning soft `{ ok: false }`

Validation snapshot:

- `pytest -q backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py backend/trading-tool-backend/backend/tests/test_replay_exactly_once_step8.py` -> `9 passed`
- `python3 -m py_compile ...` for the touched execution files -> green
