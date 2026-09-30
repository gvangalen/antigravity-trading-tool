# FINN Release Status

Status: canonical

Runtime identity comes from Git and the public deployment surfaces, not from
this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `CANDIDATE_CI_PENDING` |
| Active goal | Repair the recurring live coach defects reported on `a6247144468e9d407bb376cda115af861bfe6554`: contradictory saved BTC setup inventory and entry-condition follow-ups; BTC-to-AAPL rule scope hidden by FOMO coaching. |
| Candidate branch | `codex/finn-coach-structural-context` |
| Candidate code SHA | Pending commit and CI. |
| Production code SHA | The user reported `a6247144468e9d407bb376cda115af861bfe6554` for the latest authenticated browser QA. Build has not yet verified the next deployed candidate. |
| Release owner | Build |
| Last updated | `2026-09-30` |

The prior release remains historical evidence; its `READY_FOR_INDEPENDENT_QA`
phase does not apply to this new repair batch. The user supplied the latest
live findings. Build has not run authenticated production QA or used the
protected QA fixture or sealed holdout.

## Root Cause and Repair

The old tool represented both one active setup and a full saved-setup list.
Plural questions and follow-ups could therefore fall into singleton entity
resolution, where multiple BTC setups became an ambiguity or the first row
was mistaken for the whole list. A phrase such as "bevestigde
instapvoorwaarde" could also be parsed as an action confirmation, bypassing a
read. Separately, FOMO language could steer a two-asset applicability question
into general coaching before its asset scope was answered.

This candidate adds an owner-scoped, typed saved-setup inventory, re-reads the
verified setup IDs for collection follow-ups, distinguishes confirmation
questions from confirmation actions, and answers cross-asset rule scope before
secondary FOMO context. The inventory response explicitly states that linked
strategies were not checked for entry rules.

## Local Build Evidence

The local parity stack used isolated PostgreSQL, Redis, API, and Celery with
synthetic users. FINN chat used `gpt-6-luna` with reasoning `none`; selector and
semantic verification used `gpt-4o-mini`. Artifacts are ignored files under
`.local-finn-parity-artifacts/`.

| Gate | Result | Evidence |
| --- | --- | --- |
| New multi-turn coach repro through API/Celery | `8/8` completed, no proposals | `structural-coach-repro.json`, SHA-256 `654cdfa0c68fcc503cde5627de28182d2974bc0d988c7a35785ea589b903f551`; three BTC setups plus a separate ETH setup, verified collection-ID follow-ups and BTC-to-AAPL answer order. |
| Real-provider saved-plan scope development | `14/14` | `structural-query-eval.json`, SHA-256 `e74fe4b319135e53e4d8cb73fb8fe75ea474f5515979c37fdb20b6827e02b54c`. |
| Real-provider selector development | `18/18` | `structural-provider-development.json`, SHA-256 `357ec64637c1b0ead04cf224e52205ebd32be03bcc789f94b38d37fb6dd30bff`. |
| Real-provider selector regression | `109/109` | `structural-provider-regression.json`, SHA-256 `0eea45e5f441a7d8bc58a2980baeff5ce0367694e5a40950f481b6d95c1bb2b3`; no provider, schema, parse, or timeout failures. |
| Full safe action matrix on final local build | `16/16`, zero broker orders, live bots, live-trading calls, or production connections. | `structural-action-matrix-final.json`, SHA-256 `c21867a26768b5927a90585b3846e6baeafcb6ab72fd96b215fa1d64a6028f27`. |
| Backend canonical suite | `2894 passed, 3 skipped` | `pytest -q` after the final code changes. |
| Frontend | `PASS` | `typecheck`, `lint:i18n`, `test:i18n`, `test:commands`, `audit:high`, and production `build`; no frontend source changes. |

## Release and Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | Pending. |
| Main CI | Pending. |
| Auto Deploy | Pending. |
| Backend health and frontend build-info | Pending for the new candidate. |
| Independent authenticated live QA | Pending; QA owns the protected fixture, full live matrix, and final verdict. |

Build's local checks establish technical readiness only. Authenticated
production acceptance remains independent QA's responsibility.
