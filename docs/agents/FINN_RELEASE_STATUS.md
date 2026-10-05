# FINN Release Status

Status: canonical

Runtime identity comes from Git and public deployment surfaces, not this document's own commit SHA.

## Active Release

| Field | Value |
| --- | --- |
| Phase | `READY_FOR_INDEPENDENT_QA`; local Build gates, CI, Auto Deploy and public identity checks passed. |
| Goal | Explain an open, unconfirmed DCA concept during a coach follow-up without treating it as an absent saved plan. |
| Candidate branch | `codex/finn-open-dca-draft-read` |
| Candidate implementation SHA | `6fc4bc4643015aebbd86eb8381ad88d6928d2339`; followed by this release-status commit. |
| PR | [#71](https://github.com/gvangalen/antigravity-trading-tool/pull/71), merged. |
| Production SHA | `c928622bbe6a5b67d44bdd9bc4c7112f5b26003b`; public backend and frontend both reported it with HTTP 200 on 2026-10-05. This status-only follow-up creates a later deploy SHA; verify that final identity separately. |
| Release owner | Build |
| Last updated | 2026-10-05 |

## Change And Limits

- Authenticated browser QA on `41fb2aa7...` confirmed new fixed and Smart ETH-DCA concept, confirmation, persistence, Friday/month-day editor display, and stored-strategy readback. The remaining coach defect was that a question about an unconfirmed fixed-DCA card said the plan could not be found among saved plans.
- Local real Responses replay reproduced the failure: for a named open €75 Friday draft, the model selected `get_saved_setup_inventory` and answered that no saved plan existed. The verified proposal was available in the same conversation. The read boundary now supplies that open draft as typed evidence when a saved-plan tool is selected for the draft itself. It does not write the draft or replace the model's answer. An explicitly different named saved plan still uses the saved-plan read.
- The draft evidence now distinguishes fixed from Smart DCA: a fixed amount does not require a benchmark score to determine its amount; a Smart score curve holds without complete benchmark components. Neither statement proves that a trade will execute.
- Post-change local real Responses replay answered four varied named follow-ups as €75 on Friday and correctly identified the draft as unconfirmed. The wider fixed-DCA coach variation also passed. This is local evidence, not authenticated production acceptance.
- The actual score-driven purchase path remains unproven in live QA because complete current ETH benchmark scores were unavailable. No purchase or bot activation was performed by Build.

## Local Build Evidence

The isolated parity stack used PostgreSQL, Redis, FastAPI, prefork Celery and the real Responses provider. The chat model was `gpt-6-luna` with reasoning `none`; the selector gate used its configured `gpt-4o-mini`. Build did not access protected QA fixtures or the sealed holdout.

| Gate | Result | Evidence |
| --- | --- | --- |
| Open draft coach replays | Four varied named follow-ups passed; model still sometimes chose a saved read, but received the verified open draft and answered correctly. | `.local-finn-parity-artifacts/open-fixed-dca-coach-repeat.json`, SHA-256 `610386f1c77d28cac3ccd4f6e9b6059a2be49b6b45e4e3216d97e33a94d5cb26`. |
| Worker-driven safe action contracts | `16/16`; zero broker orders, live bots, live trading calls or production connections. | `.local-finn-parity-artifacts/open-dca-draft-read-action-matrix.json`, SHA-256 `67e104a2ea34b1b710db2683c160d2d8283a4007275fa0e9cb651a54fb93ae33`. |
| Real-provider selector development | `18/18`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/open-dca-draft-read-selector-development.json`, SHA-256 `213b6e680bfbf4912e06ab023b314ead84b5ee46fbc8941b92671d1042cfac3e`. |
| Real-provider selector regression | `109/109`; zero provider, schema, parse, validation or timeout failures. | `.local-finn-parity-artifacts/open-dca-draft-read-selector-regression.json`, SHA-256 `0932bd2703cd10db477b1c83411c4d19f721e0b653e8d7c4d4effe6236f8b573`. |
| Backend | `3092 passed, 3 skipped`; focused open-draft tests `4 passed`. | `pytest -q`; `.local-finn-parity-artifacts/open-dca-draft-read-pytest.log`. |
| Frontend | Build, typecheck, lint:i18n, test:i18n, test:commands, test:proposals, test:setups and audit:high passed; zero high production dependency vulnerabilities. | Canonical local script output. |

## Release And Independent QA

| Gate | Status |
| --- | --- |
| Candidate CI | `PASS`: [run 37266074879](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37266074879), all five jobs green. |
| Main CI and Auto Deploy | `PASS`: [main CI 37266209368](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37266209368) and [Auto Deploy 37266347102](https://github.com/gvangalen/antigravity-trading-tool/actions/runs/37266347102) on `c928622bbe6a5b67d44bdd9bc4c7112f5b26003b`. |
| Public backend health and frontend build-info | `PASS`: both HTTP 200 and SHA `c928622bbe6a5b67d44bdd9bc4c7112f5b26003b`. |
| Independent authenticated live QA | Pending; QA owns its protected fixture and verdict. |

Local Build evidence does not establish authenticated production acceptance.
