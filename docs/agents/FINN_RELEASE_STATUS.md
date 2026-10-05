# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `LOCAL_VALIDATED`; CI, Auto Deploy, public identity checks and independent QA pending. |
| Goal | List every strategy linked to one setup and create a second fixed or Smart DCA strategy through a complete FINN conversation. |
| Candidate branch | `codex/finn-multi-strategy-flow` |
| Candidate implementation SHA | `b38fda2504f209ed7b3f177900fdb14e41bd20fe`; this status commit follows it. |
| PR | Pending. |
| Production SHA | Not yet this candidate. The preceding verified release was `c928622bbe6a5b67d44bdd9bc4c7112f5b26003b`. |
| Release owner | Build |
| Last updated | 2026-10-05 |

## Change And Limits

- The user-supplied authenticated browser QA on `41fb2aa7...` found that FINN could store and target two strategies under one setup, but could not list both. A separate second-strategy request under an existing ETH-DCA setup asked for trade-only entry, stop and targets and lost the strategy concept after clarification.
- The owner-scoped `get_linked_strategies` read now returns the complete linked collection instead of selecting one row. A verified parent setup determines whether a new strategy uses trade fields or DCA amount and benchmark curve fields. The DCA follow-up keeps its setup and the name slot across turns. The concept card displays the resulting amount rule and states that confirmation does not start a bot or purchase.
- Local real Responses tests listed two BTC strategies by name, confirmed a second fixed ETH-DCA strategy and a second Smart ETH-DCA strategy under their existing setups, and completed the missing-name clarification without switching object type. All writes were to synthetic local users. These tests do not establish authenticated production acceptance.
- This batch did not change bot activation or purchase logic. Actual Smart-DCA score-driven execution remains outside this release claim.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Multi-strategy real-provider runtime | Two linked BTC strategies returned; fixed and Smart ETH-DCA second strategies confirmed and persisted with owner isolation and idempotent replay; guided name follow-up completed. | `.local-finn-parity-artifacts/multi-strategy-local-probe.json` SHA-256 `feecfecc332da78edcaf03bbbf74420cfc28c5b9c81ef98c99f58408430133aa`; `multi-strategy-smart-probe.json` SHA-256 `2d80eff43a93320aa3430a401330ee9fbb6cddc46b7e8dcdd4e7d34adf09b1a0`; `multi-strategy-followup-probe.json` SHA-256 `ad6d2bf6c8a5cba15bbbe5994828e46c6b0ed3367cd455c2761ab463751e3f0b`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. The trade-strategy fixture's parent was corrected from DCA to trade to match its existing entry/stop/targets prompt; the checks and pass criteria were unchanged. | `.local-finn-parity-artifacts/multi-strategy-action-matrix-rerun.json`, SHA-256 `529b50bdf772b78025e70e489e10eee23318bd23753ee411cba20c20af0826c7`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/multi-strategy-selector-development.json`, SHA-256 `49f5dbdad03b1866ac8aed4b1f9ea12ac9eb8fee8083cd33ed0106d0111747b9`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/multi-strategy-selector-regression.json`, SHA-256 `7bd144aad0cdcc63a3aaf35031843049b725d53167265b3dd61f52b27c4a4bd4`. |
| Backend | `3097 passed, 3 skipped`; focused strategy/read tests included. | `pytest -q`; `.local-finn-parity-artifacts/multi-strategy-pytest.log`. |
| Frontend | Typecheck, i18n lint, i18n tests, command tests, proposal tests, setup tests, build and production high-severity audit passed; zero high dependency vulnerabilities. | `.local-finn-parity-artifacts/frontend-gates.log` and `frontend-additional.log`. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI and Auto Deploy | Pending. |
| Public backend health and frontend build-info | Pending for this candidate. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
