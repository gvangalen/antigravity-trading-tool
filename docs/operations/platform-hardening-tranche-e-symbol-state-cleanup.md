# Platform Hardening Tranche E — Symbol/State Cleanup

Last updated: 2026-06-05

## Goal

Stop `bot_portfolios` from collapsing state across asset changes by scoping
portfolio rows to `(bot_id, symbol)` instead of `bot_id` alone.

## What Changed

Implemented in the current working tree:

- new migration adds a symbol-scoped unique index for `bot_portfolios`
- legacy unique indexes on `bot_id` alone are removed during migration
- blank portfolio symbols are backfilled from:
  - `bot_configs.symbol`
  - strategy/setup symbol
  - fallback `BTC`
- repository portfolio upserts now use `ON CONFLICT (bot_id, symbol)`
- trading bot agent execute-path upserts now use `ON CONFLICT (bot_id, symbol)`
- bot portfolio state reads in the trading bot agent now query by symbol too
- portfolio intelligence context joins `bot_portfolios` by both `bot_id` and
  resolved symbol

## Primary Touchpoints

- [backend/trading-tool-backend/backend/scripts/migrations/2026_06_05_bot_portfolio_symbol_scope.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/scripts/migrations/2026_06_05_bot_portfolio_symbol_scope.py)
- [backend/trading-tool-backend/backend/infrastructure/repositories/bot_repository.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/infrastructure/repositories/bot_repository.py)
- [backend/trading-tool-backend/backend/ai_agents/trading_bot_agent.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/ai_agents/trading_bot_agent.py)
- [backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py](/Users/gvangalen/Documents/antigravity-trading-tool/backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py)

## Validation Snapshot

- `pytest -q backend/trading-tool-backend/backend/tests/test_phase2_portfolio_execution_invariants.py` -> `6 passed`
- `python3 -m py_compile ...bot_repository.py ...trading_bot_agent.py` -> green

## Acceptance Read

This slice is ready when:

- symbol changes cannot overwrite prior bot portfolio state
- read paths fetch the symbol-matching portfolio row
- portfolio intelligence no longer joins a stale row from another asset context
