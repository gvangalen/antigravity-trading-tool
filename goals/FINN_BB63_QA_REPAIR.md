# GOAL - FINN bb63 Production QA Repair

## Scope

Repair the production QA failures reported for `bb63bba31fd8879b655fda3925a88d146c6d36af` as one local Build batch: lifecycle terminalization, action-contract input projection and fixture identity resolution, proposal/confirmation/idempotent safe execution, and public terminal observability.

## Non-goals

- No sealed QA manifest access, edits, or prompt-specific tuning.
- No deployment or independent QA before every local gate is green.
- No broker orders, live trading, or live bot activation.
- No new action-contract schema; the existing operation registry remains canonical.

## Required Evidence

- Reproduce failures with local synthetic fixtures and protected-runner-compatible tests.
- Prove every existing action contract resolves required inputs from its registry contract.
- Prove terminal projection, polling and SSE publish operation, polarity, inputs, reason, dispatch and attempt details.
- Prove guided setup reaches a proposal and safe fixture confirmation/execution is idempotent.
- Run targeted tests, full local matrix, real provider development/regression, and root suite.

## Release Rule

Create one candidate only after all gates are green. Do not deploy or start QA automatically.
