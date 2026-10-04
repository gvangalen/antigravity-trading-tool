# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local Build gates, CI, Auto Deploy and public identity checks passed. |
| Goal | Keep an old FINN proposal withdrawn through an explicit asset correction, a clarification turn and the replacement proposal. |
| Candidate branch | `codex/finn-proposal-asset-correction-followup` |
| Candidate implementation SHA | `03206d0b4a49a6fdd219cdbab6236cc50d794d26`; followed by release-status and merge commits. |
| PR | [#59](https://github.com/gvangalen/antigravity-trading-tool/pull/59), merged. |
| Production SHA | `25317035047c7427422125662d0d7a06031e81ba`; public backend and frontend both reported it with HTTP 200 on 2026-10-04. This status-only follow-up will create a later deploy SHA; verify that final identity separately. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- Explicit correction phrases, including the live QA wording `Correctie: gebruik AAPL (Apple) in plaats van ETH`, cancel the old owner- and conversation-scoped proposal before selection. Hypothetical comparison questions do not cancel it.
- A supported correction stays on the original proposal operation (`create_setup` for DCA), rather than becoming an active-asset change. The cancelled proposal ID and any issued confirmation token remain unusable.
- The owner's earlier non-asset fields and any explicitly named replacement are carried into a clarification turn. FINN receives the verified cancellation status as tool context. No replacement is claimed before its proposal contract succeeds.
- In the UI, an old card remains unconfirmable while a clarification is open or a proposal-status read fails. A cancelled card is retired after the authoritative status read.
- Build used synthetic local users only. No saved plan, bot or trade was executed. Authenticated production acceptance belongs to independent QA.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the existing selector evaluation gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Full ETH to AAPL correction | Old ETH `cancelled`; new AAPL `create_setup` draft; no save or execution. | `.local-finn-parity-artifacts/proposal-apple-final-full.json`, SHA-256 `39ca6fd41c4bc48a0f8342f7390068a2fc2f94e94b4763b044d19565746d10ac`. |
| ETH to AAPL across a name clarification | Old ETH `cancelled` before clarification; after the name answer, new AAPL `create_setup` draft. | `.local-finn-parity-artifacts/proposal-apple-final-clarification.json`, SHA-256 `ac13a1b37fcaeea4b51f3643a32bd1fca05c660be49ea28aa00311b0493a7061`. |
| ETH to unsupported ETH/EUR | Old ETH `cancelled`; no replacement; old publish and token confirmation both HTTP 409. | `.local-finn-parity-artifacts/proposal-apple-final-unsupported.json`, SHA-256 `5e154d7cc50b91435f059623d9ecf2826b6d3dbad59cb2d0b4b97581efb85895`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/proposal-apple-final-action-matrix.json`, SHA-256 `1dd47ec608bf9e5193facb60ffb3be722e2eb60c8fcfee445abb8931ef612215`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/proposal-apple-final-selector-development.json`, SHA-256 `e2476c225d0c7631310dc28f905b477ed45d9b9e4f40b7d616b03e254cd94f21`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/proposal-apple-final-selector-regression.json`, SHA-256 `4ab06ad19a0bb91450e5be0ce5176da2ba71a6c000f8bd849d838293d2b4b9f0`. |
| Backend | `3081 passed, 3 skipped`; includes the exact QA correction wording, a name containing “Correctie” and a hypothetical negative case. | `pytest -q`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands, test:proposals and audit:high passed; zero high production dependency vulnerabilities. | Canonical local script output. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [run 37212327942](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37212327942), all five jobs green. |
| Main CI and Auto Deploy | `PASS`: [main CI 37212497756](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37212497756) and [Auto Deploy 37212618049](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37212618049) on `25317035047c7427422125662d0d7a06031e81ba`. |
| Public backend health and frontend build-info | `PASS`: both HTTP 200 and SHA `25317035047c7427422125662d0d7a06031e81ba`. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
