# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local Build gates, CI, Auto Deploy and public identity checks passed. |
| Goal | Withdraw a superseded FINN proposal after an explicit asset correction and remove its confirmation card. |
| Candidate branch | `codex/finn-proposal-correction-invalidation` |
| Candidate implementation SHA | `f2fab0432fa337c3406641a9fb1a3b9240211e5c`; the status commit will add a later branch SHA. |
| PR | [#57](https://github.com/gvangalen/antigravity-trading-tool/pull/57), merged. |
| Production SHA | `f8a5644011297fe2b1a324287f76c96b3ea2a826`; public backend and frontend both reported it with HTTP 200 on 2026-10-04. This status-only follow-up will create a later deploy SHA; verify that final identity separately. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- An explicit correction to a different catalog instrument cancels the latest owner-scoped, conversation-scoped open proposal before the provider answers. This includes an unsupported full pair such as `ETH/EUR`; the pair is not substituted with ETH.
- Cancellation revokes any already issued confirmation token. The original proposal cannot be published or confirmed after correction.
- The chat temporarily disables confirmation while a turn is pending, re-reads visible proposal statuses after the turn, removes retired cards and checks the server again before confirming. OpenAI remains responsible for the conversational answer.
- No saved plan, bot or trade was changed by Build's local probes. Build did not use the protected QA fixture. Authenticated production acceptance remains independent QA's responsibility.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider with synthetic users. It did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| ETH to unsupported pair, with an already issued token | Completed answer, no replacement proposal; old ETH proposal `cancelled`; old publish and token confirmation both HTTP 409. | `.local-finn-parity-artifacts/proposal-correction-final-probe.json`, SHA-256 `5eba7b26c3b1f598f0301fa04c1aa0df71f1929fddf4f44634c47275cc7cc14f`. |
| ETH to supported AAPL correction | Old ETH proposal `cancelled`; new AAPL proposal `draft` in the same conversation. | `.local-finn-parity-artifacts/proposal-supported-correction-final-probe.json`, SHA-256 `7a0de9d039c41ea153c34a112f002e68c21f831a63b4ffb4f168118e4a745480`. |
| Worker-driven safe action contracts on final code | `16/16`; zero broker orders, live trading calls, live bots or production connections. | `.local-finn-parity-artifacts/proposal-correction-final-action-matrix.json`, SHA-256 `a8e833732c715aa927c8657963695bd21f83b45233d37dc5cf7b437ba7bb231b`. |
| Real-provider selector development | `18/18`; no provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/proposal-correction-final-selector-development.json`, SHA-256 `9d76711864b423d695bdf9378df12e5c62c1bbf0d565a48a0890dee4fa1a1bcf`. |
| Real-provider selector regression | `109/109`; no provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/proposal-correction-final-selector-regression.json`, SHA-256 `b50a16326b0df1d2667e9d98de86226a776bdfb3333cfa4398f7963c21f28906`. |
| Backend | `3078 passed, 3 skipped`; explicit correction parsing and negative case included. | `pytest -q`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands, new test:proposals and audit:high passed; zero high production dependency vulnerabilities. | Canonical local script output. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [run 37199819738](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37199819738), all five jobs green after adding the required tracked frontend export. |
| Main CI and Auto Deploy | `PASS`: [main CI 37199954664](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37199954664) and [Auto Deploy 37200039750](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37200039750) on `f8a5644011297fe2b1a324287f76c96b3ea2a826`. |
| Public backend health and frontend build-info | `PASS`: both HTTP 200 and SHA `f8a5644011297fe2b1a324287f76c96b3ea2a826`. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence and CI do not establish authenticated production acceptance.
