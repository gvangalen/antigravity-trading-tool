# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local Build gates, CI, Auto Deploy and public identity checks passed. |
| Goal | Show the stored weekday immediately when opening an existing DCA setup in the editor. |
| Candidate branch | `codex/finn-existing-dca-editor` |
| Candidate implementation SHA | `9d787008`; followed by this release-status commit. |
| PR | [#69](https://github.com/gvangalen/antigravity-trading-tool/pull/69), merged. |
| Production SHA | `ba8884826ed5c4d0b185d6dc91cc51b48c506e86`; public backend and frontend both reported it with HTTP 200 on 2026-10-04. This status-only follow-up creates a later deploy SHA; verify that final identity separately. |
| Release owner | Build |
| Last updated | 2026-10-04 |

## Change And Limits

- Authenticated live QA confirmed new fixed and Smart DCA create, confirm, persistence, and saved-strategy readback on `7cfbe072...`. The previously saved `ETH Vaste DCA Herhaal 0410` still appeared as Monday in the editor, while the new Friday plan appeared correctly.
- Read-only production DB inspection found weekday code `5` for both the old setup record 80 and the new setup record 82. Both values have the same text type and byte representation. The list API returns the persisted field without a per-record conversion. No plan was edited.
- The edit form previously initialized to Monday and loaded the selected plan only in an effect after the first paint. It now initializes from the selected plan before the first paint and remounts when switching to a different setup. A test passes both old and new record shapes through the initializer and expects Friday. This addresses the observed UI path; independent authenticated browser QA must verify the old plan after deployment.
- The QA run did not prove an actual score-driven purchase because current complete ETH benchmark scores were unavailable. No live trading claim is made.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Existing Friday form initialization | Both old and new saved record shapes with `dca_day=5` initialize as Friday; new-plan default remains Monday. | `npm run test:setups`: 3/3. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/existing-dca-editor-action-matrix.json`, SHA-256 `7ae01b28fe153cc4ee115d2a675987122e622287b030336f35d35cbdac3899c0`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/existing-dca-editor-selector-development.json`, SHA-256 `755f7ec55058802998b87b5b636f48ec0129b9d8faaa8e8ce5147775a39b6585`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/existing-dca-editor-selector-regression.json`, SHA-256 `f1bb24d354f8ec2b57e18ee104770498556bbb8dc8caf8b13cc68f8321d5b62f`. |
| Backend | `3089 passed, 3 skipped`. | `pytest -q`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands, test:proposals, test:setups and audit:high passed; zero high production dependency vulnerabilities. | Canonical local script output. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [run 37232364861](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37232364861), all five jobs green. |
| Main CI and Auto Deploy | `PASS`: [main CI 37232523493](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37232523493) and [Auto Deploy 37232641685](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37232641685) on `ba8884826ed5c4d0b185d6dc91cc51b48c506e86`. |
| Public backend health and frontend build-info | `PASS`: both HTTP 200 and SHA `ba8884826ed5c4d0b185d6dc91cc51b48c506e86`. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
