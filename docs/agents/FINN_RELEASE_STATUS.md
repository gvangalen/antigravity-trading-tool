# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_CI_PENDING`; local Build gates passed, candidate is not deployed. |
| Goal | Confirm and persist monthly Smart DCA against the production integer month-day schema. |
| Candidate branch | `codex/finn-smart-dca-confirm` |
| Candidate implementation SHA | `a9e68bad22746d29467bf6f4728a582754e47757`; followed by this release-status commit. |
| PR | Pending. |
| Production SHA | `87bde0307c33448a41ab052868043147d47ecc0a` before this repair; public backend and frontend both reported it with HTTP 200 on 2026-10-04. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- User-provided authenticated live QA on `87bde0307c33448a41ab052868043147d47ecc0a` confirmed fixed weekly ETH DCA, but two attempts to confirm a monthly ETH Smart DCA draft failed. The browser did not expose the typed error.
- Build read the production execution errors for those two attempts at 18:30 and 18:31 UTC. Both failed in `INSERT INTO setups`: asyncpg rejected the string `'12'` for integer `dca_month_day`. The atomic setup/strategy write did not reach strategy creation. This is a schema/type mismatch, not a score-curve or provider failure.
- SetupService now normalizes a monthly day to integer and SetupRepository binds it as integer for create and update. The disposable parity schema now uses and migrates to the production integer type, so the full local confirmation can catch this class of failure.
- Build used only synthetic local users for writes. The production check was read-only diagnostic evidence. Authenticated production acceptance remains independent QA's responsibility.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector evaluation gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Exact monthly ETH Smart DCA confirmation | Browser-style shared idempotency key; publish and confirm HTTP 200; execute HTTP 200 `succeeded`, replay `already_executed`; saved setup month day is integer `12`, strategy is `custom` with €80 base and 0.75/1.0/1.25 curve. | `.local-finn-parity-artifacts/smart-dca-confirm-repro.json`, SHA-256 `d32e653cdb6feaa12399d05f7ad8b815a094904022253217580059e6009a29fc`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/smart-monthly-action-matrix.json`, SHA-256 `a9c6a3e77b3b3fe78e099e7c8528cb1ccceaf4d24214f09183d587247badc0f4`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/smart-monthly-selector-development.json`, SHA-256 `fc17dde1ae049ba94f02a8b4a03453907a195db8b67c13305788ead12da6b937`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/smart-monthly-selector-regression.json`, SHA-256 `1ea78a404ae96b43efa9fa4d89efbf42cf73be1e991d439846ff9eef761f2c1e`. |
| Backend | `3087 passed, 3 skipped`; includes integer month-day insert/update binding regression. | `pytest -q`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands, test:proposals and audit:high passed; zero high production dependency vulnerabilities. | Canonical local script output. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI and Auto Deploy | Pending. |
| Public backend health and frontend build-info | Candidate pending. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
